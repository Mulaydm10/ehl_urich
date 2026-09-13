"""
bmw_cloud.py — the BMW-side services the route engine never had.

FLOWSTATE (service.py) is the fun-fit route engine. It knows nothing about a
garage, a fuel level, a recorded ride, a group ride or an offline map catalog.
Those are the ConnectedRide-style features the reference BMW Motorrad app
provided; this module adds them to the backend so the app can route every one
of its services through one place and be tested live.

There is no real BMW cloud reachable from here (and under the hackathon NDA the
crowd data never leaves the Mac). So this is an in-process mock store that
returns exactly the shapes the front end's domain types expect. When the real
BMW backend is handed over, replace the bodies here with real calls; the HTTP
surface in api.py and the whole front end stay unchanged.

Every geometry helper is a faithful port of the front end's mock.ts generators
(the same LCG and the same seeds), so the offline fallback in the app and the
live backend agree to the pixel.
"""

from __future__ import annotations

import math
import time
import uuid
from typing import Callable


# --------------------------------------------------------------------------
# deterministic geometry — ports of mock.ts so live and offline agree
# --------------------------------------------------------------------------

def _rand(seed: int) -> Callable[[], float]:
    s = {"v": seed}

    def nxt() -> float:
        s["v"] = (s["v"] * 1103515245 + 12345) % 2147483648
        return s["v"] / 2147483648

    return nxt


def _make_path(seed: int, frm: dict, to: dict, wiggle: float, points: int = 220) -> list[dict]:
    r = _rand(seed)
    d_lat = to["lat"] - frm["lat"]
    d_lng = to["lng"] - frm["lng"]
    length = math.hypot(d_lat, d_lng) or 1.0
    px = -d_lat / length
    py = d_lng / length
    phase = r() * math.pi * 2
    drift = (r() - 0.5) * wiggle * 4
    out = []
    for i in range(points):
        t = i / (points - 1)
        envelope = math.sin(t * math.pi)
        bend = (
            math.sin(t * math.pi * 1.3 + phase) * wiggle * 6
            + math.sin(t * math.pi * 5.7 + phase * 2) * wiggle * 2.2
            + math.sin(t * math.pi * 13.1 + phase * 3) * wiggle * 0.8
        )
        offset = (bend + drift) * envelope
        out.append({
            "lat": frm["lat"] + d_lat * t + py * offset * 0.7,
            "lng": frm["lng"] + d_lng * t + px * offset,
        })
    return out


def _make_elevation(seed: int, distance_km: float, peak: float) -> list[dict]:
    r = _rand(seed)
    steps = 60
    limits = [50, 70, 80, 100]
    out = []
    for i in range(steps):
        t = i / (steps - 1)
        base = 480 + math.sin(t * math.pi) * peak + math.sin(t * math.pi * 5) * peak * 0.16
        out.append({
            "km": round(t * distance_km, 1),
            "elevationM": round(base + (r() - 0.5) * 40),
            "speedLimit": limits[int(r() * 4)],
        })
    return out


def _make_samples(seed: int, distance_km: float, sporty: float) -> list[dict]:
    r = _rand(seed)
    steps = 120
    out = []
    for i in range(steps):
        t = i / (steps - 1)
        twist = math.sin(t * math.pi * 9)
        out.append({
            "km": round(t * distance_km, 1),
            "speedKmh": round(60 + math.sin(t * math.pi * 4) * 35 + r() * 20),
            "leanLeftDeg": max(0, round((twist if twist > 0 else 0) * sporty + r() * 6)),
            "leanRightDeg": max(0, round((-twist if twist < 0 else 0) * sporty + r() * 6)),
            "altitudeM": round(500 + math.sin(t * math.pi) * 900 + r() * 60),
            "rpm": round(3500 + math.sin(t * math.pi * 6) * 2200 + r() * 500),
        })
    return out


# --------------------------------------------------------------------------
# the store — mutable so recording / downloads / handoff are real state
# --------------------------------------------------------------------------

