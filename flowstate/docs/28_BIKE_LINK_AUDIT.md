# 28 — Bike link: audit against the shipped BMW app, and live debugging

Doc 27 describes what we built. This one records what the **real BMW Motorrad
Connected app** does on the radio (read out of the shipped APK), how our link
differs, and how to watch a real test next to the bike.

Nothing here was captured from a bike. Every line is either "decompiled from
the APK" (fact about their code) or "unverified" (needs hardware).

## 1. What the shipped app actually does

Decompiled with jadx from the Play APK (`com.bmw.motorrad.connected`).

| Area | Evidence in the APK | Reading |
| --- | --- | --- |
| Head-unit transport | `createRfcommSocketToServiceRecord(UUID…)` in `com.bmw.connride.connectivity.bluetooth` | The head unit (ICC) is driven over **Bluetooth Classic / RFCOMM**, not BLE GATT |
| Alternative channel | `createL2capChannel(22)` / `createInsecureL2capChannel(22)` | An L2CAP channel on PSM 22 exists as a second path |
| Device discovery | `adapter.getBondedDevices()`, profile proxy | It looks at **bonded** devices; it does not BLE-scan for the head unit |
| Device recognition | names starting `ICC` / `BMW Motorrad`, `"BMW Motorrad " + takeLast(str, 5)` | Name-prefix match, plus SDP UUIDs below |
| SDP service IDs | `c707050e-efae-1449-3913-c191e5bb32dc`, `a96f9e76-ab2e-869c-40e3-1da0c086a07a`, `dc32bbe5-91c1-1339-4914-aeef0e0507c7` | RFCOMM service records. **Not** GATT route-transfer UUIDs |
| Projection | `com.bmw.connride.mona.myspin.*` (`MySpinICEService`, `MySpinICEConnectionUseCase`), `MonaWifiService` | Bosch **mySPIN** projection, over Bluetooth and Wi-Fi |
| RPC | ZeroC **Ice** proxies (`MySpinICE_AppPrxHelper`, `MySpinICE_VehiclePrxHelper`), endpoints built as `"bt -u " + uuid` / `… -a "<adapter>"` | Ice runs *over* the Bluetooth endpoint; the app speaks Ice RPC, not a raw byte protocol |
| Navigation handoff | `setDestinationInformation` on the navigation proxy | The route is handed over as an **Ice call**, not as a GPX blob |
| BLE | `com.bmw.connride.lib.bluetooth`, `…lib.bledataexchange` | BLE exists, used for accessories / ConnectedRide Control — not proven to be the route path |

**Conclusion:** a route reaches the TFT through mySPIN + Ice over RFCOMM (or
Wi-Fi), addressed by `setDestinationInformation`. Writing GPX bytes to a GATT
characteristic is a *different* mechanism and there is no evidence a BMW head
unit accepts it.

## 2. What our link does today, and the gap

| | Shipped BMW app | RideFit today |
| --- | --- | --- |
| Transport | RFCOMM (+ L2CAP, Wi-Fi) | BLE GATT (`connectGatt`, `TRANSPORT_LE`) |
| Discovery | bonded devices | BLE scan — **now also** `listBondedDevices()` |
| Payload | Ice `setDestinationInformation` | raw GPX in MTU-sized chunks |
| Framing | Ice marshalling | none |
| Pairing | system bond | system bond (we never pair in-app) |

The gap is deliberate and guarded: `ROUTE_GATT` in
`app/src/services/bikeLink.ts` is `null`, and `sendRoute` rejects with
`PROTOCOL_UNVERIFIED` unless the caller passes a service + characteristic UUID
that the connected device actually exposes. Nothing is ever reported as sent
unless the device acknowledged every chunk.

Closing the gap properly means an Ice/mySPIN client, which needs the mySPIN SDK
or a capture from a real bike — out of scope until one of the two exists.

## 3. Live debugging

Every radio operation now produces a structured event: `seq`, `at`, `op`,
`level`, `source`, `session`, plus op-specific fields. Device addresses are
redacted in event fields (`aa:bb:cc:…:FF`).

Ops emitted by the phone: `plugin.load`, `permission.request|result|already`,
`scan.start|result|stop|failed`, `bonded.list`, `icc.probe.start|ok|failed`,
`gatt.connect|disconnect|connectionStateChange|requestMtu|mtuChanged`,
`gatt.discoverServices.start|servicesDiscovered`, `gatt.write`, `gatt.write.ack`,
`transfer.requested|refused|start|acknowledged|failed`, `connection.state`.
`gatt.servicesDiscovered` carries the full service tree: service UUIDs and
types, characteristic UUIDs, instance IDs, property names, property/permission
masks and descriptor UUIDs — i.e. exactly what is needed to find the real route
characteristic if one exists.

Three places to watch it:

1. **In the app** — Bike link → *Radio log* (newest last, "Problems only"
   filter, *Copy log*).
2. **logcat** — `adb logcat -s BikeLink:D`.
3. **Backend trail** — the phone batches its events to
   `POST /api/bmw/link/debug`; anyone on the tailnet polls

   ```bash
   curl -s "http://100.80.210.100:8090/api/bmw/link/debug?since=0" | jq
   curl -s -X POST "http://100.80.210.100:8090/api/bmw/link/debug/clear"
   ```

   The trail is bounded (4000 events) and reports `dropped`. It is a record
   only: an event never changes connection or transfer state.

## 4. Procedure at the bike (phone only — the emulator has no radio)

1. Pair the head unit in Android Bluetooth settings first (the BMW app relies
   on a bond; we never pair in-app).
2. App → Bike link → **List paired devices**. A device tagged
   *BMW head unit?* means the name prefix or an SDP UUID matched.
3. **Probe RFCOMM** on that device. It opens and immediately closes an RFCOMM
   socket to `c707050e-…` and reports whether the socket was accepted. It
   speaks no protocol and sends no route. A success proves the channel exists;
   it proves nothing about the payload.
4. **Scan for bike** to see what the bike advertises over BLE, then connect and
   read `gatt.servicesDiscovered` in the log for the full GATT tree.
5. Try a handoff. Expect `transfer.refused reason=PROTOCOL_UNVERIFIED` until a
   route characteristic is actually identified — that refusal is the correct
   result today, not a bug.
6. Copy the log (or pull the backend trail) and attach it to the issue.

## 5. Still unverified

- whether the bike accepts an RFCOMM connection from our app at all;
- the Ice/mySPIN handshake and the `setDestinationInformation` payload;
- whether any GATT characteristic accepts a route;
- pairing/bonding behaviour with a real ICC;
- everything about the TFT display side.
