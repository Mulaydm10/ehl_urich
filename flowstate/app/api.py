"""
api.py — the thin HTTP wrapper docs 25 §9 / 26 §8 ask for.

One FastAPI process that exposes:
  * the FLOWSTATE fun-fit route engine (service.py), and
  * the BMW-side services the engine never had (bmw_cloud.py: garage, rides,
    group, maps, vehicle status, GPX handoff, live ride recording).

It is the single place the mobile app talks to. On the Mac mini it loads the
real service off data/cache/demo.pkl; anywhere without the bake (CI, a laptop,
the phone-app dev box) it falls back to flowstate_mock so the whole app can be
run and tested live. The BMW services are an in-process mock store either way,
until the real BMW backend is handed over.

Run:
    uvicorn api:app --host 127.0.0.1 --port 8090        # local / this box
    FS_ADDR=100.80.210.100 ./run_api.sh                 # Mac, tailnet only

NDA rules honoured here (doc 25 §9):
  * NaN floats are converted to null before they leave the process.
  * bind to the tailnet address on the Mac, never 0.0.0.0 / funnel (run_api.sh).
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assistant as assistant_mod  # noqa: E402
import bike_link  # noqa: E402
import bmw_cloud  # noqa: E402
import copilot as copilot_mod  # noqa: E402
import via as via_mod  # noqa: E402

# ---- pick the real engine if its data is here, else the mock ---------------
ENGINE: Any
ENGINE_KIND: str
if os.environ.get("FLOWSTATE_MOCK") == "1":
    import flowstate_mock as ENGINE  # type: ignore
    ENGINE_KIND = "mock (forced)"
else:
    try:
        import service as _svc  # type: ignore
        _svc.init()
        ENGINE = _svc
        ENGINE_KIND = "service"
    except Exception as exc:  # noqa: BLE001 - any load failure => usable mock
        # On the demo Mac a mock must never stand in for the real engine: its
        # numbers match doc 25, so a silent fallback would look real on stage.
        if os.environ.get("FLOWSTATE_REQUIRE_REAL") == "1":
            raise
        import flowstate_mock as ENGINE  # type: ignore
        ENGINE_KIND = f"mock (service unavailable: {type(exc).__name__})"

CLOUD = bmw_cloud.BmwCloud()
LINK = bike_link.BikeLink(CLOUD)  # FLOWSTATE_BIKE_LINK=stand_in (default) | native
ASSISTANT = assistant_mod.Assistant(ENGINE, CLOUD, ENGINE_KIND)
COPILOT = copilot_mod.Copilot(ENGINE, CLOUD, ENGINE_KIND)

app = FastAPI(title="FLOWSTATE + BMW backend", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --------------------------------------------------------------------------
# JSON hygiene — NaN/Inf -> null (doc 25 §9)
# --------------------------------------------------------------------------

def _clean(o: Any) -> Any:
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def ok(o: Any) -> JSONResponse:
    return JSONResponse(_clean(o))


# --------------------------------------------------------------------------
# request bodies
# --------------------------------------------------------------------------

class RouteReq(BaseModel):
    a: list[float]
    b: list[float]
    rider_key: str = "userA"
    z_star: float = 0.5
    mode: str = "flow"


class ViaReq(BaseModel):
    """Start, the stops in the rider's own order, and the end."""
    points: list[list[float]]
    rider_key: str = "userA"
    z_star: float = 0.5
    mode: str = "flow"


class LoopReq(BaseModel):
    start: list[float]
    hours: float = 2.0
    rider_key: str = "userA"
    z_star: float = 0.5
    mode: str = "flow"


class CompareReq(BaseModel):
    a: list[float]
    b: list[float]
    rider_key: str = "userA"
    lo: float = 0.15
    hi: float = 0.90
    mode: str = "flow"


class ParetoReq(BaseModel):
    a: list[float]
    b: list[float]
    rider_key: str = "userA"


class PlanReq(BaseModel):
    origin: str
    destination: str
    via: list[str] = []
    mode: str = "curvy"
    avoid: list[str] = []
    roundTrip: bool = False
    bikeId: str = "gs"


class ImportReq(BaseModel):
    fileName: str


class ExportReq(BaseModel):
    routeId: str
    target: str = "connectedride"


class HandoffReq(BaseModel):
    routeId: str
    bikeId: str


class LinkScanReq(BaseModel):
    active: bool = True


class LinkDeviceReq(BaseModel):
    deviceId: str