class BmwCloud:
    """In-process stand-in for the ConnectedRide cloud + the phone's own data."""

    def __init__(self) -> None:
        self.profile = {
            "bmwId": "rider@example.com",
            "displayName": "Jacob",
            "memberSince": "2019",
            "homeDealer": "BMW Motorrad Munchen",
        }
        self.bikes = _seed_bikes()
        self.routes = _seed_routes()
        self.rides = _seed_rides()
        self.group = _seed_group()
        self.regions = _seed_regions()
        self.stats = {
            "year": 2026, "rides": 47, "distanceKm": 6218, "ridingTimeMin": 9840,
            "passesRidden": 23, "topCurviness": 97, "countries": ["DE", "AT", "IT", "CH"],
        }
        # live ride recording, keyed by id
        self._recordings: dict[str, dict] = {}

    # -- garage / account ------------------------------------------------
    def get_profile(self) -> dict:
        return self.profile

    def get_bikes(self) -> list[dict]:
        return self.bikes

    def get_bike(self, bike_id: str) -> dict | None:
        return next((b for b in self.bikes if b["id"] == bike_id), None)

    def vehicle_status(self, bike_id: str) -> dict:
        """The live 'vehicle status' tile. Phone-only bikes report unavailable."""
        b = self.get_bike(bike_id)
        if b is None:
            return {"ok": False, "note": f"No bike {bike_id} in the garage."}
        if b["connection"] == "phone_only":
            return {"ok": True, "bikeId": bike_id, "live": False,
                    "note": "This bike has no connectivity module; the phone shows ride "
                            "data only.",
                    "fuelPercent": None, "rangeKm": None, "odometerKm": None,
                    "batteryVolt": None, "tyrePressureBar": None,
                    "serviceDueKm": None, "serviceDueDate": None, "recall": None}
        return {"ok": True, "bikeId": bike_id, "live": b["connection"] == "connected",
                "note": "", "fuelPercent": b["fuelPercent"], "rangeKm": b["rangeKm"],
                "odometerKm": b["odometerKm"], "batteryVolt": b["batteryVolt"],
                "tyrePressureBar": b["tyrePressureBar"], "serviceDueKm": b["serviceDueKm"],
                "serviceDueDate": b["serviceDueDate"], "recall": b["recall"]}

    # -- routes / cloud sync ---------------------------------------------
    def get_routes(self) -> list[dict]:
        return self.routes

    def plan_route(self, inp: dict) -> dict:
        base = self.routes[0]
        factor = {"fastest": 0.82, "fast_curvy": 0.95, "curvy": 1.0, "extra_curvy": 1.18}[inp["mode"]]
        curviness = {"fastest": 38, "fast_curvy": 62, "curvy": 81, "extra_curvy": 94}[inp["mode"]]
        rt = bool(inp.get("roundTrip"))
        route = {
            **base,
            "id": f"r-{int(time.time() * 1000)}",
            "name": f"{inp['origin']} round trip" if rt else f"{inp['origin']} - {inp['destination']}",
            "origin": inp["origin"],
            "destination": inp["origin"] if rt else inp["destination"],
            "via": inp.get("via", []),
            "mode": inp["mode"],
            "avoid": inp.get("avoid", []),
            "roundTrip": rt,
            "distanceKm": round(base["distanceKm"] * factor),
            "durationMin": round(base["durationMin"] * factor),
            "curvinessScore": curviness,
            "source": "planned",
            "savedAt": "just now",
        }
        self.routes.insert(0, route)
        return route

    def import_route(self, file_name: str) -> dict:
        src = self.routes[-1]
        route = {**src, "id": f"r-{int(time.time() * 1000)}", "author": file_name,
                 "savedAt": "Imported just now", "source": "imported"}
        self.routes.insert(0, route)
        return route

    def export_route(self, route_id: str, target: str) -> dict:
        return {"ok": True, "file": f"{route_id}-{target}.gpx"}

    def handoff(self, route_id: str, bike_id: str) -> dict:
        b = self.get_bike(bike_id)
        if b is None:
            return {"ok": False, "target": "phone", "message": f"No bike {bike_id}."}
        if b["hasConnectedRideNavigator"]:
            return {"ok": True, "target": "ConnectedRide Navigator",
                    "message": f"Route on {b['model']}. Scroll it with the handlebar wheel."}
        return {"ok": False, "target": "phone",
                "message": f"{b['model']} has no ConnectedRide Navigator - navigating on the "
                           f"phone instead."}

    # -- rides ------------------------------------------------------------
    def get_rides(self) -> list[dict]:
        return self.rides

    def start_recording(self, bike_id: str, title: str) -> dict:
        rid = f"live-{uuid.uuid4().hex[:8]}"
        rec = {"id": rid, "bikeId": bike_id, "title": title or "Live ride",
               "startedAt": time.time(), "distanceKm": 0.0, "durationMin": 0,
               "maxLeanLeftDeg": 0, "maxLeanRightDeg": 0, "samples": [], "recording": True}
        self._recordings[rid] = rec
        return {"ok": True, "rideId": rid}

    def push_sample(self, ride_id: str, sample: dict) -> dict:
        rec = self._recordings.get(ride_id)
        if not rec or not rec["recording"]:
            return {"ok": False, "note": "No such live ride."}
        rec["samples"].append(sample)
        rec["distanceKm"] = round(sample.get("km", rec["distanceKm"]), 1)
        rec["maxLeanLeftDeg"] = max(rec["maxLeanLeftDeg"], sample.get("leanLeftDeg", 0))
        rec["maxLeanRightDeg"] = max(rec["maxLeanRightDeg"], sample.get("leanRightDeg", 0))
        return {"ok": True, "samples": len(rec["samples"]),
                "distanceKm": rec["distanceKm"]}

    def stop_recording(self, ride_id: str) -> dict:
        rec = self._recordings.get(ride_id)
        if not rec:
            return {"ok": False, "note": "No such live ride."}
        rec["recording"] = False
        dur = max(1, round((time.time() - rec["startedAt"]) / 60))
        speeds = [s.get("speedKmh", 0) for s in rec["samples"]] or [0]
        ride = {
            "id": rec["id"], "title": rec["title"], "date": "Just now", "bikeId": rec["bikeId"],
            "distanceKm": rec["distanceKm"], "durationMin": dur,
            "avgSpeedKmh": round(sum(speeds) / len(speeds)), "topSpeedKmh": max(speeds),
            "maxLeanLeftDeg": rec["maxLeanLeftDeg"], "maxLeanRightDeg": rec["maxLeanRightDeg"],
            "ascentM": 0, "curvinessScore": 0,
            # one malformed sample must not lose the whole ride: accept lng or lon,
            # skip samples with no position
            "path": [{"lat": s["lat"], "lng": s.get("lng", s.get("lon"))} for s in rec["samples"]
                     if "lat" in s and ("lng" in s or "lon" in s)],
            "samples": rec["samples"], "photos": [],
        }
        self.rides.insert(0, ride)
        return {"ok": True, "ride": ride}

    # -- group ------------------------------------------------------------
    def get_group(self) -> dict:
        return self.group

    # -- maps -------------------------------------------------------------
    def get_regions(self) -> list[dict]:
        return self.regions

    def start_download(self, region_id: str) -> dict:
        region = next((r for r in self.regions if r["id"] == region_id), None)
        if region is None:
            return {"ok": False, "note": f"Unknown region {region_id}"}
        region["status"] = "downloading"
        region["progress"] = max(region["progress"], 5)
        return {"ok": True, "region": region}

    # -- stats ------------------------------------------------------------
    def get_stats(self) -> dict:
        return self.stats


