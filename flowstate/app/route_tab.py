"""
route_tab.py — the ROUTE tab: both of the things BMW actually asked for.

    use case A   A -> B, the best road rather than the fastest one
    use case B   a loop of roughly X hours from where I am standing

Everything here goes through `service.py`. This module never touches a
DataFrame, never builds a graph and never learns what a morton code is; it
turns plain dicts into pixels.

MOBILE FIRST, on purpose. The demo is served from the Mac and watched on a
phone over Tailscale, so:

  * the Thrill Dial lives in the tab body, not the sidebar — on a phone the
    sidebar is a hamburger drawer, and the dial is the hero control;
  * every preset is a full-width BUTTON, not a dropdown;
  * the map draws its own grey roads from cached OSM and asks for no tiles,
    because with the network unplugged a tile map is a black rectangle;
  * Cruise and Send it are drawn on ONE map at the same time. Across 200 O-D
    pairs the median demand gain from the dial is -0.00 deg (doc 14), so
    making a judge drag a slider and hope is a bad bet. Show both lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import pydeck as pdk
    HAS_PYDECK = True
except Exception:                                          # pragma: no cover
    HAS_PYDECK = False

BLUE = "#1C69D4"
GOLD = "#FFD23F"
RED = "#E8523F"
GREY = "#8A8F98"
TEAL = "#00BEA0"

# the crowd data is Bavaria only. A Zurich start returns nothing, so the free
# -entry boxes are clamped to the box rather than allowed to fail politely.
COVERAGE = (47.38, 48.03, 10.72, 11.96)

RED_CLASSES = {"motorway", "motorway_link", "trunk", "trunk_link"}

CSS = """
<style>
  /* the deck is sized in px for the laptop and in vh for the phone */
  @media (max-width: 640px) {
    div[data-testid="stDeckGlJsonChart"],
    div[data-testid="stDeckGlJsonChart"] > div { height: 50vh !important; }
    .fs-head { font-size: 1.02rem !important; }
  }
  .fs-head {
    background: linear-gradient(90deg, #1C69D422, #FFD23F18);
    border-left: 4px solid #FFD23F; border-radius: 6px;
    padding: 11px 14px; margin: 4px 0 10px 0;
    font-size: 1.12rem; font-weight: 600; line-height: 1.45;
  }
  .fs-why { color: #8A8F98; font-size: 0.78rem; margin: -6px 0 10px 2px; }
  .fs-exp { line-height: 1.62; font-size: 0.94rem; }
  .fs-exp li { margin-bottom: 5px; }
  .fs-ref { color: #E8523F; font-size: 0.86rem; line-height: 1.5; }
  .fs-key { display:flex; gap:14px; flex-wrap:wrap; font-size:0.78rem;
            color:#8A8F98; margin: 6px 0 2px 2px; }
  .fs-key b { font-weight:600; }
</style>
"""


# ==========================================================================
# the service, loaded once
# ==========================================================================

@st.cache_resource(show_spinner="Loading the baked scenario…")
def _svc():
    import service as S
    S.init()
    return S


@st.cache_data(show_spinner=False)
def _basemap():
    """17,345 OSM ways, split into what BMW flags RED and everything else."""
    bm = _svc().basemap()
    red = [w for w in bm if w["cls"] in RED_CLASSES]
    grey = [w for w in bm if w["cls"] not in RED_CLASSES]
    return grey, red


@st.cache_data(show_spinner=False)
def _riders():
    return _svc().riders()


@st.cache_data(show_spinner="Routing…")
def _route(a, b, rider, z):
    return _svc().route(a, b, rider, z)


@st.cache_data(show_spinner="Routing both dial settings…")
def _compare(a, b, rider):
    return _svc().compare(a, b, rider)


@st.cache_data(show_spinner="Building a loop…")
def _loop(start, hours, rider, z):
    return _svc().loop(start, hours, rider, z)


# ==========================================================================
# map plumbing
# ==========================================================================

def _fit(pts, width_px: int = 700, height_px: int = 430, pad: float = 0.45):
    """
    Fit a [lon, lat] point list to the canvas. At zoom z a tile is 256 px and
    spans 360/2^z degrees, so the zoom that fits a box is
    log2(px * 360 / (256 * span)) — dropping the pixel term is what opens a
    deck.gl map zoomed out over half of Europe.
    """
    if not pts:
        return 47.70, 11.40, 9.0
    lons = np.array([p[0] for p in pts], dtype=float)
    lats = np.array([p[1] for p in pts], dtype=float)
    clat, clon = float(lats.mean()), float(lons.mean())
    lat_span = max(float(lats.max() - lats.min()), 1e-3)
    lon_span = max(float(lons.max() - lons.min()), 1e-3)
    cos = max(np.cos(np.radians(clat)), 0.1)
    z_lon = np.log2(width_px * 360.0 / (256.0 * lon_span))
    z_lat = np.log2(height_px * 360.0 * cos / (256.0 * lat_span))
    return clat, clon, float(np.clip(min(z_lon, z_lat) - pad, 6.0, 14.0))


def _flow_color(f: float, alpha: int = 240):
    """Dim steel blue at no fit, BMW gold at a perfect one."""
    f = float(np.clip(f, 0.0, 1.0))
    lo, hi = (64, 86, 124), (255, 210, 63)
    return [int(lo[i] + (hi[i] - lo[i]) * f) for i in range(3)] + [alpha]


def _basemap_layers():
    grey, red = _basemap()
    return [
        pdk.Layer("PathLayer", data=grey, get_path="path",
                  get_color=[78, 84, 96, 150], width_min_pixels=1,
                  get_width=1, width_units="pixels", pickable=False),
        pdk.Layer("PathLayer", data=red, get_path="path",
                  get_color=[150, 66, 58, 170], width_min_pixels=1,
                  get_width=2, width_units="pixels", pickable=False),
    ]


def _flow_path_layer(res: dict, width: int = 5):
    """One record per segment so the line can be coloured by fit."""
    data = []
    for s in res["segments"]:
        data.append({"path": [s["from"], s["to"]],
                     "color": _flow_color(s["flow"]),
                     "tip": f"fit {s['flow']:.2f} · asks {s['demand']:.1f}° of lean"})
    return pdk.Layer("PathLayer", data=data, get_path="path", get_color="color",
                     get_width=width, width_units="pixels", width_min_pixels=3,
                     pickable=True, cap_rounded=True, joint_rounded=True)


def _flat_path_layer(res: dict, color, width: int, label: str):
    data = [{"path": res["path"], "tip": label}]
    return pdk.Layer("PathLayer", data=data, get_path="path", get_color=color,
                     get_width=width, width_units="pixels",
                     width_min_pixels=max(2, width - 1), pickable=True,
                     cap_rounded=True, joint_rounded=True)


def _refusal_layer(res: dict):
    """
    Red pins where the safety gate REMOVED a road. A refusal is a deleted
    edge, not an expensive one — a gate you can buy past with a big enough
    detour budget is not a gate.
    """
    data = [{"pos": [r["lon"], r["lat"]],
             "tip": "REFUSED — " + r["reason"]} for r in res.get("refusals", [])]
    if not data:
        return None
    return pdk.Layer("ScatterplotLayer", data=data, get_position="pos",
                     get_fill_color=[232, 82, 63, 225],
                     get_line_color=[255, 255, 255, 220], line_width_min_pixels=2,
                     stroked=True, get_radius=340, radius_min_pixels=6,
                     radius_max_pixels=11, pickable=True)


def _ends_layer(path, loop: bool = False):
    if not path:
        return None
    data = [{"pos": path[0], "tip": "start", "c": [0, 190, 160, 235]}]
    if not loop:
        data.append({"pos": path[-1], "tip": "finish", "c": [240, 240, 245, 235]})
    return pdk.Layer("ScatterplotLayer", data=data, get_position="pos",
                     get_fill_color="c", get_line_color=[20, 22, 28, 230],
                     line_width_min_pixels=2, stroked=True, get_radius=420,
                     radius_min_pixels=7, radius_max_pixels=12, pickable=True)


def _deck(layers, pts, height: int = 430, key: str = "rt"):
    """Draw it. If pydeck is missing or throws, fall back to plotly."""
    layers = [l for l in layers if l is not None]
    clat, clon, zoom = _fit(pts, height_px=height)
    if HAS_PYDECK:
        try:
            st.pydeck_chart(
                pdk.Deck(layers=layers,
                         initial_view_state=pdk.ViewState(
                             latitude=clat, longitude=clon, zoom=zoom,
                             pitch=0, bearing=0),
                         map_provider=None, map_style=None,
                         tooltip={"html": "<b>{tip}</b>",
                                  "style": {"backgroundColor": "#14161c",
                                            "color": "#eaeaea",
                                            "fontSize": "12px"}}),
                height=height, key=key)
            return
        except Exception as exc:                           # pragma: no cover
            st.caption(f"pydeck unavailable ({type(exc).__name__}) — "
                       f"drawing the plain offline map instead.")
    _plotly_fallback(pts, height, key)


def _plotly_fallback(pts, height: int, key: str):
    import plotly.graph_objects as go
    fig = go.Figure()
    if pts:
        fig.add_trace(go.Scattergl(x=[p[0] for p in pts], y=[p[1] for p in pts],
                                   mode="lines", line=dict(color=GOLD, width=2),
                                   hoverinfo="skip"))
    clat = float(np.mean([p[1] for p in pts])) if pts else 47.7
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0),
                      showlegend=False, xaxis_title="", yaxis_title="")
    fig.update_yaxes(scaleanchor="x",
                     scaleratio=1.0 / max(np.cos(np.radians(clat)), 0.1))
    st.plotly_chart(fig, key=key + "_pl", config={"displayModeBar": False})


# ==========================================================================
# small ui helpers
# ==========================================================================

def _pick(label: str, options, key: str, default=None, help: str | None = None):
    """Segmented control where the Streamlit build has one, radio otherwise."""
    vis = "collapsed" if not label else "visible"
    if hasattr(st, "segmented_control"):
        v = st.segmented_control(
            label or key, options, key=key, label_visibility=vis, help=help,
            default=default if key not in st.session_state else None)
        return v if v is not None else (st.session_state.get(key) or default)
    return st.radio(label or key, options, key=key, horizontal=True, help=help,
                    label_visibility=vis,
                    index=options.index(default) if default in options else 0)


def _explain(res: dict):
    st.markdown("<ul class='fs-exp'>"
                + "".join(f"<li>{x}</li>" for x in res.get("explain", []))
                + "</ul>", unsafe_allow_html=True)


def _key_line():
    st.markdown(
        "<div class='fs-key'>"
        "<span><b style='color:#FFD23F'>&#9473;</b> fits you</span>"
        "<span><b style='color:#405C7C'>&#9473;</b> dull for you</span>"
        "<span><b style='color:#96423A'>&#9473;</b> motorway / trunk (BMW RED)</span>"
        "<span><b style='color:#E8523F'>&#9679;</b> refused by your safety gate</span>"
        "</div>", unsafe_allow_html=True)


def _summary_row(s: dict, z_star: float, loop: bool = False):
    c1, c2, c3 = st.columns(3)
    c1.metric("Distance", f"{s['km']:.0f} km")
    if loop:
        c2.metric("Riding time", f"{s['minutes']:.0f} min",
                  f"{s['budget_fill']:.0%} of budget")
    else:
        c2.metric("Riding time", f"{s['minutes']:.0f} min")
    c3.metric("Mean lean asked", f"{s['mean_demand']:.1f}°",
              help="Absolute, so it is comparable across dial settings. "
                   "fun_score is not.")
    c4, c5, c6 = st.columns(3)
    c4.metric("Peak fit (best 5 km)", f"{s['peak_flow']:.2f}")
    c5.metric("Fun score", f"{s['fun_score']:.0f}",
              help="Comparable across ROUTES at the same dial, never across "
                   "dial settings — flow is fit to whatever z* you asked for, "
                   "so Send it can legitimately score below Cruise.")
    grip = s.get("grip_lat_p95", float("nan"))
    c6.metric("Grip used", f"{grip:.0%}" if np.isfinite(grip) else "—",
              help="Lateral only, p95, mu = 1.1.")
    gate = s.get("gate_deg", float("nan"))
    st.caption(f"Fun score is read at z★ = {z_star:.2f}."
               + (f" Your safety gate on this profile is {gate:.1f}° of lean."
                  if np.isfinite(gate) else ""))


# ==========================================================================
# the tab
# ==========================================================================

def render():
    st.markdown(CSS, unsafe_allow_html=True)

    S = _svc()
    P = S.presets()
    rl = _riders()

    st.caption("Two questions BMW asked. **A → B**, the best road rather than "
               "the fastest one — and **a loop for X hours** from where you are "
               "standing. Both answered from the crowd's own lean angles.")

    # ---- rider --------------------------------------------------------
    labels = {r["label"]: r["key"] for r in rl}
    rider_label = _pick("Rider profile", list(labels), key="rt_rider",
                        default=rl[0]["label"],
                        help="Two people have personal telemetry: User A and "
                             "User C. The bike profiles are User A on one machine "
                             "at a time, because lean p95 on an S1000RR and on an "
                             "R18 are not the same measurement.")
    rider_key = labels.get(rider_label, rl[0]["key"])
    rr = next(r for r in rl if r["key"] == rider_key)

    with st.expander(f"This rider · skill {rr['skill']:.1f}° · "
                     f"gate {rr['gate']:.1f}°"):
        a, b, c = st.columns(3)
        a.metric("Skill", f"{rr['skill']:.1f}°",
                 help="Median demand of the cells this rider actually rode, "
                      "read off the crowd's own ruler.")
        b.metric("σ", f"{rr['sigma']:.1f}°")
        c.metric("Safety gate", f"{rr['gate']:.1f}°", help="skill + 2σ")
        a.metric("Hardest ridden", f"{rr['hardest_ridden']:.1f}°")
        b.metric("Gate agreement", f"{rr['gate_agreement']:.3f}×",
                 help="Gate ÷ the hardest road this rider ever chose. Nothing "
                      "in the construction forces this to be near 1.")
        c.metric("Grip already used", f"{rr['grip_p95']:.0%}")
        st.caption(f"{rr['n_cells']:,} crowd cells ridden · "
                   f"{rr['n_corners']:,} corners. The gate is derived from the "
                   f"*spread* of this rider's road choices, yet lands within "
                   f"{abs(1 - rr['gate_agreement']):.1%} of the hardest road "
                   f"they have ever chosen.")

    mode = _pick("", ["A → B", "Loop for X hours"], key="rt_mode",
                 default="A → B")
    st.divider()

    if mode == "Loop for X hours":
        _render_loop(S, P, rider_key)
    else:
        _render_ab(S, P, rider_key, rl)

    st.caption(f"Coverage is Bavaria only — lat {COVERAGE[0]}–{COVERAGE[1]}, "
               f"lon {COVERAGE[2]}–{COVERAGE[3]}. Outside that box the crowd has "
               f"never ridden and the router says so rather than inventing a "
               f"road. Everything on this screen came off a 6 MB local bake; "
               f"no BMW data and no request leaves this machine.")


# --------------------------------------------------------------------------
# use case A
# --------------------------------------------------------------------------

def _render_ab(S, P, rider_key: str, rl: list):
    st.markdown("##### Where to?")
    st.caption("Rehearsed pairs. The dial only moves the road where a second "
               "corridor exists, which is a minority of pairs — these are the "
               "ones where it does.")

    st.session_state.setdefault("rt_pair", P["routes"][0]["key"])
    for p in P["routes"]:
        chosen = p["key"] == st.session_state["rt_pair"]
        if st.button(("● " if chosen else "○ ") + p["label"],
                     key="rtb_" + p["key"], use_container_width=True,
                     type="primary" if chosen else "secondary"):
            st.session_state["rt_pair"] = p["key"]
            st.session_state["rt_use_free"] = False
            st.rerun()
        if chosen:
            st.markdown(f"<div class='fs-why'>{p['why']}</div>",
                        unsafe_allow_html=True)

    pair = next(p for p in P["routes"] if p["key"] == st.session_state["rt_pair"])
    a, b = tuple(pair["a"]), tuple(pair["b"])

    with st.expander("…or pick your own two points"):
        c1, c2 = st.columns(2)
        alat = c1.number_input("from lat", COVERAGE[0], COVERAGE[1], float(a[0]),
                               step=0.01, format="%.3f", key="rt_alat")
        alon = c2.number_input("from lon", COVERAGE[2], COVERAGE[3], float(a[1]),
                               step=0.01, format="%.3f", key="rt_alon")
        blat = c1.number_input("to lat", COVERAGE[0], COVERAGE[1], float(b[0]),
                               step=0.01, format="%.3f", key="rt_blat")
        blon = c2.number_input("to lon", COVERAGE[2], COVERAGE[3], float(b[1]),
                               step=0.01, format="%.3f", key="rt_blon")
        if st.button("Route these", use_container_width=True, key="rt_free"):
            st.session_state["rt_free_ab"] = ((alat, alon), (blat, blon))
            st.session_state["rt_use_free"] = True
            st.rerun()
        if st.session_state.get("rt_use_free"):
            st.caption("Using your own points. Tap a preset above to go back.")
    if st.session_state.get("rt_use_free") and st.session_state.get("rt_free_ab"):
        a, b = st.session_state["rt_free_ab"]

    cmp = _compare(a, b, rider_key)
    lo, hi = cmp["low"], cmp["high"]
    if not (lo["ok"] and hi["ok"]):
        st.error(lo.get("note") or hi.get("note") or "No route.")
        return

    # ---- the money shot: both dial settings on one map -----------------
    st.markdown(f"<div class='fs-head'>{cmp['headline']}</div>",
                unsafe_allow_html=True)

    layers = _basemap_layers() + [
        _flat_path_layer(lo, [130, 148, 178, 200], 4, "Cruise  z★ 0.15"),
        _flat_path_layer(hi, [255, 210, 63, 240], 6, "Send it  z★ 0.90"),
        _refusal_layer(hi),
        _ends_layer(hi["path"]),
    ]
    _deck(layers, lo["path"] + hi["path"], height=430, key="rt_cmp")
    st.markdown(
        "<div class='fs-key'>"
        "<span><b style='color:#FFD23F'>&#9473;</b> Send it</span>"
        "<span><b style='color:#8294B2'>&#9473;</b> Cruise</span>"
        "<span><b style='color:#96423A'>&#9473;</b> motorway / trunk (BMW RED)</span>"
        "<span><b style='color:#E8523F'>&#9679;</b> refused by the gate</span>"
        "</div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Cruise", f"{lo['summary']['km']:.0f} km",
              f"{lo['summary']['mean_demand']:.1f}° mean lean",
              delta_color="off")
    c2.metric("Send it", f"{hi['summary']['km']:.0f} km",
              f"{hi['summary']['mean_demand']:.1f}° mean lean",
              delta_color="off")
    c3.metric("Shared road", f"{cmp['overlap']:.0%}",
              help="Share of cells the two answers have in common.")
    if cmp["overlap"] > 0.60 and cmp["demand_gain"] < 0.5:
        st.caption("On this pair the dial barely moves the road, and the app "
                   "says so rather than dressing it up. Either the crowd graph "
                   "has only one corridor here, or the more demanding road sits "
                   "past this rider's safety gate - any road refused is pinned "
                   "in red below.")
    else:
        st.caption("The router is not padding mileage — it is choosing "
                   "character. Same two points, roughly the same distance, a "
                   "different road.")

    st.divider()

    # ---- one dial, in detail -----------------------------------------
    st.markdown("##### Thrill Dial")
    dial = _pick("", list(P["dial"]), key="rt_dial", default="Send it",
                 help="Flow theory: people are in flow when the challenge sits "
                      "slightly ABOVE their skill. z★ is how far above.")
    z = P["dial"].get(dial, 0.90)
    res = _route(a, b, rider_key, z)
    if not res["ok"]:
        st.error(res["note"])
        return

    if res["note"]:                    # empty on a healthy route; a caveat if not
        st.warning(res["note"])
    layers = _basemap_layers() + [_flow_path_layer(res),
                                  _refusal_layer(res),
                                  _ends_layer(res["path"])]
    _deck(layers, res["path"], height=430, key="rt_one")
    _key_line()
    _summary_row(res["summary"], z)

    st.markdown("##### Why this road")
    _explain(res)
    if res["refusals"]:
        st.markdown("<div class='fs-ref'>" + "<br>".join(
            f"● {r['reason']}" for r in res["refusals"]) + "</div>",
            unsafe_allow_html=True)
        st.caption("These roads were deleted from the graph, not made "
                   "expensive. A gate you can buy past with a big enough "
                   "detour budget is not a gate.")


# --------------------------------------------------------------------------
# use case B
# --------------------------------------------------------------------------

def _render_loop(S, P, rider_key: str):
    st.markdown("##### Start from")
    st.session_state.setdefault("rt_start", P["loops"][0]["key"])
    cols = st.columns(2)
    for i, p in enumerate(P["loops"]):
        chosen = p["key"] == st.session_state["rt_start"]
        if cols[i % 2].button(("● " if chosen else "○ ") + p["label"],
                              key="rtl_" + p["key"], use_container_width=True,
                              type="primary" if chosen else "secondary"):
            st.session_state["rt_start"] = p["key"]
            st.rerun()
    start = tuple(next(p for p in P["loops"]
                       if p["key"] == st.session_state["rt_start"])["start"])

    c1, c2 = st.columns(2)
    with c1:
        hours = _pick("How long have you got?", ["1 h", "1.5 h", "2 h", "3 h"],
                      key="rt_hours", default="2 h")
    with c2:
        dial = _pick("Thrill Dial", list(P["dial"]), key="rt_ldial",
                     default="Send it")
    h = float(str(hours).replace(" h", ""))
    z = P["dial"].get(dial, 0.90)

    res = _loop(start, h, rider_key, z)
    if not res["ok"]:
        st.error(res["note"])
        return

    layers = _basemap_layers() + [_flow_path_layer(res),
                                  _refusal_layer(res),
                                  _ends_layer(res["path"], loop=True)]
    _deck(layers, res["path"], height=440, key="rt_loop")
    _key_line()

    s = res["summary"]
    _summary_row(s, z, loop=True)
    c1, c2 = st.columns(2)
    c1.metric("Road ridden only once", f"{s['distinct_share']:.0%}",
              help="A genuine loop, not an out-and-back retrace.")
    c2.metric("Back at the start", "yes")

    if "closest" in res["note"]:
        st.warning(res["note"])

    st.markdown("##### Why this loop")
    _explain(res)
    st.caption("Choosing the best closed tour under a time budget is the "
               "orienteering problem, which is NP-hard — this is a heuristic "
               "and says so. Dijkstra out, a second Dijkstra on the transposed "
               "graph for the ride home, rank the turnarounds by fit-cost per "
               "second, then make the outbound roads 6× expensive so the return "
               "leg finds new ones. Time comes from the crowd's own median "
               "speeds, so the budget is real riding minutes.")
