"""
router.py — Phase 2. Turn the cell table + edge table into routes that are
chosen for FIT, not for speed.

The whole argument in one line: an edge does not cost metres, it costs
metres inflated by how badly the destination cell fits this rider at this
dial setting.

    cost = length_m * (1 + LAMBDA * (1 - flow_of_destination_cell))

Never 1/flow. A zero-flow cell would make that infinite and Dijkstra would
quietly return "unreachable" instead of "expensive", which on stage looks
like a crash rather than an opinion.

Two layers, kept apart on purpose:

  soft  — a cell that fits badly is expensive. The router will still use it
          to get you somewhere, it just resents it.
  hard  — a cell whose demand exceeds skill + 2 sigma is REFUSED. The edge
          is removed from the graph, not made expensive. That is the safety
          criterion, and a safety gate you can buy your way past with a big
          enough detour budget is not a safety gate.

Every refusal is recorded with a reason so the UI can say out loud which
road it would not send this rider down, and why.

Inputs (built by analysis/10 and analysis/11):
    analysis/out/crowd_grid_s2.parquet    26,987 cells
    analysis/out/graph_edges_s2.parquet   38,351 directed edges, 21,130 nodes

Reads morton codes as TEXT, always. They are base-4 strings; as ints they
lose their leading digits and the whole spatial index collapses.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

G = 9.80665
TAU_DEFAULT = 0.5
GATE_SIGMAS = 2.0
LAMBDA_DEFAULT = 10.0       # calibrated in analysis/12_route_calibration.py.
                            # 10 is the smallest value at which the routing
                            # has saturated: cost = L*(1 + lam*(1-flow)) tends
                            # to lam*L*(1-flow) as lam grows, so beyond the
                            # ceiling the ranking of paths cannot change and
                            # lam=20, 40, 80 return the identical route.
MU_DEFAULT = 1.1            # sport-touring tyre on dry tarmac, 1.0-1.2

# how hard the soft penalties bite. Both are plan values.
STOP_PENALTY = 0.50         # a cell where traversals stop is not flow
UNFLOW_PENALTY = 0.30       # ... nor is one nobody gets through cleanly

# peak-end aggregation
W_MEAN, W_PEAK, W_FINAL = 0.35, 0.40, 0.25
PEAK_WINDOW_M = 5000.0      # "the best five kilometres of the ride"
FINAL_SHARE = 0.15          # the last 15% is what you remember
LOW_FLOW = 0.20             # below this a cell counts toward the dull tail
TAIL_PENALTY = 0.50         # at most halve the score for an all-dull route

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FS_OUT", ROOT / "analysis" / "out"))
# The router runs on the 16-CHARACTER grid, not the 18-character one the
# rest of the app uses. This is a deliberate split and the reason is in
# analysis/12_route_calibration.py: at 18 chars (153 x 102 m) the ride-derived
# graph has exactly ONE corridor between any two points — delete the shortest
# path's edges and A and B become disconnected — so no cost function of any
# shape can route around anything. At 16 chars (~600 x 400 m) parallel roads
# share a node, real alternatives appear, and an edge-disjoint second path
# exists at 1.35-1.38x the direct distance.
# Scoring, the map and the corner work stay at 18. Only topology moves.
TAG = os.environ.get("FS_TAG", "_c16")

# BMW's coverage box. Outside it we have no crowd, so we have no opinion.
COVERAGE = (47.38, 48.03, 10.72, 11.96)


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def _haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    R = 6371008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


# --------------------------------------------------------------------------
# rider
# --------------------------------------------------------------------------

@dataclass
class Rider:
    """
    The two numbers the router needs. Both in degrees of lean.

    skill  — what this rider actually uses (lean p95 from their own corners)
    sigma  — how much they vary (sd of lean)

    Accepts a flowstate.RiderDNA via `from_dna` so the app has one source of
    truth for the rider and this module never re-derives a skill number.
    """
    label: str
    skill: float
    sigma: float

    @property
    def gate(self) -> float:
        """Demand above this is refused outright."""
        return self.skill + GATE_SIGMAS * self.sigma

    n_cells: int = 0
    skill_corner: float = float("nan")     # kept for display, NOT for routing
    crowd_skill: float = float("nan")      # the same statistic for everyone
    hardest_ridden: float = float("nan")   # p95 of their ridden cells

    @property
    def gate_agreement(self) -> float:
        """gate / hardest road actually ridden. Near 1.0 validates the gate."""
        return self.gate / self.hardest_ridden if self.hardest_ridden else float("nan")

    @classmethod
    def from_dna(cls, dna) -> "Rider":
        """
        Corner-axis rider. Correct for scoring individual corners, WRONG for
        scoring cells — see calibrate_rider. Kept so the app can still show
        the familiar "you lean 30 degrees" number.
        """
        return cls(label=getattr(dna, "label", "rider"),
                   skill=float(getattr(dna, "skill_all", getattr(dna, "skill", 25.0))),
                   sigma=float(getattr(dna, "sigma", 7.5)))


def calibrate_rider(corners: pd.DataFrame, cells: pd.DataFrame,
                    label: str = "rider", q: float = 50.0) -> Rider:
    """
    Put skill and challenge on THE SAME AXIS. This is the whole reason the
    first version of this router scored every road in Bavaria at flow 0.

    A rider's skill from `flowstate.rider_dna` is peak lean *per corner*:
    p95 = 30.2 deg for user A. A cell's `demand_p90` is the 90th percentile
    over *every sample in a 153 m cell*, straights included: median 7.4 deg.
    Those are different statistics of the same physical quantity, and
    subtracting one from the other gives z = -3 everywhere — the model
    says "nothing in Bavaria could possibly interest you", which is an
    artefact of aggregation, not a fact about the rider.

    So measure the rider with the crowd's own ruler: take the cells this
    rider actually rode, and read their skill off the same `demand_p90`
    column the challenge comes from.

        skill = MEDIAN demand_p90 over the cells they rode
        sigma = sd of the same

    Why the median and not p95. `z = (challenge - skill) / sigma` is a
    stretch measured from where the rider normally lives, and z* = 0 has to
    mean "exactly the road I habitually ride". Skill therefore has to be the
    habitual road, not the hardest one. Taking p95 puts the rider at the 99th
    percentile of every road in Bavaria, nothing fits, flow collapses to zero
    network-wide, and the dial stops doing anything.

    The demonstrated maximum is not thrown away — it lands on the gate
    instead, and the two agree without being made to:

        median + 2 sigma      = 14.68 + 12.62 = 27.30 deg   <- the gate
        p95 of ridden cells   =                 26.62 deg   <- hardest road
                                                               actually ridden

    A safety threshold derived from the spread of this rider's road choices
    lands within 3% of the hardest road this rider has ever chosen. Nothing
    in the construction forces that; it is a property of the data, and it is
    the best evidence we have that the gate is set at a real place.

    For reference the crowd-wide p95 across all 27k cells is 21.7 deg, so
    user A's hardest roads sit well above the average road in the dataset.

    Falls back to the corner axis, loudly, if the overlap is too thin.
    """
    idx = cells.set_index("morton_code")
    chars = len(str(idx.index[0]))
    ridden = corners["morton"].astype(str).str.slice(0, chars)
    ridden = ridden[ridden.isin(idx.index)].unique()

    d = idx.loc[ridden, "demand_p90"].dropna() if len(ridden) else pd.Series(dtype=float)
    crowd = float(np.nanpercentile(idx["demand_p90"], 95))

    if len(d) < 50:
        return Rider(label=f"{label} (uncalibrated — only {len(d)} shared cells)",
                     skill=crowd, sigma=float(np.nanstd(idx["demand_p90"])),
                     n_cells=int(len(d)), crowd_skill=crowd)

    return Rider(label=label,
                 skill=float(np.percentile(d, q)),
                 sigma=float(d.std()),
                 n_cells=int(len(d)),
                 hardest_ridden=float(np.percentile(d, 95)),
                 skill_corner=float(np.nanpercentile(corners["lean_deg"].dropna(), 95)),
                 crowd_skill=crowd)


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_cells(tag: str = TAG) -> pd.DataFrame:
    c = pd.read_parquet(OUT / f"crowd_grid{tag}.parquet")
    c["morton_code"] = c["morton_code"].astype(str)     # TEXT. always.
    return c


def load_edges(tag: str = TAG, symmetrise: bool = True) -> pd.DataFrame:
    e = pd.read_parquet(OUT / f"graph_edges{tag}.parquet")
    e["ci"] = e["ci"].astype(str)
    e["cj"] = e["cj"].astype(str)
    return symmetrise_edges(e) if symmetrise else e


def load_osm(tag: str = TAG) -> pd.DataFrame | None:
    """OSM attributes joined per cell by analysis/13_osm_layer.py. Optional."""
    f = OUT / f"osm_cells{tag}.parquet"
    if not f.exists():
        return None
    o = pd.read_parquet(f)
    o["morton_code"] = o["morton_code"].astype(str)
    return o.set_index("morton_code")


def apply_legal_speed(cells: pd.DataFrame, osm: pd.DataFrame | None,
                      tol: float = 1.10) -> pd.DataFrame:
    """
    Recompute road demand at the POSTED LIMIT instead of at the speed the
    crowd actually used.

    This is the honest fix, and it is better than refusing the road. Our
    challenge number is a lean angle, theta = arctan(v^2 / (R g)). If the
    crowd's p85 speed on a cell is 120 km/h in an 80 zone, then the lean we
    are promising is only reachable by breaking the law — so the model would
    be selling a thrill that no law-abiding rider can have. Refusing the road
    would be crude; the road may be excellent at 80. Instead, re-price it at
    80 and let it compete on what it legally offers.

    Since tan(theta) is proportional to v^2 at fixed radius:

        tan(theta_legal) = tan(theta_crowd) * (v_limit / v_p85)^2

    Only applied where a limit is known AND the crowd exceeds it by more than
    `tol` (10%, which absorbs GPS speed error). A German autobahn with no
    posted limit parses to NaN and is left alone — its road class carries the
    meaning instead.

    Returns a copy with `demand_p90` corrected and two new columns:
    `demand_capped` (bool) and `demand_before_cap`.
    """
    c = cells.copy()
    c["demand_capped"] = False
    c["demand_before_cap"] = c["demand_p90"]
    if osm is None or "osm_maxspeed_kmh" not in getattr(osm, "columns", []):
        return c

    lim = osm["osm_maxspeed_kmh"].reindex(c["morton_code"]).to_numpy(dtype=float)
    v85 = c["crowd_v_p85"].to_numpy(dtype=float) * 3.6          # m/s -> km/h
    dem = c["demand_p90"].to_numpy(dtype=float)

    hit = np.isfinite(lim) & np.isfinite(v85) & np.isfinite(dem) & (v85 > lim * tol)
    ratio = np.where(hit, np.clip(lim / np.where(v85 > 0, v85, np.nan), 0.0, 1.0), 1.0)
    legal = np.degrees(np.arctan(np.tan(np.radians(dem)) * ratio ** 2))

    c["demand_p90"] = np.where(hit, legal, dem)
    c["demand_capped"] = hit
    return c


def mu_for_temp(temp_c, mu0: float = MU_DEFAULT, t_full: float = 20.0,
                t_cold: float = 5.0, floor: float = 0.75):
    """
    Available grip falls on cold tarmac. Returns a temperature-derated mu.

    HONESTY WARNING, and it must survive into the UI: this curve is an
    engineering assumption from tyre behaviour, NOT something we measured
    here. We tested it on BMW's own data and it did not replicate: across
    5,253 corners spearman(lean, temp) = -0.016, and per-trip the lean/demand
    ratio against temperature is rho = +0.22 at p = 0.24 over 29 trips. The
    direction is right and the magnitude is undetectable at this sample size.

    So this feeds the SAFETY readout only — grip headroom — and never the fun
    score. The measured core of the model stays measured.
    """
    t = np.asarray(temp_c, dtype=float)
    f = np.clip((t - t_cold) / (t_full - t_cold), 0.0, 1.0)
    return mu0 * (floor + (1.0 - floor) * f)


def symmetrise_edges(e: pd.DataFrame) -> pd.DataFrame:
    """
    graph_edges is directed because it is built from ride direction: an edge
    exists i->j only because somebody rode i then j. A road that the sample
    only ever caught northbound therefore has no southbound edge.

    That is a fact about the sample, not about the road. Riding it the other
    way is legal, and pretending otherwise cost us most of the network's
    routing freedom: 2,022 independent loops exist in the undirected graph,
    but directed they are largely untraversable, so Dijkstra had exactly one
    candidate path between any two points and the Thrill Dial changed nothing.

    So add the reverse of every edge. The evidence carried on an edge —
    n_transitions, median speed, the radius and demand of both cells —
    describes the ROAD, and survives the reversal. The one quantity that does
    not is `surprise = log(R_i / R_j)`: tightening one way is opening up the
    other, so its sign flips.

    One-way streets do get reversed by this. In the mountains outside a town
    centre that is rare, and the cost of the alternative — a router that
    cannot detour at all — is certain rather than rare.
    """
    rev = e.rename(columns={"ci": "cj", "cj": "ci",
                            "radius_i": "radius_j", "radius_j": "radius_i",
                            "demand_i": "demand_j", "demand_j": "demand_i"})
    if "surprise" in rev.columns:
        rev["surprise"] = -rev["surprise"]
    out = pd.concat([e, rev[e.columns]], ignore_index=True)
    return out.drop_duplicates(["ci", "cj"], keep="first").reset_index(drop=True)


# --------------------------------------------------------------------------
# the flow score, over every cell at once
# --------------------------------------------------------------------------

def score_cells(cells: pd.DataFrame, rider: Rider, z_star: float,
                tau: float = TAU_DEFAULT,
                gate_sigmas: float = GATE_SIGMAS,
                osm: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    One NumPy pass over all 27k rows. No loops, no apply, no iterrows —
    the dial moves in the UI and this has to re-run between two frames.

    Returns a frame indexed by cell with z, flow, gated and a reason string.
    """
    n = len(cells)
    demand = cells["demand_p90"].to_numpy(dtype=float)

    # ~1.5% of cells carry no corner at all: the crowd rode them, nobody
    # leaned. That is a straight, not a missing value. Impute at the low
    # end of the observed distribution rather than dropping the cell —
    # dropping would tear holes in a graph whose whole value is connectivity.
    missing = ~np.isfinite(demand)
    fill = float(np.nanpercentile(demand, 10)) if np.isfinite(demand).any() else 0.0
    demand = np.where(missing, fill, demand)

    sigma = max(float(rider.sigma), 1e-6)
    skill = float(rider.skill)

    z = (demand - skill) / sigma
    flow = np.exp(-((z - float(z_star)) ** 2) / (2.0 * float(tau) ** 2))

    # --- hard gate: a refusal, not a penalty -----------------------------
    gate = skill + gate_sigmas * sigma
    gated = demand > gate
    flow = np.where(gated, 0.0, flow)

    # --- soft penalties --------------------------------------------------
    stop = np.clip(cells["stop_rate"].to_numpy(dtype=float), 0.0, 1.0)
    stop = np.nan_to_num(stop, nan=0.0)

    # the plan asks for dwell_share; the cell table does not carry one. The
    # honest stand-in is the complement of flow_index — the share of
    # traversals that did NOT get through cleanly at speed. It folds dwell
    # and crawling together, which is the behaviour we wanted to punish.
    unflow = 1.0 - np.clip(cells["flow_index"].to_numpy(dtype=float), 0.0, 1.0)
    unflow = np.nan_to_num(unflow, nan=0.0)

    flow = flow * (1.0 - STOP_PENALTY * stop)
    flow = flow * (1.0 - UNFLOW_PENALTY * np.minimum(1.0, unflow))
    flow = np.clip(flow, 0.0, 1.0)

    # --- reasons, vectorised ---------------------------------------------
    reason = np.full(n, "", dtype=object)
    reason = np.where(
        gated,
        np.array([f"REFUSED — the crowd leans {d:.0f}° here, past your gate of "
                  f"{gate:.0f}° ({skill:.0f}° + 2σ)" for d in demand], dtype=object),
        reason)
    soft = (~gated) & (stop > 0.25)
    reason = np.where(
        soft,
        np.array([f"avoided — {s:.0%} of rides stop in this cell" for s in stop],
                 dtype=object),
        reason)

    # --- BMW's own RED flags, now facts rather than inferences -----------
    # Until OSM landed we guessed at these from telemetry. A motorway and a
    # fast country road look similar in a lean channel; gravel and tarmac
    # look identical. These are tags, not guesses.
    red_reason = np.full(n, "", dtype=object)
    if osm is not None:
        idx = cells["morton_code"]
        for col, mult, why in (
                ("red_fast_boring", 0.45, "motorway or trunk road — fast, straight, BMW RED"),
                ("red_inner_city", 0.45, "residential street — inner city and standstills, BMW RED"),
                ("red_bad_surface", 0.55, "unpaved or cobbled surface, BMW RED")):
            if col not in osm.columns:
                continue
            m = osm[col].reindex(idx).fillna(False).to_numpy(dtype=bool)
            flow = np.where(m, flow * mult, flow)
            red_reason = np.where(m & (red_reason == ""), why, red_reason)
    flow = np.clip(flow, 0.0, 1.0)

    return pd.DataFrame({
        "cell": cells["morton_code"].to_numpy(),
        "lat": cells["lat"].to_numpy(dtype=float),
        "lon": cells["lon"].to_numpy(dtype=float),
        "demand": demand,
        "demand_imputed": missing,
        "z": z,
        "flow": flow,
        "gated": gated,
        "stop_rate": stop,
        "reason": np.where(reason == "", red_reason, reason),
        "demand_capped": (cells["demand_capped"].to_numpy(dtype=bool)
                          if "demand_capped" in cells.columns
                          else np.zeros(n, dtype=bool)),
    }).set_index("cell")