def _seed_bikes() -> list[dict]:
    return [
        {"id": "gs", "model": "R 1300 GS", "variant": "Adventure \u00b7 Racing Blue",
         "vin": "WB10A0308PZ***421", "imageTint": "#2E9CE8", "connection": "connected",
         "lastSeen": "Live \u00b7 2 min ago", "fuelPercent": 68, "rangeKm": 412,
         "odometerKm": 24817, "tankLitres": 19, "consumptionLper100": 4.7,
         "serviceDueKm": 3183, "serviceDueDate": "14 Apr 2026", "recall": None,
         "tyrePressureBar": {"front": 2.4, "rear": 2.8}, "batteryVolt": 12.9,
         "hasConnectedRideNavigator": True},
        {"id": "xr", "model": "S 1000 XR", "variant": "M Package \u00b7 Light White",
         "vin": "WB10E1308MZ***077", "imageTint": "#E7222E", "connection": "last_seen",
         "lastSeen": "Last seen yesterday, 19:42", "fuelPercent": 31, "rangeKm": 143,
         "odometerKm": 11294, "tankLitres": 20, "consumptionLper100": 6.1,
         "serviceDueKm": 706, "serviceDueDate": "02 Mar 2026",
         "recall": "Recall 0061240200 - rear brake line clip inspection",
         "tyrePressureBar": {"front": 2.5, "rear": 2.9}, "batteryVolt": 12.4,
         "hasConnectedRideNavigator": True},
        {"id": "nine", "model": "R 12 nineT", "variant": "Option 719 Aluminium",
         "vin": "WB10J0107RZ***903", "imageTint": "#C9A227", "connection": "phone_only",
         "lastSeen": "No connectivity module", "fuelPercent": None, "rangeKm": None,
         "odometerKm": None, "tankLitres": 16, "consumptionLper100": 5.4,
         "serviceDueKm": None, "serviceDueDate": None, "recall": None,
         "tyrePressureBar": None, "batteryVolt": None, "hasConnectedRideNavigator": False},
        {"id": "ce04", "model": "CE 04", "variant": "Avantgarde \u00b7 Magellan Grey",
         "vin": "WB10K0400NZ***155", "imageTint": "#8BFF2E", "connection": "connected",
         "lastSeen": "Live \u00b7 charging", "fuelPercent": 54, "rangeKm": 72,
         "odometerKm": 6042, "tankLitres": 8.9, "consumptionLper100": 12.4,
         "serviceDueKm": 1958, "serviceDueDate": "30 Jun 2026", "recall": None,
         "tyrePressureBar": {"front": 2.2, "rear": 2.5}, "batteryVolt": 12.7,
         "hasConnectedRideNavigator": False},
    ]