class LinkSendReq(BaseModel):
    routeId: str
    bikeId: str
    deviceId: str | None = None


class LinkReportReq(BaseModel):
    adapter: dict | None = None
    devices: list[dict] | None = None
    connection: dict | None = None
    transfer: dict | None = None


class LinkDebugReq(BaseModel):
    """Batch of radio events from the phone's BikeLink plugin."""
    session: str | None = None
    events: list[dict] = []


class AssistantReq(BaseModel):
    text: str
    context: dict | None = None


class RealtimeSessionReq(BaseModel):
    context: dict | None = None


class ToolReq(BaseModel):
    name: str
    args: dict | None = None
    # The live ride (position, plan being followed) when the phone has one, so
    # mid-ride tools re-plan from where the bike actually is.
    context: dict | None = None


class CopilotTickReq(BaseModel):
    """One live position report from a ride in progress.

    `route` is the plan the rider is currently following, as the app already
    holds it (path, segments, refusals, destination, remaining_km). It is sent
    with every tick rather than stored server-side so the co-pilot has no
    opinion about which plan is current — the app does.
    """
    session: str = "default"
    lat: float
    lon: float
    speed_kmh: float | None = None
    heading_deg: float | None = None
    rider_key: str = "userA"
    thrill: float = 0.5
    mode: str = "flow"
    bike_id: str | None = None
    route: dict | None = None


class CopilotDismissReq(BaseModel):
    session: str = "default"
    kind: str


class StartRideReq(BaseModel):
    bikeId: str
    title: str = ""


class SampleReq(BaseModel):
    rideId: str
    sample: dict


# --------------------------------------------------------------------------
# meta
# --------------------------------------------------------------------------

@app.get("/health")
def health() -> JSONResponse:
    return ok({"ok": True, "engine": ENGINE_KIND})


@app.get("/api/status")
def status() -> JSONResponse:
    return ok({**ENGINE.status(), "engine": ENGINE_KIND})


# --------------------------------------------------------------------------
# assistant (OpenAI tool calling over this app's own services)
# --------------------------------------------------------------------------

@app.get("/api/assistant/status")
def assistant_status() -> JSONResponse:
    return ok(ASSISTANT.status())


@app.post("/api/assistant")
def assistant_ask(req: AssistantReq) -> JSONResponse:
    res = ASSISTANT.ask(req.text, req.context)
    return JSONResponse(_clean(res), status_code=200 if res.get("ok") else 503)


@app.post("/api/assistant/realtime")
def assistant_realtime(req: RealtimeSessionReq) -> JSONResponse:
    """Short-lived client secret for a speech-to-speech session. The real key
    never leaves this server; the phone talks WebRTC to OpenAI with this."""
    res = ASSISTANT.realtime_session(req.context)
    return JSONResponse(_clean(res), status_code=200 if res.get("ok") else 503)


@app.get("/api/copilot/status")
def copilot_status() -> JSONResponse:
    return ok(COPILOT.status())


@app.post("/api/copilot/tick")
def copilot_tick(req: CopilotTickReq) -> JSONResponse:
    """Live ride watcher: deterministic triggers decide whether there is
    anything to say, OpenAI only phrases it. At most one suggestion."""
    return ok(COPILOT.tick(req.model_dump()))


@app.post("/api/copilot/dismiss")
def copilot_dismiss(req: CopilotDismissReq) -> JSONResponse:
    return ok(COPILOT.dismiss(req.session, req.kind))


@app.post("/api/copilot/reset")
def copilot_reset(req: CopilotDismissReq) -> JSONResponse:
    return ok(COPILOT.reset(req.session))


@app.post("/api/assistant/tool")
def assistant_tool(req: ToolReq) -> JSONResponse:
    """Run one assistant tool. The realtime model's function calls arrive on
    the phone, so they are executed here against the same engine and cloud."""
    res = ASSISTANT.run_tool(req.name, req.args or {}, req.context)
    return JSONResponse(_clean(res), status_code=200)


# --------------------------------------------------------------------------
# FLOWSTATE fun-fit engine
# --------------------------------------------------------------------------

@app.get("/api/riders")
def riders() -> JSONResponse:
    return ok(ENGINE.riders())


@app.get("/api/presets")
def presets() -> JSONResponse:
    return ok(ENGINE.presets())


@app.get("/api/modes")
def modes() -> JSONResponse:
    return ok(ENGINE.modes())