# --------------------------------------------------------------------------
# the graph
# --------------------------------------------------------------------------

@dataclass
class Graph:
    """
    The plan's signature is `build_graph(...) -> csr_matrix`. We return the
    matrix wrapped with its node index, because a bare csr cannot be mapped
    back to cell ids and the caller would only have to rebuild that index.
    `graph.matrix` is the csr_matrix the plan asks for.
    """
    matrix: csr_matrix
    nodes: np.ndarray                 # index -> cell id (str)
    index: dict                       # cell id -> index
    scored: pd.DataFrame              # the score_cells output
    edges: pd.DataFrame               # the surviving edges, with cost
    refused: pd.DataFrame             # edges dropped by the hard gate
    z_star: float = 0.0
    lam: float = LAMBDA_DEFAULT
    rider: Rider | None = None

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)


def build_graph(edges: pd.DataFrame, cells: pd.DataFrame, rider: Rider,
                z_star: float, tau: float = TAU_DEFAULT,
                lam: float = LAMBDA_DEFAULT,
                hard_gate: bool = True,
                osm: pd.DataFrame | None = None) -> Graph:
    """
    Cost an edge by how well its DESTINATION cell fits the rider.

        cost = length_m * (1 + lam * (1 - flow_j))

    lam is the detour budget: at lam=8 the router will ride 9 m of perfect
    road rather than 1 m of road that fits this rider not at all.

    hard_gate=True drops every edge whose destination is refused. Set it
    False only for the unreachable fallback, and say so in the UI.
    """
    scored = score_cells(cells, rider, z_star, tau=tau, osm=osm)

    nodes = np.array(sorted(set(edges["ci"]) | set(edges["cj"])), dtype=object)
    index = {c: i for i, c in enumerate(nodes)}

    e = edges.copy()
    e["i"] = e["ci"].map(index).to_numpy()
    e["j"] = e["cj"].map(index).to_numpy()

    # a cell can be an edge endpoint and still be absent from the cell table
    # (it never accumulated enough points). Treat it as unknown, not as fun:
    # flow 0, ungated — expensive but passable.
    flow_j = scored["flow"].reindex(e["cj"]).to_numpy(dtype=float)
    gated_j = scored["gated"].reindex(e["cj"]).fillna(False).to_numpy(dtype=bool)
    unknown = ~np.isfinite(flow_j)
    flow_j = np.where(unknown, 0.0, flow_j)

    # --- edge length: centre to centre, NOT the edge table's median_metres --
    # `median_metres` in graph_edges is the distance between the last sample
    # before the boundary and the first sample after it — two samples one
    # second apart, so ~21 m at 75 km/h. It is a boundary-crossing step, not
    # the length of the edge. Summing it gave 10 km for a route whose
    # endpoints are 43 km apart. A cell is ~153 x 102 m; the honest length of
    # a cell-to-cell edge is the distance between the two cell centres.
    ll = cells.set_index("morton_code")[["lat", "lon"]]
    pi = ll.reindex(e["ci"]).to_numpy(dtype=float)
    pj = ll.reindex(e["cj"]).to_numpy(dtype=float)
    length = _haversine_m(pi[:, 0], pi[:, 1], pj[:, 0], pj[:, 1])
    # an endpoint missing from the cell table has no centre: fall back to the
    # measured boundary step rather than dropping the edge.
    fallback = e["median_metres"].to_numpy(dtype=float)
    length = np.where(np.isfinite(length) & (length > 0.0), length, fallback)
    length = np.where(np.isfinite(length) & (length > 0.0), length, 1.0)
    e["length_m"] = length

    # time follows from length and the speed actually measured on the
    # transition — median_seconds is the same boundary artefact as
    # median_metres and is always ~1 s.
    v = e["median_speed"].to_numpy(dtype=float)
    v = np.where(np.isfinite(v) & (v > 2.0), v, 8.0)      # 2 m/s floor
    e["seconds"] = length / v
    e["flow_j"] = flow_j
    e["gated_j"] = gated_j
    e["cost"] = length * (1.0 + float(lam) * (1.0 - flow_j))

    if hard_gate:
        refused = e.loc[gated_j].copy()
        keep = e.loc[~gated_j].copy()
    else:
        refused = e.iloc[0:0].copy()
        keep = e

    m = csr_matrix(
        (keep["cost"].to_numpy(dtype=float),
         (keep["i"].to_numpy(dtype=np.int64), keep["j"].to_numpy(dtype=np.int64))),
        shape=(len(nodes), len(nodes)),
    )

    return Graph(matrix=m, nodes=nodes, index=index, scored=scored,
                 edges=keep, refused=refused, z_star=float(z_star),
                 lam=float(lam), rider=rider)