def _alpine_pois() -> list[dict]:
    return [
        {"id": "p1", "name": "Aral Bad Tolz", "layer": "fuel", "atKm": 46,
         "note": "Last fuel before the pass"},
        {"id": "p2", "name": "Sylvenstein dam viewpoint", "layer": "twisty", "atKm": 71},
        {"id": "p3", "name": "Achenpass \u00b7 941 m", "layer": "passes", "atKm": 88},
        {"id": "p4", "name": "Gasthof Alpenrose", "layer": "food", "atKm": 103,
         "note": "Biker-friendly, big parking"},
        {"id": "p5", "name": "BMW Motorrad Garmisch", "layer": "dealers", "atKm": 141},
        {"id": "p6", "name": "Hotel Zugspitze (BMW partner)", "layer": "hotels", "atKm": 147},
    ]


def _seed_routes() -> list[dict]:
    return [
        {"id": "r-alpine", "name": "Alpine Passes Loop", "region": "Bavaria \u00b7 Tyrol",
         "origin": "Munchen", "destination": "Munchen",
         "via": ["Bad Tolz", "Achenpass", "Sylvenstein", "Garmisch"],
         "distanceKm": 294, "durationMin": 348, "ascentM": 3120, "curvinessScore": 83,
         "mode": "curvy", "avoid": ["motorways", "tolls"], "roundTrip": True,
         "segments": [
             {"fromKm": 0, "toKm": 42, "mode": "fastest", "road": "B11 out of the city"},
             {"fromKm": 42, "toKm": 188, "mode": "extra_curvy", "road": "Achenpass / Sylvenstein"},
             {"fromKm": 188, "toKm": 294, "mode": "fast_curvy", "road": "Loisach valley home"}],
         "elevation": _make_elevation(7, 294, 1150),
         "path": _make_path(11, {"lat": 48.137, "lng": 11.575}, {"lat": 47.492, "lng": 11.096}, 0.09),
         "pois": _alpine_pois(), "source": "planned", "savedAt": "2 days ago"},
        {"id": "r-stelvio", "name": "Stelvio Back Road", "region": "South Tyrol",
         "origin": "Bormio", "destination": "Prad am Stilfserjoch", "via": ["Passo dello Stelvio"],
         "distanceKm": 49, "durationMin": 96, "ascentM": 1840, "curvinessScore": 97,
         "mode": "extra_curvy", "avoid": ["unpaved"], "roundTrip": False,
         "segments": [{"fromKm": 0, "toKm": 49, "mode": "extra_curvy", "road": "SS38 \u00b7 48 hairpins"}],
         "elevation": _make_elevation(3, 49, 1700),
         "path": _make_path(5, {"lat": 46.467, "lng": 10.373}, {"lat": 46.617, "lng": 10.588}, 0.03),
         "pois": [{"id": "s1", "name": "Passo dello Stelvio \u00b7 2757 m", "layer": "passes", "atKm": 24},
                  {"id": "s2", "name": "Tibet Hutte", "layer": "food", "atKm": 26},
                  {"id": "s3", "name": "Agip Prad", "layer": "fuel", "atKm": 46}],
         "source": "curated", "author": "BMW Motorrad Touring", "savedAt": "Saved 1 week ago"},
        {"id": "r-gravel", "name": "Bohemian Gravel Link", "region": "Bavarian Forest",
         "origin": "Zwiesel", "destination": "Bayerisch Eisenstein", "via": ["Arber forest tracks"],
         "distanceKm": 112, "durationMin": 178, "ascentM": 1420, "curvinessScore": 74,
         "mode": "curvy", "avoid": ["tolls"], "roundTrip": False,
         "segments": [{"fromKm": 0, "toKm": 38, "mode": "curvy", "road": "Forest asphalt"},
                      {"fromKm": 38, "toKm": 74, "mode": "curvy", "road": "Gravel service road"},
                      {"fromKm": 74, "toKm": 112, "mode": "fast_curvy", "road": "B11 border run"}],
         "elevation": _make_elevation(9, 112, 780),
         "path": _make_path(13, {"lat": 49.017, "lng": 13.236}, {"lat": 49.122, "lng": 13.204}, 0.05),
         "pois": [{"id": "g1", "name": "Grosser Arber gravel start", "layer": "twisty", "atKm": 38},
                  {"id": "g2", "name": "Shell Zwiesel", "layer": "fuel", "atKm": 4},
                  {"id": "g3", "name": "Waldhaus (GS meetup)", "layer": "events", "atKm": 66}],
         "source": "community", "author": "gs_rider_muc", "savedAt": "Saved 3 weeks ago"},
        {"id": "r-city", "name": "Isar Night Loop", "region": "Munchen",
         "origin": "Munchen Ost", "destination": "Munchen Ost", "via": ["Isar riverside", "Olympiapark"],
         "distanceKm": 38, "durationMin": 62, "ascentM": 140, "curvinessScore": 41,
         "mode": "fastest", "avoid": ["motorways"], "roundTrip": True,
         "segments": [{"fromKm": 0, "toKm": 38, "mode": "fastest", "road": "City boulevards"}],
         "elevation": _make_elevation(17, 38, 90),
         "path": _make_path(21, {"lat": 48.12, "lng": 11.62}, {"lat": 48.18, "lng": 11.53}, 0.02),
         "pois": [{"id": "c1", "name": "Charge point Olympiapark", "layer": "parking", "atKm": 18},
                  {"id": "c2", "name": "Cafe Kosmos", "layer": "food", "atKm": 27}],
         "source": "curated", "author": "BMW Motorrad Urban", "savedAt": "Saved yesterday"},
        {"id": "r-import", "name": "Munich - Garmisch-Partenkirchen", "region": "Imported GPX",
         "origin": "Munchen", "destination": "Garmisch-Partenkirchen", "via": [],
         "distanceKm": 96, "durationMin": 129, "ascentM": 620, "curvinessScore": 58,
         "mode": "fast_curvy", "avoid": [], "roundTrip": False,
         "segments": [{"fromKm": 0, "toKm": 96, "mode": "fast_curvy", "road": "B2 / B23"}],
         "elevation": _make_elevation(23, 96, 520),
         "path": _make_path(29, {"lat": 48.137, "lng": 11.575}, {"lat": 47.492, "lng": 11.096}, 0.02),
         "pois": [{"id": "i1", "name": "Total Murnau", "layer": "fuel", "atKm": 58}],
         "source": "imported", "author": "kurviger_route.gpx", "savedAt": "Imported today"},
    ]


