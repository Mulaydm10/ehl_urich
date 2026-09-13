"""
bike_link.py — the local phone <-> motorcycle link (Bluetooth), transport-agnostic.

The BMW cloud (bmw_cloud.py) is one channel. The other is the local link between
the phone and the bike's TFT / ConnectedRide Navigator: in the real BMW Motorrad
Connected app that is BLE (accessory pairing, ConnectedRide Control) plus the
Bosch mySPIN SDK (phone <-> TFT mirroring, send-to-navigator). This module owns
that second channel on the backend side and exposes one stable HTTP contract
(api.py, /api/bmw/link/*) for the app.

Two transports implement the same interface:

* StandInTransport   - runs anywhere (VM, emulator, laptop). It keeps honest
                       state so the whole UI flow can be exercised, but it can
                       NEVER report a real connection or a real route transfer:
                       every answer carries ``standIn: true`` and ``ok: false``
                       for anything that would have needed a radio.
* NativeBleTransport - the backend has no radio of its own; the phone does. The
                       Capacitor plugin on the phone owns BLE I/O and reports
                       adapter / scan / connection / transfer state here
                       (POST /api/bmw/link/native/report). ``send`` hands the
                       phone a GPX payload and a transferId, and the transfer
                       only becomes ``sent`` once the phone reports it did.

Honesty rule (same as the rest of the backend): nothing here ever claims a
bike connection or a route transfer that did not happen on a real device.

Unverified: the BLE GATT layout and the mySPIN wire protocol of the real bike
were not captured (the analysis emulator has no radio). Nothing in this file
depends on specific UUIDs or opcodes; the payload is plain GPX 1.1, which is
what the phone-side transport has to translate once the protocol is known.

What the decompiled BMW app does instead (docs/28): the bike head unit (ICC)
is a *bonded Bluetooth Classic* device reached over RFCOMM/SPP, carrying a
ZeroC Ice session; navigation is pushed as maneuvers, not as a GPX file. The
debug trail below exists so that the phone's real radio behaviour next to the
bike can be watched live from here instead of guessed.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Literal
from xml.sax.saxutils import escape

TransportKind = Literal["stand_in", "native_ble"]
ConnectionState = Literal["unavailable", "disconnected", "connecting", "connected"]
TransferStatus = Literal["stand_in", "pending_phone", "sent", "failed", "unknown_transfer"]

TRAIL_LIMIT = 4000  # debug events kept in memory; oldest dropped first


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def route_to_gpx(route: dict) -> str:
    """GPX 1.1 for a route in the bmw_cloud shape (path as {lat,lng}, pois with atKm)."""
    name = escape(str(route.get("name", "Route")))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="FLOWSTATE bike-link" xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <metadata><name>{name}</name></metadata>",
    ]
    path = route.get("path") or []
    total_km = float(route.get("distanceKm") or 0)
    for poi in route.get("pois") or []:
        if not path or total_km <= 0:
            break
        idx = min(len(path) - 1, max(0, round(float(poi.get("atKm", 0)) / total_km * (len(path) - 1))))
        p = path[idx]
        lines.append(
            f'  <wpt lat="{p["lat"]:.6f}" lon="{p["lng"]:.6f}"><name>{escape(str(poi.get("name", "")))}</name></wpt>'
        )
    lines.append(f"  <trk><name>{name}</name><trkseg>")
    for p in path:
        lines.append(f'    <trkpt lat="{p["lat"]:.6f}" lon="{p["lng"]:.6f}"></trkpt>')
    lines += ["  </trkseg></trk>", "</gpx>", ""]
    return "\n".join(lines)


def capabilities_for(bike: dict | None) -> dict:
    """
    What the bike can take from the phone. Only the garage record is known here:
    a physical TFT / Navigator / sensor box can only be confirmed by the phone
    once it is actually connected to the bike. ``None`` means "unverified".
    """
    if bike is None:
        return {"ok": False, "note": "Unknown bike.", "verified": False}
    has_module = bike.get("connection") != "phone_only"
    return {
        "ok": True,
        "bikeId": bike["id"],
        "verified": False,
        "source": "garage_record",
        "hasTft": has_module,
        "hasConnectedRideNavigator": bool(bike.get("hasConnectedRideNavigator")),
        "hasSensorBox": None,
        "hasV2bCapability": None,
        "navigationHandoff": has_module,
        "note": ("Read from the garage record, not from the bike. A physical TFT or "
                 "ConnectedRide Navigator is required for navigation handoff; sensor box "
                 "and V2B capability are only known once the phone has connected.")
                if has_module else
                "No connectivity module: navigation stays on the phone.",
    }


# --------------------------------------------------------------------------
# debug trail — what actually happened on the radio
# --------------------------------------------------------------------------

class DebugTrail:
    """
    In-memory, monotonically numbered event log of the link.

    The phone posts what its radio did (POST /api/bmw/link/debug); the backend
    appends what it did itself. Anyone watching (the app's log panel, curl on
    the Mac) polls GET /api/bmw/link/debug?since=<seq>. It is a diagnostic
    record only: an event here never changes connection or transfer state.
    """

    def __init__(self, limit: int = TRAIL_LIMIT) -> None:
        self.limit = limit
        self.events: list[dict] = []
        self.next_seq = 1
        self.dropped = 0

    def add(self, source: str, op: str, level: str = "info", **fields) -> dict:
        ev = {
            "seq": self.next_seq,
            "at": time.time(),
            "source": source,       # "phone" | "backend"
            "op": op,               # scan.start, gatt.write.ack, icc.probe, ...
            "level": level,         # info | warn | error
            **{k: v for k, v in fields.items() if v is not None},
        }
        self.next_seq += 1
        self.events.append(ev)
        if len(self.events) > self.limit:
            cut = len(self.events) - self.limit
            del self.events[:cut]
            self.dropped += cut
        return ev

    def ingest(self, events: list[dict], session: str | None = None) -> dict:
        """Phone-side events keep their own timestamps/ordering fields."""
        taken = 0
        for e in events:
            if not isinstance(e, dict):
                continue
            self.add(
                str(e.get("source") or "phone"),
                str(e.get("op") or "phone.event"),
                str(e.get("level") or "info"),
                session=session or e.get("session"),
                phoneSeq=e.get("seq"),
                phoneAt=e.get("at"),
                detail={k: v for k, v in e.items()
                        if k not in ("source", "op", "level", "seq", "at", "session")} or None,
            )
            taken += 1
        return {"ok": True, "accepted": taken, "nextSeq": self.next_seq}

    def since(self, seq: int = 0, limit: int = 500) -> dict:
        out = [e for e in self.events if e["seq"] > seq][:limit]
        return {
            "ok": True,
            "events": out,
            "nextSeq": self.next_seq,
            "count": len(out),
            "dropped": self.dropped,
            "buffered": len(self.events),
        }

    def clear(self) -> dict:
        self.events.clear()
        self.dropped = 0
        return {"ok": True, "nextSeq": self.next_seq}

    def telemetry(self) -> dict:
        """
        Latest mySPIN vehicle-data value per key, plus what the head unit
        granted this app. Derived purely from what the phone reported: an empty
        result means the phone never received vehicle data, never a placeholder.
        """
        values: dict[str, dict] = {}
        access: dict[str, bool] = {}
        connected = False
        for ev in self.events:
            detail = ev.get("detail") or {}
            op = ev.get("op")
            if op == "vehicle.data":
                key = detail.get("key")
                if key:
                    values[str(key)] = {"values": detail.get("values"), "at": ev.get("phoneAt") or ev.get("at")}
            elif op == "myspin.access":
                key = detail.get("key")
                if key:
                    access[str(key)] = bool(detail.get("granted"))
            elif op == "myspin.connection":
                connected = bool(detail.get("connected"))
        return {
            "ok": True,
            "connected": connected,
            "granted": sorted(k for k, v in access.items() if v),
            "denied": sorted(k for k, v in access.items() if not v),
            "values": values,
            "note": "" if values else "No mySPIN vehicle data has been reported by a phone yet.",
        }


# --------------------------------------------------------------------------
# transports
# --------------------------------------------------------------------------

class BikeLinkTransport:
    kind: TransportKind
    stand_in: bool

    def __init__(self, cloud) -> None:
        self.cloud = cloud
        self.transfers: dict[str, dict] = {}

    # -- read --
    def adapter(self) -> dict: raise NotImplementedError
    def devices(self) -> list[dict]: raise NotImplementedError
    def connection(self) -> dict: raise NotImplementedError

    # -- act --
    def scan(self, active: bool) -> dict: raise NotImplementedError
    def pair(self, device_id: str) -> dict: raise NotImplementedError
    def unpair(self, device_id: str) -> dict: raise NotImplementedError
    def connect(self, device_id: str) -> dict: raise NotImplementedError
    def disconnect(self) -> dict: raise NotImplementedError
    def send(self, route: dict, bike: dict, device_id: str | None) -> dict: raise NotImplementedError

    def status(self) -> dict:
        return {
            "transport": self.kind,
            "standIn": self.stand_in,
            "adapter": self.adapter(),
            "connection": self.connection(),
            "devices": self.devices(),
        }

    def transfer(self, transfer_id: str) -> dict:
        t = self.transfers.get(transfer_id)
        if t is None:
            return {"ok": False, "status": "unknown_transfer", "transferId": transfer_id,
                    "standIn": self.stand_in, "message": "No such transfer."}
        return t

    def _new_transfer(self, route: dict, bike: dict, device_id: str | None,
                      status: TransferStatus, ok: bool, message: str) -> dict:
        tid = f"tx-{uuid.uuid4().hex[:10]}"
        t = {
            "ok": ok,
            "status": status,
            "standIn": self.stand_in,
            "transport": self.kind,
            "transferId": tid,
            "routeId": route["id"],
            "bikeId": bike["id"],
            "deviceId": device_id,
            "target": "ConnectedRide Navigator" if bike.get("hasConnectedRideNavigator") else
                      ("TFT" if bike.get("connection") != "phone_only" else "phone"),
            "message": message,
            "createdAt": time.time(),
            "updatedAt": time.time(),
        }
        self.transfers[tid] = t
        return t


class StandInTransport(BikeLinkTransport):
    """No radio. Exercises the flow, never claims a bike heard anything."""

    kind: TransportKind = "stand_in"
    stand_in = True
    NOTE = "stand-in: nothing was sent to a physical bike"

    def __init__(self, cloud) -> None:
        super().__init__(cloud)
        self._scanning = False
        self._paired: set[str] = set()
        self._connected: str | None = None

    def _device_for(self, bike: dict) -> dict:
        return {
            "id": f"standin-{bike['id']}",
            "name": f"{bike['model']} TFT (stand-in)",
            "bikeId": bike["id"],
            "rssi": None,
            "paired": f"standin-{bike['id']}" in self._paired,
            "standIn": True,
        }

    def adapter(self) -> dict:
        return {"present": False, "enabled": False, "standIn": True,
                "note": "Stand-in transport: this backend has no Bluetooth adapter. "
                        "Pairing and transfers below are simulated and say so."}

    def devices(self) -> list[dict]:
        if not self._scanning and not self._paired:
            return []
        out = [self._device_for(b) for b in self.cloud.get_bikes() if b.get("connection") != "phone_only"]
        return out if self._scanning else [d for d in out if d["paired"]]

    def connection(self) -> dict:
        state: ConnectionState = "connected" if self._connected else "disconnected"
        dev = next((d for d in self.devices() if d["id"] == self._connected), None) if self._connected else None
        return {"state": state, "deviceId": self._connected, "deviceName": dev["name"] if dev else None,
                "standIn": True, "scanning": self._scanning,
                "note": f"{self.NOTE}; this connection is simulated." if self._connected else self.NOTE}

    def scan(self, active: bool) -> dict:
        self._scanning = active
        return {"ok": True, "scanning": active, "standIn": True, "devices": self.devices(), "note": self.NOTE}

    def _known(self, device_id: str) -> dict | None:
        return next((self._device_for(b) for b in self.cloud.get_bikes()
                     if b.get("connection") != "phone_only" and f"standin-{b['id']}" == device_id), None)

    def pair(self, device_id: str) -> dict:
        if self._known(device_id) is None:
            return {"ok": False, "standIn": True, "message": f"No device {device_id}."}
        self._paired.add(device_id)
        return {"ok": True, "standIn": True, "device": self._known(device_id),
                "message": f"Simulated pairing only ({self.NOTE})."}

    def unpair(self, device_id: str) -> dict:
        self._paired.discard(device_id)
        if self._connected == device_id:
            self._connected = None
        return {"ok": True, "standIn": True, "message": "Simulated pairing removed."}

    def connect(self, device_id: str) -> dict:
        if device_id not in self._paired:
            return {"ok": False, "standIn": True, "connection": self.connection(),
                    "message": "Pair the device first."}
        self._connected = device_id
        return {"ok": True, "standIn": True, "connection": self.connection(),
                "message": f"Simulated connection only ({self.NOTE})."}

    def disconnect(self) -> dict:
        self._connected = None
        return {"ok": True, "standIn": True, "connection": self.connection()}

    def send(self, route: dict, bike: dict, device_id: str | None) -> dict:
        # ok is always False here: a stand-in must never look like a transfer.
        t = self._new_transfer(
            route, bike, device_id or self._connected, "stand_in", False,
            f"Stand-in transport: route '{route['name']}' was NOT sent to {bike['model']} "
            f"({self.NOTE}). Build and run the Android app next to the bike to send it for real.",
        )
        t["gpxBytes"] = len(route_to_gpx(route).encode())
        return t


class NativeBleTransport(BikeLinkTransport):
    """
    The phone owns the radio. This side is a mirror of what the phone reported
    plus the transfer ledger; it never invents state the phone did not send.
    """

    kind: TransportKind = "native_ble"
    stand_in = False

    def __init__(self, cloud) -> None:
        super().__init__(cloud)
        self._adapter: dict = {"present": None, "enabled": None, "standIn": False,
                               "note": "No report from the phone yet."}
        self._devices: list[dict] = []
        self._connection: dict = {"state": "unavailable", "deviceId": None, "deviceName": None,
                                  "standIn": False, "scanning": False,
                                  "note": "No report from the phone yet."}
        self._reported_at: float | None = None

    def adapter(self) -> dict:
        return {**self._adapter, "reportedAt": self._reported_at}

    def devices(self) -> list[dict]:
        return self._devices

    def connection(self) -> dict:
        return {**self._connection, "reportedAt": self._reported_at}

    def _phone_only(self, action: str) -> dict:
        return {"ok": False, "standIn": False, "delegatedToPhone": True,
                "message": f"'{action}' runs on the phone's Bluetooth radio (BikeLink plugin); "
                           f"the backend only mirrors what the phone reports."}

    def scan(self, active: bool) -> dict: return self._phone_only("scan")
    def pair(self, device_id: str) -> dict: return self._phone_only("pair")
    def unpair(self, device_id: str) -> dict: return self._phone_only("unpair")
    def connect(self, device_id: str) -> dict: return self._phone_only("connect")
    def disconnect(self) -> dict: return self._phone_only("disconnect")

    def send(self, route: dict, bike: dict, device_id: str | None) -> dict:
        if self._connection.get("state") != "connected":
            return self._new_transfer(route, bike, device_id, "failed", False,
                                      "Phone reports no connected bike; nothing was sent.")
        t = self._new_transfer(route, bike, device_id or self._connection.get("deviceId"),
                               "pending_phone", False,
                               "Handed to the phone's Bluetooth link; waiting for the phone to "
                               "confirm the bike received it.")
        t["gpx"] = route_to_gpx(route)
        return t

    def report(self, rep: dict) -> dict:
        """Phone -> backend: adapter / devices / connection / transfer outcome."""
        self._reported_at = time.time()
        if isinstance(rep.get("adapter"), dict):
            self._adapter = {**self._adapter, "note": "", **rep["adapter"], "standIn": False}
        if isinstance(rep.get("devices"), list):
            self._devices = [{**d, "standIn": False} for d in rep["devices"] if isinstance(d, dict)]
        if isinstance(rep.get("connection"), dict):
            self._connection = {**self._connection, "note": "", **rep["connection"], "standIn": False}
        tx = rep.get("transfer")
        if isinstance(tx, dict) and tx.get("transferId") in self.transfers:
            t = self.transfers[tx["transferId"]]
            sent = bool(tx.get("ok"))
            t.update({"ok": sent, "status": "sent" if sent else "failed",
                      "message": str(tx.get("message") or ("Bike confirmed the route." if sent else
                                                            "Phone reported the transfer failed.")),
                      "updatedAt": time.time()})
            t.pop("gpx", None)
        return {"ok": True, "status": self.status()}


# --------------------------------------------------------------------------
# facade used by api.py
# --------------------------------------------------------------------------

class BikeLink:
    def __init__(self, cloud, transport: str | None = None) -> None:
        self.cloud = cloud
        kind = (transport or os.environ.get("FLOWSTATE_BIKE_LINK", "stand_in")).strip().lower()
        self.transport: BikeLinkTransport = (
            NativeBleTransport(cloud) if kind in ("native", "native_ble", "ble") else StandInTransport(cloud)
        )
        self.trail = DebugTrail()
        self.trail.add("backend", "link.init", transportKind=self.transport.kind,
                       standIn=self.transport.stand_in)

    def status(self) -> dict:
        return self.transport.status()

    def capabilities(self, bike_id: str) -> dict:
        caps = capabilities_for(self.cloud.get_bike(bike_id))
        conn = self.transport.connection()
        caps["linkState"] = conn.get("state")
        caps["standIn"] = self.transport.stand_in
        return caps

    def send(self, route_id: str, bike_id: str, device_id: str | None) -> dict:
        route = next((r for r in self.cloud.get_routes() if r["id"] == route_id), None)
        bike = self.cloud.get_bike(bike_id)
        if route is None or bike is None:
            return {"ok": False, "status": "failed", "standIn": self.transport.stand_in,
                    "transport": self.transport.kind, "target": "phone",
                    "message": f"No route {route_id}." if route is None else f"No bike {bike_id}."}
        if bike.get("connection") == "phone_only":
            return {"ok": False, "status": "failed", "standIn": self.transport.stand_in,
                    "transport": self.transport.kind, "target": "phone",
                    "message": f"{bike['model']} has no connectivity module - navigating on the phone."}
        t = self.transport.send(route, bike, device_id)
        self.trail.add("backend", "transfer.created", level="warn" if not t.get("ok") else "info",
                       transferId=t.get("transferId"), status=t.get("status"), routeId=route_id,
                       bikeId=bike_id, deviceId=device_id, gpxBytes=len(t.get("gpx", "")) or None)
        return t

    def gpx(self, route_id: str) -> str | None:
        route = next((r for r in self.cloud.get_routes() if r["id"] == route_id), None)
        return route_to_gpx(route) if route else None

    def report(self, rep: dict) -> dict:
        tx = rep.get("transfer") if isinstance(rep.get("transfer"), dict) else None
        self.trail.add("phone", "report", level="warn" if tx and not tx.get("ok") else "info",
                       connection=rep.get("connection"), adapter=rep.get("adapter"),
                       deviceCount=len(rep["devices"]) if isinstance(rep.get("devices"), list) else None,
                       transfer=tx)
        if isinstance(self.transport, NativeBleTransport):
            return self.transport.report(rep)
        return {"ok": False, "standIn": True,
                "message": "Backend is running the stand-in transport; phone reports are ignored. "
                           "Start it with FLOWSTATE_BIKE_LINK=native to mirror the phone."}