# --------------------------------------------------------------------------
# snapping
# --------------------------------------------------------------------------

def snap(lat: float, lon: float, cells: pd.DataFrame,
         nodes: np.ndarray | None = None) -> str:
    """
    Nearest cell centre. Equirectangular is exact enough over a 70 km box
    and ~30x faster than haversine on 27k rows.

    Pass `nodes` to snap only to cells that are actually in the graph —
    otherwise a click can land on an isolated cell and the route fails for
    a reason that has nothing to do with the rider.
    """
    c = cells
    if nodes is not None:
        c = c[c["morton_code"].isin(set(nodes))]
    if not len(c):
        raise ValueError("no candidate cells to snap to")

    la = c["lat"].to_numpy(dtype=float)
    lo = c["lon"].to_numpy(dtype=float)
    k = np.cos(np.radians(float(lat)))
    d2 = (la - float(lat)) ** 2 + ((lo - float(lon)) * k) ** 2
    return str(c["morton_code"].to_numpy()[int(np.argmin(d2))])


def in_coverage(lat: float, lon: float) -> bool:
    lo_la, hi_la, lo_lo, hi_lo = COVERAGE
    return (lo_la <= lat <= hi_la) and (lo_lo <= lon <= hi_lo)


# --------------------------------------------------------------------------
# the friction circle
# --------------------------------------------------------------------------