def _engine(call) -> JSONResponse:
    """Run an engine call; a request the engine rejects is the caller's error.

    modes.custom_columns raises ValueError on a spec it will not accept (a
    column the mode scan did not pass, a weight out of range). That is a bad
    request, not a server fault, so answer 400 with the reason instead of a
    bare 500 the app can only show as "something went wrong".
    """
    try:
        return ok(call())
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": "invalid_request", "note": str(exc)},
                            status_code=400)


@app.post("/api/route")
def route(req: RouteReq) -> JSONResponse:
    return _engine(lambda: ENGINE.route(req.a, req.b, req.rider_key, req.z_star, mode=req.mode))


@app.post("/api/route/via")
def route_via(req: ViaReq) -> JSONResponse:
    return _engine(lambda: via_mod.plan_via(ENGINE.route, req.points, req.rider_key,
                                            req.z_star, mode=req.mode))


@app.post("/api/loop")
def loop(req: LoopReq) -> JSONResponse:
    return _engine(lambda: ENGINE.loop(req.start, req.hours, req.rider_key, req.z_star, mode=req.mode))


@app.post("/api/compare")
def compare(req: CompareReq) -> JSONResponse:
    return _engine(lambda: ENGINE.compare(req.a, req.b, req.rider_key, req.lo, req.hi, mode=req.mode))


@app.post("/api/pareto")
def pareto(req: ParetoReq) -> JSONResponse:
    return ok(ENGINE.pareto(req.a, req.b, req.rider_key))


@app.get("/api/basemap")
def basemap() -> JSONResponse:
    return ok(ENGINE.basemap())


@app.get("/api/cells_layer")
def cells_layer(rider_key: str = "userA", z_star: float = 0.5, min_flow: float = 0.0,
                mode: str = "flow") -> JSONResponse:
    return ok(ENGINE.cells_layer(rider_key, z_star, min_flow, mode))


@app.get("/api/rider_joy")
def rider_joy(rider_key: str = "userA") -> JSONResponse:
    return ok(ENGINE.rider_joy(rider_key))


@app.get("/api/gem_pool")
def gem_pool(rider_key: str = "userA", z_star: float = 0.5, n: int = 20,
             mode: str = "flow") -> JSONResponse:
    return ok(ENGINE.gem_pool(rider_key, z_star, n, mode))


# --------------------------------------------------------------------------
# BMW garage / account / vehicle status
# --------------------------------------------------------------------------

@app.get("/api/bmw/profile")
def bmw_profile() -> JSONResponse:
    return ok(CLOUD.get_profile())


@app.get("/api/bmw/bikes")
def bmw_bikes() -> JSONResponse:
    return ok(CLOUD.get_bikes())


@app.get("/api/bmw/bikes/{bike_id}/status")
def bmw_vehicle_status(bike_id: str) -> JSONResponse:
    return ok(CLOUD.vehicle_status(bike_id))


@app.get("/api/bmw/stats")
def bmw_stats() -> JSONResponse:
    return ok(CLOUD.get_stats())


# --------------------------------------------------------------------------
# BMW routes / cloud sync / handoff
# --------------------------------------------------------------------------

@app.get("/api/bmw/routes")
def bmw_routes() -> JSONResponse:
    return ok(CLOUD.get_routes())


@app.post("/api/bmw/plan")
def bmw_plan(req: PlanReq) -> JSONResponse:
    return ok(CLOUD.plan_route(req.model_dump()))


@app.post("/api/bmw/import")
def bmw_import(req: ImportReq) -> JSONResponse:
    return ok(CLOUD.import_route(req.fileName))


@app.post("/api/bmw/export")
def bmw_export(req: ExportReq) -> JSONResponse:
    return ok(CLOUD.export_route(req.routeId, req.target))


@app.post("/api/bmw/handoff")
def bmw_handoff(req: HandoffReq) -> JSONResponse:
    return ok(CLOUD.handoff(req.routeId, req.bikeId))


# --------------------------------------------------------------------------
# BMW local bike link (Bluetooth / TFT) — bike_link.py
# --------------------------------------------------------------------------

@app.get("/api/bmw/link/status")
def bmw_link_status() -> JSONResponse:
    return ok(LINK.status())


@app.get("/api/bmw/link/adapter")
def bmw_link_adapter() -> JSONResponse:
    return ok(LINK.transport.adapter())