def _seed_rides() -> list[dict]:
    return [
        {"id": "ride-1", "title": "Achenpass evening", "date": "Sat 6 Sep \u00b7 16:20",
         "bikeId": "gs", "distanceKm": 187, "durationMin": 214, "avgSpeedKmh": 52,
         "topSpeedKmh": 164, "maxLeanLeftDeg": 43, "maxLeanRightDeg": 39, "ascentM": 1980,
         "curvinessScore": 81,
         "path": _make_path(31, {"lat": 48.137, "lng": 11.575}, {"lat": 47.55, "lng": 11.7}, 0.07),
         "samples": _make_samples(33, 187, 44),
         "photos": [{"id": "ph1", "atKm": 88, "caption": "Achenpass summit", "tint": "#2E9CE8"},
                    {"id": "ph2", "atKm": 121, "caption": "Sylvenstein blue", "tint": "#2E6B8C"}]},
        {"id": "ride-2", "title": "Sunday sport run", "date": "Sun 31 Aug \u00b7 09:05",
         "bikeId": "xr", "distanceKm": 226, "durationMin": 232, "avgSpeedKmh": 58,
         "topSpeedKmh": 211, "maxLeanLeftDeg": 51, "maxLeanRightDeg": 48, "ascentM": 1440,
         "curvinessScore": 92,
         "path": _make_path(37, {"lat": 48.1, "lng": 11.4}, {"lat": 47.7, "lng": 12.1}, 0.08),
         "samples": _make_samples(39, 226, 54),
         "photos": [{"id": "ph3", "atKm": 140, "caption": "Kesselberg", "tint": "#E7222E"}]},
        {"id": "ride-3", "title": "Commute \u00b7 Isar", "date": "Fri 29 Aug \u00b7 07:48",
         "bikeId": "ce04", "distanceKm": 21, "durationMin": 38, "avgSpeedKmh": 33,
         "topSpeedKmh": 89, "maxLeanLeftDeg": 22, "maxLeanRightDeg": 19, "ascentM": 80,
         "curvinessScore": 28,
         "path": _make_path(41, {"lat": 48.12, "lng": 11.62}, {"lat": 48.16, "lng": 11.55}, 0.015),
         "samples": _make_samples(43, 21, 24), "photos": []},
    ]