def grip_used(lean_deg, a_long_g, mu: float = MU_DEFAULT):
    """
    Share of available grip in use, lateral and longitudinal together.

        grip = sqrt(tan(theta)^2 + (a_long/g)^2) / mu

    a_long arrives ALREADY IN g (verified on this data: the truth is
    bracketed in [5.52, 10.15] against dv/dt, which contains 9.81 and
    excludes 1.0 by a mile). So it goes straight into the formula — do not
    divide by 9.81 a second time.
    """
    lat = np.tan(np.radians(np.asarray(lean_deg, dtype=float)))
    lon = np.asarray(a_long_g, dtype=float)
    return np.sqrt(lat ** 2 + np.nan_to_num(lon) ** 2) / float(mu)


def rider_grip_p95(corners: pd.DataFrame, mu: float = MU_DEFAULT,
                   clip_g: float = 1.0) -> float:
    """
    The rider's own p95 grip utilisation across their corners. Uses the
    larger-magnitude of a_min/a_max per corner, clipped — a handful of
    corner-level accel extremes are sensor artefacts, not physics
    (a motorcycle does not brake at 2.6 g).
    """
    if not {"lean_deg", "a_min", "a_max"} <= set(corners.columns):
        return float("nan")
    lean = corners["lean_deg"].to_numpy(dtype=float)
    a = np.nanmax(np.abs(corners[["a_min", "a_max"]].to_numpy(dtype=float)), axis=1)
    a = np.clip(np.nan_to_num(a), 0.0, clip_g)
    g = grip_used(lean, a, mu=mu)
    g = g[np.isfinite(g)]
    return float(np.percentile(g, 95)) if len(g) else float("nan")