@app.get("/api/bmw/link/devices")
def bmw_link_devices() -> JSONResponse:
    return ok(LINK.transport.devices())


@app.post("/api/bmw/link/scan")
def bmw_link_scan(req: LinkScanReq) -> JSONResponse:
    return ok(LINK.transport.scan(req.active))


@app.post("/api/bmw/link/pair")
def bmw_link_pair(req: LinkDeviceReq) -> JSONResponse:
    return ok(LINK.transport.pair(req.deviceId))


@app.post("/api/bmw/link/unpair")
def bmw_link_unpair(req: LinkDeviceReq) -> JSONResponse:
    return ok(LINK.transport.unpair(req.deviceId))


@app.post("/api/bmw/link/connect")
def bmw_link_connect(req: LinkDeviceReq) -> JSONResponse:
    return ok(LINK.transport.connect(req.deviceId))


@app.post("/api/bmw/link/disconnect")
def bmw_link_disconnect() -> JSONResponse:
    return ok(LINK.transport.disconnect())


@app.get("/api/bmw/link/capabilities/{bike_id}")
def bmw_link_capabilities(bike_id: str) -> JSONResponse:
    return ok(LINK.capabilities(bike_id))


@app.post("/api/bmw/link/send")
def bmw_link_send(req: LinkSendReq) -> JSONResponse:
    return ok(LINK.send(req.routeId, req.bikeId, req.deviceId))


@app.get("/api/bmw/link/transfers/{transfer_id}")
def bmw_link_transfer(transfer_id: str) -> JSONResponse:
    return ok(LINK.transport.transfer(transfer_id))


@app.get("/api/bmw/link/gpx/{route_id}")
def bmw_link_gpx(route_id: str) -> Response:
    gpx = LINK.gpx(route_id)
    if gpx is None:
        return JSONResponse({"ok": False, "note": f"No route {route_id}."}, status_code=404)
    return Response(gpx, media_type="application/gpx+xml")


@app.post("/api/bmw/link/native/report")
def bmw_link_native_report(req: LinkReportReq) -> JSONResponse:
    return ok(LINK.report(req.model_dump(exclude_none=True)))


# Live debug trail. The phone posts what its radio did; the app's log panel and
# anyone on the tailnet (`curl .../link/debug?since=N`) read it back, so a test
# ride next to the bike can be watched from the Mac in real time.

@app.post("/api/bmw/link/debug")
def bmw_link_debug_post(req: LinkDebugReq) -> JSONResponse:
    return ok(LINK.trail.ingest(req.events, req.session))


@app.get("/api/bmw/link/debug")
def bmw_link_debug_get(since: int = 0, limit: int = 500) -> JSONResponse:
    return ok(LINK.trail.since(since, max(1, min(limit, 2000))))


@app.post("/api/bmw/link/debug/clear")
def bmw_link_debug_clear() -> JSONResponse:
    return ok(LINK.trail.clear())


@app.get("/api/bmw/link/telemetry")
def bmw_link_telemetry() -> JSONResponse:
    """Latest mySPIN vehicle-data per key + granted/denied keys the phone saw."""
    return ok(LINK.trail.telemetry())


# --------------------------------------------------------------------------
# BMW rides + live recording
# --------------------------------------------------------------------------

@app.get("/api/bmw/rides")
def bmw_rides() -> JSONResponse:
    return ok(CLOUD.get_rides())


@app.post("/api/bmw/rides/start")
def bmw_ride_start(req: StartRideReq) -> JSONResponse:
    return ok(CLOUD.start_recording(req.bikeId, req.title))


@app.post("/api/bmw/rides/sample")
def bmw_ride_sample(req: SampleReq) -> JSONResponse:
    return ok(CLOUD.push_sample(req.rideId, req.sample))


@app.post("/api/bmw/rides/{ride_id}/stop")
def bmw_ride_stop(ride_id: str) -> JSONResponse:
    return ok(CLOUD.stop_recording(ride_id))


# --------------------------------------------------------------------------
# BMW group ride + offline maps
# --------------------------------------------------------------------------

@app.get("/api/bmw/group")
def bmw_group() -> JSONResponse:
    return ok(CLOUD.get_group())


@app.get("/api/bmw/maps")
def bmw_maps() -> JSONResponse:
    return ok(CLOUD.get_regions())


@app.post("/api/bmw/maps/{region_id}/download")
def bmw_map_download(region_id: str) -> JSONResponse:
    return ok(CLOUD.start_download(region_id))