def _seed_group() -> dict:
    return {
        "id": "grp-1", "name": "Saturday Pass Run", "routeId": "r-alpine",
        "startsAt": "Today \u00b7 08:30", "regroupPoint": "Achenpass summit car park",
        "regroupAtKm": 88,
        "riders": [
            {"id": "u1", "name": "Jacob (you)", "bike": "R 1300 GS", "status": "riding",
             "distanceBehindKm": 0, "batteryPercent": 84, "position": {"lat": 47.72, "lng": 11.62}},
            {"id": "u2", "name": "Lena", "bike": "F 900 XR", "status": "riding",
             "distanceBehindKm": 1.2, "batteryPercent": 66, "position": {"lat": 47.735, "lng": 11.605}},
            {"id": "u3", "name": "Timo", "bike": "R 1250 RT", "status": "stopped",
             "distanceBehindKm": 6.4, "batteryPercent": 41, "position": {"lat": 47.78, "lng": 11.58}},
            {"id": "u4", "name": "Marco", "bike": "S 1000 XR", "status": "lost_signal",
             "distanceBehindKm": 12.8, "batteryPercent": 23, "position": {"lat": 47.83, "lng": 11.54}},
        ],
    }


def _seed_regions() -> list[dict]:
    return [
        {"id": "m1", "name": "Germany \u00b7 Bavaria", "sizeMb": 1840, "status": "installed",
         "progress": 100, "updatedAt": "4 Sep 2026"},
        {"id": "m2", "name": "Austria \u00b7 Tyrol", "sizeMb": 720, "status": "downloading",
         "progress": 62, "updatedAt": None},
        {"id": "m3", "name": "Italy \u00b7 South Tyrol", "sizeMb": 910, "status": "failed",
         "progress": 18, "updatedAt": None,
         "error": "Map catalog unreachable - tap to resume, the planner keeps working online"},
        {"id": "m4", "name": "Switzerland", "sizeMb": 1120, "status": "available",
         "progress": 0, "updatedAt": None},
    ]