# --------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------

@dataclass
class Route:
    ok: bool
    cells: list = field(default_factory=list)      # cell ids, A -> B
    path: pd.DataFrame = field(default_factory=pd.DataFrame)   # the edges used
    summary: dict = field(default_factory=dict)
    note: str = ""

    @property
    def km(self) -> float:
        return float(self.summary.get("km", 0.0))


def _shortest(graph: Graph, si: int, ti: int, weights: np.ndarray | None = None,
              matrix: csr_matrix | None = None):
    """Dijkstra on the fit cost, a re-weighted copy, or a supplied matrix."""
    m = graph.matrix if matrix is None else matrix
    if weights is not None:
        m = csr_matrix((weights, m.indices, m.indptr), shape=m.shape)
    dist, pred = dijkstra(m, directed=True, indices=si, return_predecessors=True)
    if not np.isfinite(dist[ti]):
        return None
    out, k = [ti], ti
    while k != si:
        k = int(pred[k])
        if k < 0:
            return None
        out.append(k)
    return out[::-1]


def route_a_to_b(A, B, rider: Rider, z_star: float,
                 graph: Graph | None = None,
                 cells: pd.DataFrame | None = None,
                 edges: pd.DataFrame | None = None,
                 lam: float = LAMBDA_DEFAULT,
                 tau: float = TAU_DEFAULT,
                 osm: pd.DataFrame | None = None) -> Route:
    """
    A and B are (lat, lon). Builds the graph if one is not handed in — the
    app should hand one in and rebuild it only when the dial moves.
    """
    cells = load_cells() if cells is None else cells
    edges = load_edges() if edges is None else edges
    if graph is None:
        graph = build_graph(edges, cells, rider, z_star, tau=tau, lam=lam, osm=osm)

    for pt, name in ((A, "start"), (B, "finish")):
        if not in_coverage(pt[0], pt[1]):
            return Route(False, note=(
                f"The {name} is outside BMW's coverage "
                f"({COVERAGE[0]}-{COVERAGE[1]} N, {COVERAGE[2]}-{COVERAGE[3]} E). "
                "We have no crowd there, so we have no opinion."))

    a = snap(A[0], A[1], cells, nodes=graph.nodes)
    b = snap(B[0], B[1], cells, nodes=graph.nodes)
    if a == b:
        return Route(False, note="Start and finish snap to the same cell.")

    si, ti = graph.index[a], graph.index[b]
    note = ""

    idx = _shortest(graph, si, ti)
    if idx is None:
        # every corridor was refused. Do not return nothing on stage: say so,
        # reopen the gate as a penalty, and label the route honestly.
        open_graph = build_graph(edges, cells, rider, z_star, tau=tau, lam=lam,
                                 hard_gate=False, osm=osm)
        si, ti = open_graph.index[a], open_graph.index[b]
        idx = _shortest(open_graph, si, ti)
        if idx is None:
            return Route(False, note="No connected route between these two cells.")
        graph = open_graph
        note = ("Every route between these points crosses a road above this "
                "rider's gate. Shown with the gate as a penalty, not a refusal — "
                "read it as a warning, not a recommendation.")

    return _assemble(graph, idx, note=note)


def _assemble(graph: Graph, idx: list, note: str = "") -> Route:
    cells_path = [str(graph.nodes[i]) for i in idx]
    pairs = pd.DataFrame({"ci": cells_path[:-1], "cj": cells_path[1:]})
    path = pairs.merge(graph.edges, on=["ci", "cj"], how="left", validate="m:1")
    return Route(True, cells=cells_path, path=path,
                 summary=route_summary(path, graph.scored, graph.edges, graph=graph),
                 note=note)


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------

def _window_mean(flow: np.ndarray, length: np.ndarray, window_m: float) -> float:
    """Best contiguous `window_m` of the route, by length-weighted mean flow."""
    if len(flow) == 0:
        return 0.0
    cum_l = np.concatenate([[0.0], np.cumsum(length)])
    cum_f = np.concatenate([[0.0], np.cumsum(flow * length)])
    if cum_l[-1] <= window_m:
        return float(cum_f[-1] / max(cum_l[-1], 1e-9))
    ends = np.searchsorted(cum_l, cum_l[:-1] + window_m, side="left")
    ends = np.minimum(ends, len(length))
    span = cum_l[ends] - cum_l[:-1]
    val = cum_f[ends] - cum_f[:-1]
    ok = span > 1e-9
    return float(np.max(val[ok] / span[ok])) if ok.any() else 0.0


def route_summary(path: pd.DataFrame, cells: pd.DataFrame,
                  edges: pd.DataFrame, graph: Graph | None = None,
                  mu: float = MU_DEFAULT) -> dict:
    """
    Everything the ROUTE tab needs to put on screen, including the sentences
    it should say out loud about roads it refused.

    `cells` here is the scored table from score_cells (or graph.scored).

    CAVEAT for the UI: `fun_score` compares ROUTES AT THE SAME DIAL SETTING.
    It is not comparable across settings, because flow is fit to whatever z*
    is currently asked for — a Send It route can score below a Cruise route
    on the same roads without either being wrong. Show the dial setting next
    to the number, or compare mean_demand instead, which is an absolute.
    """
    if "flow" not in cells.columns and graph is not None:
        cells = graph.scored

    length = path["length_m"].to_numpy(dtype=float)
    length = np.where(np.isfinite(length), length, 0.0)
    secs = np.nan_to_num(path["seconds"].to_numpy(dtype=float))
    flow = np.nan_to_num(path["flow_j"].to_numpy(dtype=float))

    total_m = float(length.sum())
    w = length / max(total_m, 1e-9)

    mean_flow = float((flow * w).sum())
    peak_flow = _window_mean(flow, length, PEAK_WINDOW_M)

    cum = np.cumsum(length)
    tail_start = total_m * (1.0 - FINAL_SHARE)
    tail = cum >= tail_start
    final_flow = (float((flow[tail] * length[tail]).sum() /
                        max(length[tail].sum(), 1e-9)) if tail.any() else mean_flow)

    dull_share = float(length[flow < LOW_FLOW].sum() / max(total_m, 1e-9))
    base = W_MEAN * mean_flow + W_PEAK * peak_flow + W_FINAL * final_flow
    fun = 100.0 * base * (1.0 - TAIL_PENALTY * dull_share)

    # what the road asks of the tyre, lateral only — the longitudinal half
    # of the circle is a rider choice and we do not know it in advance.
    on = cells.reindex([c for c in path["cj"].astype(str)])
    demand = on["demand"].to_numpy(dtype=float)
    grip_lat = grip_used(demand, 0.0, mu=mu)

    ref = pd.DataFrame()
    if graph is not None and len(graph.refused):
        near = set(path["ci"].astype(str)) | set(path["cj"].astype(str))
        ref = graph.refused[graph.refused["ci"].isin(near)]

    refusals = []
    if graph is not None:
        g = graph.scored
        seen = set()
        src = ref if len(ref) else graph.refused.head(0)
        for c in src["cj"].astype(str):
            if c in seen or c not in g.index:
                continue
            seen.add(c)
            r = g.loc[c]
            refusals.append({"cell": c, "lat": float(r["lat"]), "lon": float(r["lon"]),
                             "demand": float(r["demand"]), "reason": str(r["reason"])})
            if len(refusals) >= 8:
                break

    return {
        "km": total_m / 1000.0,
        "minutes": float(secs.sum()) / 60.0,
        "n_cells": int(len(path) + 1),
        "mean_flow": mean_flow,
        "peak_flow": peak_flow,
        "final_flow": final_flow,
        "fun_score": float(np.clip(fun, 0.0, 100.0)),
        "dull_share": dull_share,
        "max_demand": float(np.nanmax(demand)) if len(demand) else float("nan"),
        "mean_demand": float(np.nansum(demand * w)) if len(demand) else float("nan"),
        "grip_lat_p95": float(np.nanpercentile(grip_lat, 95)) if len(grip_lat) else float("nan"),
        "grip_lat_max": float(np.nanmax(grip_lat)) if len(grip_lat) else float("nan"),
        "gate_deg": float(graph.rider.gate) if graph and graph.rider else float("nan"),
        "n_refused_nearby": int(len(ref)),
        "refusals": refusals,
        "imputed_cells": int(on["demand_imputed"].sum()) if "demand_imputed" in on else 0,
    }


def _path_sum(m: csr_matrix, idx) -> float:
    """Total of one CSR weight along a node path, without touching pandas."""
    tot = 0.0
    for a, b in zip(idx[:-1], idx[1:]):
        lo, hi = m.indptr[a], m.indptr[a + 1]
        k = np.flatnonzero(m.indices[lo:hi] == b)
        if len(k):
            tot += float(m.data[lo + k[0]])
    return tot


def _penalise(m: csr_matrix, pairs, factor: float = 6.0) -> csr_matrix:
    """
    Make the edges already used expensive, in BOTH directions, so the return
    leg looks for another road. Riding the same pass back the way you came is
    a legal loop and a poor one.
    """
    m2 = m.copy()
    for i, j in pairs:
        for a, b in ((i, j), (j, i)):
            lo, hi = m2.indptr[a], m2.indptr[a + 1]
            k = np.flatnonzero(m2.indices[lo:hi] == b)
            if len(k):
                m2.data[lo + k[0]] *= factor
    return m2


def route_loop(start, hours: float, rider: Rider, z_star: float,
               graph: Graph | None = None,
               cells: pd.DataFrame | None = None,
               edges: pd.DataFrame | None = None,
               lam: float = LAMBDA_DEFAULT,
               tau: float = TAU_DEFAULT,
               osm: pd.DataFrame | None = None,
               tolerance: float = 0.20,
               n_candidates: int = 160,
               reuse_penalty: float = 6.0) -> Route:
    """
    BMW use case B: "give me a loop for the next X hours from here."

    Choosing the best closed tour under a time budget is the orienteering
    problem, which is NP-hard, so this is a heuristic — and an honest one:

      1. Dijkstra out from the start, and a second Dijkstra on the transposed
         graph, which gives the time to get BACK from every node. A node is a
         feasible turnaround only if out + back fits inside the budget.
      2. Rank the feasible ring by fit cost per second — low cost per second
         is exactly "this direction is full of roads that suit you".
      3. For the best handful, ride out to the turnaround, then make every
         edge just used 6x expensive and route home again. The return leg
         then finds different roads instead of retracing the outbound one.
      4. Keep the loops that land inside the budget and return the one with
         the best peak-end score.

    Time comes from the edge table's own median speeds, so the budget is in
    real riding minutes, not an assumed average.
    """
    cells = load_cells() if cells is None else cells
    edges = load_edges() if edges is None else edges
    if graph is None:
        graph = build_graph(edges, cells, rider, z_star, tau=tau, lam=lam, osm=osm)

    if not in_coverage(start[0], start[1]):
        return Route(False, note=(
            f"That start is outside BMW's coverage "
            f"({COVERAGE[0]}-{COVERAGE[1]} N, {COVERAGE[2]}-{COVERAGE[3]} E). "
            "We have no crowd there, so we have no opinion."))

    a = snap(start[0], start[1], cells, nodes=graph.nodes)
    si = graph.index[a]
    budget = float(hours) * 3600.0

    fit = graph.matrix
    sec = csr_matrix((_csr_aligned(graph, "seconds"), fit.indices, fit.indptr),
                     shape=fit.shape)

    t_out = dijkstra(sec, directed=True, indices=si)
    t_back = dijkstra(sec.T.tocsr(), directed=True, indices=si)
    c_out = dijkstra(fit, directed=True, indices=si)
    c_back = dijkstra(fit.T.tocsr(), directed=True, indices=si)

    total_t = t_out + t_back
    total_c = c_out + c_back
    # leave room for the detour the disjoint return will cost us
    feasible = np.flatnonzero(np.isfinite(total_t) & np.isfinite(total_c) &
                              (total_t >= 0.50 * budget) &
                              (total_t <= 1.00 * budget))
    if not len(feasible):
        reach = np.nanmax(t_out[np.isfinite(t_out)]) / 3600.0 if np.isfinite(t_out).any() else 0.0
        return Route(False, note=(
            f"No turnaround fits a {hours:.1f} h budget from here. The "
            f"furthest point reachable on roads we have data for is "
            f"{reach:.1f} h away, so try a shorter loop or a start with more "
            f"road around it."))

    order = feasible[np.argsort(total_c[feasible] / np.maximum(total_t[feasible], 1.0))]

    # Score candidates WITHOUT assembling them. Assembling means a pandas
    # merge per candidate, which is ~5 ms and caps us at a few dozen tries;
    # scoring off flat NumPy arrays is microseconds and lets us try hundreds.
    flow_by_node = (graph.scored["flow"].reindex(graph.nodes)
                    .fillna(0.0).to_numpy(dtype=float))
    target = hours * 60.0

    def try_all(tol: float):
        hit, hit_score = None, -1.0
        for mid in order[:n_candidates]:
            out_idx = _shortest(graph, si, int(mid))
            if out_idx is None or len(out_idx) < 2:
                continue
            used = list(zip(out_idx[:-1], out_idx[1:]))
            home_idx = _shortest(graph, int(mid), si,
                                 matrix=_penalise(fit, used, reuse_penalty))
            if home_idx is None or len(home_idx) < 2:
                continue
            idx = out_idx + home_idx[1:]
            mins = _path_sum(sec, idx) / 60.0
            if not (1.0 - tol) * target <= mins <= (1.0 + tol) * target:
                continue
            arr = np.asarray(idx)
            distinct = len(set(idx)) / len(idx)
            fill = 1.0 - abs(mins - target) / max(target, 1.0)
            sc = float(flow_by_node[arr].mean()) * distinct * fill
            if sc > hit_score:
                hit, hit_score = idx, sc
        return hit

    idx = try_all(tolerance)
    widened = False
    if idx is None:
        # Do not hand the stage a dead end. Say the budget could not be met
        # exactly and show the closest thing we can actually ride.
        idx = try_all(min(tolerance * 2.5, 0.6))
        widened = idx is not None

    if idx is None:
        return Route(False, note=(
            f"Found turnarounds for a {hours:.1f} h loop but none came home "
            f"inside the budget. Try a start with more connected road around "
            f"it, or a different number of hours."))

    best = _assemble(graph, idx)
    if not best.ok:
        return best
    best.summary["distinct_share"] = len(set(idx)) / len(idx)
    best.summary["budget_fill"] = best.summary["minutes"] / max(target, 1.0)

    best.summary["is_loop"] = True
    best.summary["budget_min"] = hours * 60.0
    best.summary["turnaround"] = str(graph.nodes[order[0]])
    note = (f"Loop: {best.summary['distinct_share']:.0%} of the cells are "
            f"ridden once, the rest is unavoidable retracing.")
    if widened:
        note += (f" No loop fitted {hours:.1f} h to within "
                 f"{tolerance:.0%}; this is the closest ridable one at "
                 f"{best.summary['minutes']:.0f} min.")
    best.note = (best.note + " " if best.note else "") + note
    return best


def compare_routes(a: Route, b: Route) -> dict:
    """
    How different are two routes for the same A and B? This, not the detour
    ratio, is what the Thrill Dial actually moves on this network — see
    analysis/12_route_calibration.py.
    """
    ca, cb = set(a.cells), set(b.cells)
    return {
        "overlap": len(ca & cb) / max(len(ca | cb), 1),
        "km_ratio": b.km / a.km if a.km else float("nan"),
        "demand_gain": b.summary.get("mean_demand", float("nan"))
                       - a.summary.get("mean_demand", float("nan")),
    }


def direct_route(A, B, graph: Graph) -> Route:
    """The same graph costed by pure length — the baseline to detour against."""
    cells_ = graph.scored
    a = snap(A[0], A[1], cells_.reset_index().rename(columns={"cell": "morton_code"}),
             nodes=graph.nodes)
    b = snap(B[0], B[1], cells_.reset_index().rename(columns={"cell": "morton_code"}),
             nodes=graph.nodes)
    si, ti = graph.index[a], graph.index[b]
    idx = _shortest(graph, si, ti, weights=_csr_aligned_lengths(graph))
    if idx is None:
        return Route(False, note="No connected route.")
    return _assemble(graph, idx)


def _csr_aligned(graph: Graph, col: str) -> np.ndarray:
    """
    csr_matrix sorts and may sum duplicate (i,j) entries, so the edge frame's
    row order is NOT the matrix's data order. Rebuild any edge column through
    the same constructor so it lines up with graph.matrix.data exactly.
    """
    m = csr_matrix(
        (graph.edges[col].to_numpy(dtype=float),
         (graph.edges["i"].to_numpy(dtype=np.int64),
          graph.edges["j"].to_numpy(dtype=np.int64))),
        shape=graph.matrix.shape,
    )
    return m.data


def _csr_aligned_lengths(graph: Graph) -> np.ndarray:
    return _csr_aligned(graph, "length_m")


# --------------------------------------------------------------------------
# stop-check
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import time

    cells = load_cells()
    edges = load_edges()
    osm = load_osm()
    print(f"grid {TAG}: {len(cells):,} cells, {len(edges):,} edges "
          f"(symmetrised), {len(set(edges.ci) | set(edges.cj)):,} nodes")

    if osm is None:
        print("  OSM layer ABSENT — run analysis/13_osm_layer.py. "
              "No posted-limit check, no surface or road-class flags.")
    else:
        cells = apply_legal_speed(cells, osm)
        capped = int(cells["demand_capped"].sum())
        m = cells["demand_capped"]
        before = cells.loc[m, "demand_before_cap"].mean()
        after = cells.loc[m, "demand_p90"].mean()
        known = osm["osm_maxspeed_kmh"].reindex(cells["morton_code"]).notna().mean()
        share = capped / max(int((osm["osm_maxspeed_kmh"]
                                  .reindex(cells["morton_code"]).notna()).sum()), 1)
        print(f"  OSM: posted limit known for {known:.0%} of cells. "
              f"{capped:,} of those ({share:.0%}) had a crowd p85 above the "
              f"limit and were re-priced at the legal speed:")
        print(f"       their mean demand falls {before:.2f} -> {after:.2f} deg "
              f"({after-before:+.2f})")
        for c, label in (("red_fast_boring", "motorway/trunk"),
                         ("red_inner_city", "residential"),
                         ("red_bad_surface", "unpaved/cobbled")):
            if c in osm.columns:
                m = osm[c].reindex(cells["morton_code"]).fillna(False)
                print(f"       RED {label:<16s} {int(m.sum()):5,} cells ({m.mean():5.1%})")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import flowstate as fs
    corners = fs.load_corners(filtered=True)
    rider = calibrate_rider(corners, cells, "User A")
    grip = rider_grip_p95(corners)

    print(f"{rider.label}: skill {rider.skill:.2f}deg  sigma {rider.sigma:.2f}  "
          f"gate {rider.gate:.2f}deg vs hardest road actually ridden "
          f"{rider.hardest_ridden:.2f}deg ({rider.gate_agreement:.3f}x)")
    print(f"  calibrated on {rider.n_cells} shared cells; crowd-wide p95 "
          f"{rider.crowd_skill:.2f}deg; rider grip p95 {grip:.2f} of mu={MU_DEFAULT}")

    # the demo pair, picked by the scan in analysis/12_route_calibration.py
    A, B = (47.59, 11.75), (47.73, 11.37)
    lam = float(os.environ.get("FS_LAM", LAMBDA_DEFAULT))
    out = {}
    for name, z in (("Cruise", 0.15), ("Send it", 0.90)):
        t0 = time.time()
        g = build_graph(edges, cells, rider, z, lam=lam, osm=osm)
        r = route_a_to_b(A, B, rider, z, graph=g, cells=cells, edges=edges, osm=osm)
        d = direct_route(A, B, g)
        ms = (time.time() - t0) * 1000
        out[name] = r
        s_ = r.summary
        print(f"\n{name:8s} z*={z:<5} lam={lam:<5} {ms:5.0f} ms")
        print(f"  {s_['km']:5.1f} km / {s_['minutes']:4.0f} min   "
              f"direct {d.summary['km']:5.1f} km   detour {s_['km']/d.summary['km']:.2f}x")
        print(f"  flow mean {s_['mean_flow']:.3f} peak {s_['peak_flow']:.3f} "
              f"final {s_['final_flow']:.3f}  ->  FUN {s_['fun_score']:.1f}")
        print(f"  demand mean {s_['mean_demand']:5.2f}deg  max {s_['max_demand']:5.2f}deg "
              f"(gate {s_['gate_deg']:.2f})  grip p95 {s_['grip_lat_p95']:.2f}")
        print(f"  graph {g.n_nodes:,} nodes, {len(g.edges):,} edges, "
              f"{len(g.refused):,} refused by the gate")
        if r.note:
            print(f"  NOTE {r.note}")
        for x in s_["refusals"][:2]:
            print(f"  refused {x['lat']:.4f},{x['lon']:.4f}: {x['reason']}")

    cmp = compare_routes(out["Cruise"], out["Send it"])
    print(f"\ndial effect: {cmp['km_ratio']:.2f}x the distance, "
          f"{cmp['overlap']:.0%} of cells shared, "
          f"{cmp['demand_gain']:+.2f}deg mean demand")
