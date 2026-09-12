"""
FLOWSTATE — BMW Motorrad "Find Your Thrill", TUM.AI Hackathon Zürich 2026.

    streamlit run F:\\bmw\\app\\streamlit_app.py --server.headless true --server.port 8502

Everything is local. No network calls, no uploads, no external data. The only
thing that ever touches the network is the optional basemap tile layer, and the
app is built to render correctly with it switched off — see the sidebar.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flowstate as F  # noqa: E402
import route_tab  # noqa: E402

try:
    import pydeck as pdk
    HAS_PYDECK = True
except Exception:                                    # pragma: no cover
    HAS_PYDECK = False

# MOBILE FIRST. This is served from the Mac and watched on a phone over
# Tailscale, so the layout is centred (a phone viewport is narrower than the
# centred column anyway, and it fixes the deck.gl zoom fit, which assumes a
# 700 px canvas) and the sidebar starts collapsed — on a phone it is a
# hamburger drawer, so nothing that matters may live in it.
st.set_page_config(page_title="FLOWSTATE — BMW Motorrad",
                   page_icon="🏍", layout="centered",
                   initial_sidebar_state="collapsed")

# NOTE for whoever demos this: the deck.gl maps zoom on mouse wheel and
# Streamlit's deck component ignores deck's controller config, so scroll the
# PAGE from the margin beside a map, not over it. Drag to pan, +/- to zoom.

BLUE = "#1C69D4"      # BMW blue
GOLD = "#FFD23F"
RED = "#E8523F"
GREY = "#8A8F98"
TEAL = "#00BEA0"

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 1rem;}
  div[data-testid="stMetricValue"] {font-size: 1.5rem;}
  .fs-tag {display:inline-block;padding:2px 9px;border-radius:10px;font-size:0.72rem;
           font-weight:600;letter-spacing:.4px;margin-right:6px;}
  /* phone: reclaim the margins, let metric rows wrap, keep tabs on one line */
  @media (max-width: 640px) {
    .block-container {padding-top: 1.1rem; padding-left: .7rem; padding-right: .7rem;}
    div[data-testid="stMetricValue"] {font-size: 1.15rem;}
    div[data-testid="stMetricLabel"] p {font-size: 0.72rem;}
    button[data-baseweb="tab"] p {font-size: 0.78rem;}
  }
</style>
""", unsafe_allow_html=True)


# ==========================================================================
# cached loaders — every read is cached, the app runs entirely offline
# ==========================================================================

@st.cache_data(show_spinner="Loading corners…")
def get_corners(filtered: bool = True) -> pd.DataFrame:
    return F.load_corners(filtered)


@st.cache_data(show_spinner="Loading road grid…")
def get_grid() -> pd.DataFrame:
    return F.load_grid()


@st.cache_data(show_spinner="Indexing rides…")
def get_trips() -> pd.DataFrame:
    return F.load_trip_index()


@st.cache_data(show_spinner="Loading ride telemetry…", max_entries=6)
def get_trip(trip_id: str, max_points: int = 2000):
    df = F.load_trip(trip_id, max_points)
    return df, dict(df.attrs)


@st.cache_data(show_spinner=False)
def get_manifest() -> pd.DataFrame:
    return F.load_manifest()


@st.cache_data(show_spinner=False)
def get_asymmetry(scope: str) -> dict:
    return F.lr_asymmetry(subset_for(scope))


@st.cache_data(show_spinner=False)
def get_radar(scope: str) -> pd.DataFrame:
    return F.radar_profile(subset_for(scope), get_corners(True))


def subset_for(scope: str) -> pd.DataFrame:
    c = get_corners(True)
    if scope.startswith("Bike "):
        return c[c["bike"] == scope.split(" ")[1]]
    return c


@st.cache_data(show_spinner=False)
def dna_for(scope: str) -> F.RiderDNA:
    c = get_corners(True)
    return F.rider_dna(subset_for(scope), label=scope, fallback_sigma=float(c["lean_deg"].std()))


# ==========================================================================
# map helpers — pydeck when it works, plotly when there is no GPU/tiles
# ==========================================================================

def view_for(lat: pd.Series, lon: pd.Series, width_px: int = 700,
             height_px: int = 430, pad: float = 0.35):
    """
    Fit a bounding box to the actual canvas. At zoom z one tile is 256 px and
    spans 360/2^z degrees of longitude, so the zoom that fits a box is
    log2(px * 360 / (256 * span)) — forgetting the pixel term is what makes an
    auto-fitted deck.gl map open zoomed out over half of Europe.
    """
    lat, lon = pd.Series(lat).dropna(), pd.Series(lon).dropna()
    if lat.empty:
        return 48.14, 11.58, 7.0
    clat = float((lat.max() + lat.min()) / 2)
    clon = float((lon.max() + lon.min()) / 2)
    lat_span = max(float(lat.max() - lat.min()), 1e-3)
    lon_span = max(float(lon.max() - lon.min()), 1e-3)
    cos = max(np.cos(np.radians(clat)), 0.1)
    z_lon = np.log2(width_px * 360.0 / (256.0 * lon_span))
    z_lat = np.log2(height_px * 360.0 * cos / (256.0 * lat_span))
    return clat, clon, float(np.clip(min(z_lon, z_lat) - pad, 2.0, 15.0))


def render_map(layers, lat_c, lon_c, zoom, fallback: pd.DataFrame,
               color_col: str | None = None, height: int = 480, key: str | None = None,
               tooltip: dict | None = None, fallback_line: pd.DataFrame | None = None,
               crange: tuple | None = None):
    """
    Draw the deck. If pydeck is unavailable or throws, fall back to a plain
    lat/lon scatter that needs no tiles and no GPU — the demo never dies
    because the network is unplugged.
    """
    renderer = st.session_state.get("renderer", "pydeck")
    if HAS_PYDECK and renderer == "pydeck":
        try:
            basemap = st.session_state.get("basemap", True)
            deck = pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(latitude=lat_c, longitude=lon_c,
                                                 zoom=zoom, pitch=0, bearing=0),
                map_provider="carto" if basemap else None,
                map_style="dark" if basemap else None,
                tooltip=tooltip or {"text": "{tip}"},
            )
            st.pydeck_chart(deck, height=height, key=key)
            return
        except Exception as exc:                       # pragma: no cover
            st.caption(f"pydeck unavailable ({type(exc).__name__}) — drawing the offline map instead.")

    fig = go.Figure()
    if fallback_line is not None and not fallback_line.empty:
        fig.add_trace(go.Scattergl(x=fallback_line["lon"], y=fallback_line["lat"],
                                   mode="lines", line=dict(color="rgba(140,150,175,0.45)",
                                                           width=1),
                                   hoverinfo="skip", name="route"))
    if not fallback.empty:
        colors = fallback[color_col] if color_col and color_col in fallback else BLUE
        mk = dict(size=6, color=colors)
        if color_col:
            mk.update(colorscale="Turbo", showscale=True,
                      colorbar=dict(title=color_col, thickness=12))
            if crange:
                mk.update(cmin=crange[0], cmax=crange[1])
        fig.add_trace(go.Scattergl(
            x=fallback["lon"], y=fallback["lat"], mode="markers", marker=mk,
            hovertext=fallback.get("tip"), hoverinfo="text", name="",
        ))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0),
                      xaxis_title="longitude", yaxis_title="latitude",
                      showlegend=False)
    fig.update_yaxes(scaleanchor="x", scaleratio=1.0 / max(np.cos(np.radians(lat_c)), .1))
    st.plotly_chart(fig, key=key, config={"displayModeBar": False})


def band_figure(z_star: float, tau: float, z_now: float | None = None,
                gate_z: float = F.GATE_SIGMAS, height: int = 300,
                title: str = "") -> go.Figure:
    """The flow kernel with BOREDOM / FLOW / RISK annotated, plus a live marker."""
    z, f = F.flow_curve(z_star, tau)
    fig = go.Figure()
    fig.add_vrect(x0=-4, x1=z_star - tau, fillcolor=GREY, opacity=0.13, line_width=0,
                  annotation_text="BOREDOM", annotation_position="top left",
                  annotation_font_size=11)
    fig.add_vrect(x0=z_star - tau, x1=z_star + tau, fillcolor=TEAL, opacity=0.18, line_width=0,
                  annotation_text="FLOW", annotation_position="top left",
                  annotation_font_size=11)
    fig.add_vrect(x0=z_star + tau, x1=4, fillcolor=RED, opacity=0.13, line_width=0,
                  annotation_text="RISK", annotation_position="top right",
                  annotation_font_size=11)
    fig.add_vline(x=gate_z, line_dash="dot", line_color=RED,
                  annotation_text=f"safety gate  +{gate_z:g}σ", annotation_font_size=10)
    fig.add_trace(go.Scatter(x=z, y=f, mode="lines", line=dict(color=BLUE, width=3),
                             name="flow", hovertemplate="z=%{x:.2f}<br>flow=%{y:.2f}<extra></extra>"))
    fig.add_vline(x=z_star, line_dash="dash", line_color=GOLD)
    if z_now is not None and np.isfinite(z_now):
        y_now = float(np.exp(-((z_now - z_star) ** 2) / (2 * tau ** 2)))
        if z_now > gate_z:
            y_now = 0.0
        fig.add_trace(go.Scatter(x=[z_now], y=[y_now], mode="markers",
                                 marker=dict(size=17, color=GOLD, line=dict(color="white", width=2)),
                                 name="now", hovertemplate="now: z=%{x:.2f}<extra></extra>"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30 if title else 10, b=10),
                      showlegend=False, title=title,
                      xaxis_title="z  =  (corner demand − rider skill) / σ",
                      yaxis_title="flow", yaxis_range=[0, 1.12], xaxis_range=[-4, 4])
    return fig


def tag(text: str, color: str) -> str:
    return f'<span class="fs-tag" style="background:{color}22;color:{color};border:1px solid {color}55">{text}</span>'


# ==========================================================================
# sidebar — the single source of truth for the Thrill Dial
# ==========================================================================

corners = get_corners(True)
trips = get_trips()

# widget defaults must exist BEFORE the widgets are created
for _k, _v in [("z_star", 0.50), ("tau", 0.50), ("basemap", True),
               ("renderer_choice", "pydeck"), ("frame", 0), ("playing", False)]:
    st.session_state.setdefault(_k, _v)

with st.sidebar:
    st.markdown(f"## 🏍 FLOWSTATE\n**Fun is the *fit* between road and rider.**")

    st.markdown("#### Rider")
    bikes = (corners["bike"].value_counts())
    bike_opts = [f"Bike {b} · {n} corners" for b, n in bikes.items() if n >= 50]
    scope_label = st.selectbox(
        "Whose skill are we scoring against?",
        ["User A — all rides"] + bike_opts,
        help="User A is an internal test rider on 15 bikes. Lean p95 on an S1000RR "
             "and on an R18 are not the same measurement, so bike confounds skill — "
             "split the profile per bike to see it.")
    scope = "User A" if scope_label.startswith("User A") else scope_label.split(" ")[0] + " " + scope_label.split(" ")[1]
    dna = dna_for(scope)

    st.markdown("#### Thrill Dial")
    z_star = st.slider("z★ — how far above skill to aim", 0.0, 1.2,
                       key="z_star", step=0.05,
                       help="Flow theory: people are in flow when the challenge sits "
                            "slightly ABOVE their skill. 0.15 Cruise · 0.50 Flow · 0.90 Send it.")
    tau = st.slider("τ — width of the flow band", 0.2, 1.0, key="tau", step=0.05)

    st.divider()
    st.markdown("#### This rider")
    c1, c2 = st.columns(2)
    c1.metric("Lean p95 L", f"{dna.skill_left:.1f}°")
    c2.metric("Lean p95 R", f"{dna.skill_right:.1f}°")
    c1.metric("σ", f"{dna.sigma:.1f}°")
    c2.metric("Headroom", f"{dna.headroom:.1f}°", help="2σ — the distance to the safety gate")
    st.caption(f"{dna.n_corners:,} corners · {dna.n_rides} rides · {dna.n_bikes} bikes")

    st.divider()
    st.markdown("#### Display")
    st.toggle("Basemap tiles", key="basemap",
              help="OFF = fully offline. Layers still draw without tiles.")
    st.radio("Map renderer", ["pydeck", "plotly (no tiles)"], key="renderer_choice",
             horizontal=True, label_visibility="collapsed")
    st.session_state["renderer"] = ("pydeck" if st.session_state.get("renderer_choice", "pydeck")
                                    == "pydeck" else "plotly")
    st.caption("BMW data is under NDA — nothing leaves this machine. "
               "The only network call this app can make is a map tile.")


z_star = float(st.session_state["z_star"])
tau = float(st.session_state["tau"])

st.markdown(
    f"#### FLOWSTATE &nbsp;·&nbsp; <span style='color:{GREY};font-weight:400'>"
    f"one curve that scores fun <i>and</i> safety, in degrees of lean</span>",
    unsafe_allow_html=True)

# ROUTE goes first: it is the only tab that answers the question BMW asked.
TAB_ROUTE, TAB_REPLAY, TAB_DNA, TAB_DIAL, TAB_GRID = st.tabs(
    ["🛣 ROUTE", "🎬 RIDE REPLAY", "🧬 RIDER DNA", "🎚 THRILL DIAL", "🗺 ROAD GRID"])


# ==========================================================================
# 0 — ROUTE  (use case A: A->B, use case B: a loop for X hours)
# ==========================================================================

with TAB_ROUTE:
    route_tab.render()


# ==========================================================================
# 1 — RIDE REPLAY
# ==========================================================================

with TAB_REPLAY:
    st.caption("A real recorded BMW ride, replayed from its own telemetry. "
               "The path is coloured by how well each metre fitted **this** rider.")

    ride_labels = trips["label"].tolist()
    chosen = st.selectbox("Ride", ride_labels, index=0, key="ride_pick")
    row = trips.iloc[ride_labels.index(chosen)]
    trip_id = row["trip_id"]

    trip_raw, meta = get_trip(trip_id)

    if trip_raw.empty:
        st.error("No usable trackpoints in this ride.")
    else:
        ride = F.score_trip(trip_raw, dna, z_star, tau)

        if st.session_state.get("replay_trip") != trip_id:
            st.session_state["replay_trip"] = trip_id
            st.session_state["frame"] = 0
            st.session_state["playing"] = False
        st.session_state.setdefault("frame", 0)
        st.session_state.setdefault("playing", False)

        if "GPS-derived" in meta.get("speed_source", ""):
            st.warning(f"Speed channel dead on this ride — using {meta['speed_source']}. "
                       "27 of user A's 100 rides are like this; it is not in BMW's README.")
        if not meta.get("lean_ok", True):
            st.warning("The lean channel is flat on this ride — the rider trace will be empty, "
                       "but the road's demand is still computed from speed and yaw rate.")

        # NOTE: everything the fragment needs is passed IN. A fragment rerun does
        # not re-execute the rest of the script, so a bare global would resolve to
        # whatever a later tab last assigned to that name.
        @st.fragment
        def replay_panel(ride, meta, dna, z_star, tau, trip_id):
            n = len(ride)
            frame = int(np.clip(st.session_state["frame"], 0, n - 1))
            cur = ride.iloc[frame]

            ctl = st.columns([1, 1, 1, 2, 5])
            playing = st.session_state["playing"]
            if ctl[0].button("⏸ Pause" if playing else "▶ Play", width="stretch",
                             type="primary" if not playing else "secondary"):
                st.session_state["playing"] = not playing
                st.rerun(scope="fragment")
            if ctl[1].button("⏮ Reset", width="stretch"):
                st.session_state["frame"] = 0
                st.session_state["playing"] = False
                st.rerun(scope="fragment")
            speed_mult = ctl[2].selectbox("Speed", [1, 2, 5, 10, 25, 50], index=3,
                                          key="speed_mult", label_visibility="collapsed")
            # dynamic key: the scrubber is rebuilt at the current frame each tick, so
            # dragging it moves the animation instead of fighting it
            new_frame = ctl[3].slider("Position", 0, max(n - 1, 1), frame,
                                      key=f"scrub_{trip_id}_{frame}",
                                      label_visibility="collapsed")
            if new_frame != frame:
                st.session_state["frame"] = new_frame
                frame = new_frame
                cur = ride.iloc[frame]
            ctl[4].markdown(
                f"**{cur['km']:.1f} km** into the ride &nbsp;·&nbsp; "
                f"t+{int(cur['t_s'] // 60):02d}:{int(cur['t_s'] % 60):02d} &nbsp;·&nbsp; "
                f"frame {frame + 1} / {n} &nbsp;·&nbsp; "
                f"<span style='color:{GREY}'>{meta['raw_points']:,} raw points "
                f"→ {meta.get('trimmed_points', 0):,} parked ones trimmed → {n} frames</span>",
                unsafe_allow_html=True)

            # ---- live gauges -------------------------------------------------
            g = st.columns(7)
            g[0].metric("Speed", f"{cur['kmh']:.0f} km/h")
            lean = cur["lean_deg"]
            side = "" if not np.isfinite(lean) else (" R" if lean > 0 else " L")
            g[1].metric("Lean", "—" if not np.isfinite(lean) else f"{abs(lean):.0f}°{side}")
            g[2].metric("Demand", f"{cur['req_deg']:.0f}°",
                        help="arctan(v·ω/g) — what the road asks for")
            g[3].metric("Throttle", f"{cur['throttle']:.0f} %")
            g[4].metric("Gear", "—" if not np.isfinite(cur["gear"]) or cur["gear"] <= 0
                        else f"{int(cur['gear'])}")
            abs_hit = int(cur["abs_code"]) == 3
            g[5].metric("ABS", cur["abs_label"], delta="LIMIT" if abs_hit else None,
                        delta_color="inverse")
            flow_now = cur["flow"]
            g[6].metric("FLOW", "—" if not np.isfinite(flow_now) else f"{flow_now:.2f}",
                        delta=cur["band"] if np.isfinite(flow_now) else None,
                        delta_color="off")

            left, right = st.columns([3, 2])

            # ---- map ---------------------------------------------------------
            with left:
                done = ride.iloc[:frame + 1]
                colors = F.flow_color(done["flow"].fillna(0.0), alpha=220)
                pts = pd.DataFrame({
                    "lat": done["lat"], "lon": done["lon"],
                    "r": [c[0] for c in colors], "g": [c[1] for c in colors],
                    "b": [c[2] for c in colors],
                    "tip": [f"{k:.1f} km · demand {q:.0f}° · flow {fl:.2f}"
                            for k, q, fl in zip(done["km"], done["req_deg"],
                                                done["flow"].fillna(0))],
                    "flow": done["flow"].fillna(0.0),
                })
                lat_c, lon_c, zoom = view_for(ride["lat"], ride["lon"], 700, 430)
                # the ridden trail as a coloured PATH, not dots: one segment per
                # frame, coloured by the flow this rider was in on that segment
                seg = [{"path": [[float(pts["lon"].iat[i]), float(pts["lat"].iat[i])],
                                 [float(pts["lon"].iat[i + 1]), float(pts["lat"].iat[i + 1])]],
                        "color": [int(pts["r"].iat[i + 1]), int(pts["g"].iat[i + 1]),
                                  int(pts["b"].iat[i + 1])]}
                       for i in range(len(pts) - 1)]
                hot = pts[pts["flow"] > 0.5]
                layers = []
                if HAS_PYDECK:
                    layers = [
                        pdk.Layer("PathLayer",
                                  data=[{"path": ride[["lon", "lat"]].values.tolist()}],
                                  get_path="path", get_color=[72, 80, 96],
                                  width_min_pixels=1, get_width=3, pickable=False),
                        pdk.Layer("PathLayer", data=seg, get_path="path",
                                  get_color="color", width_min_pixels=3, get_width=9,
                                  pickable=False),
                        pdk.Layer("ScatterplotLayer", data=hot,
                                  get_position=["lon", "lat"],
                                  get_fill_color=[255, 210, 63, 235],
                                  get_radius=140, radius_min_pixels=4, radius_max_pixels=11,
                                  pickable=True),
                        pdk.Layer("ScatterplotLayer",
                                  data=done.loc[done["abs_code"] == 3, ["lat", "lon"]]
                                      .assign(tip="ABS limit event"),
                                  get_position=["lon", "lat"],
                                  get_fill_color=[232, 82, 63, 255],
                                  get_radius=160, radius_min_pixels=6, pickable=True),
                        pdk.Layer("ScatterplotLayer",
                                  data=pd.DataFrame([{"lat": cur["lat"], "lon": cur["lon"],
                                                      "tip": "the bike, now"}]),
                                  get_position=["lon", "lat"],
                                  get_fill_color=[255, 255, 255, 255],
                                  get_radius=200, radius_min_pixels=7, pickable=False),
                    ]
                render_map(layers, lat_c, lon_c, zoom, fallback=pts, color_col="flow",
                           height=430, key=f"replaymap_{trip_id}",
                           fallback_line=ride[["lat", "lon"]], crange=(0.0, 1.0))
                st.caption(f"Dim line = the whole route. Bright trail = ridden so far, "
                           f"coloured by flow — **gold** where this rider was in the band, "
                           f"slate where the road was below them. Gold dots mark the "
                           f"{len(hot)} flow moments so far; red dots are ABS limit events.")

            # ---- flow curve + traces ----------------------------------------
            with right:
                st.plotly_chart(band_figure(z_star, tau, z_now=cur["z"], height=270),
                                key=f"band_{trip_id}", config={"displayModeBar": False})
                w = 120
                lo_i, hi_i = max(0, frame - w), frame + 1
                win = ride.iloc[lo_i:hi_i]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=win["km"], y=win["req_deg"], name="road demand",
                                         line=dict(color=RED, width=2)))
                fig.add_trace(go.Scatter(x=win["km"], y=win["lean_abs"], name="rider lean",
                                         line=dict(color=BLUE, width=2)))
                fig.add_hline(y=dna.skill_left, line_dash="dot", line_color=GOLD,
                              annotation_text="skill p95", annotation_font_size=10)
                fig.update_layout(height=210, margin=dict(l=10, r=10, t=26, b=10),
                                  title="last 2 km — demand vs rider, degrees",
                                  xaxis_title="km", yaxis_title="°",
                                  legend=dict(orientation="h", y=1.16, x=0))
                st.plotly_chart(fig, key=f"trace_{trip_id}", config={"displayModeBar": False})

            # ---- the animation loop -----------------------------------------
            if st.session_state["playing"]:
                nxt = frame + int(speed_mult)
                if nxt >= n - 1:
                    st.session_state["frame"] = n - 1
                    st.session_state["playing"] = False
                else:
                    st.session_state["frame"] = nxt
                    time.sleep(0.02)
                st.rerun(scope="fragment")

        replay_panel(ride, meta, dna, z_star, tau, trip_id)


# ==========================================================================
# 2 — RIDER DNA
# ==========================================================================

with TAB_DNA:
    sub = subset_for(scope)
    st.caption(f"Profile built from **{len(sub):,} corners** of {scope_label}. "
               "Skill is lean p95 per direction — a p95, not a max, because per-ride "
               "maxima are noise-dominated.")

    m = st.columns(6)
    m[0].metric("Lean p95", f"{dna.skill_all:.1f}°")
    m[1].metric("Left / Right", f"{dna.skill_left:.0f}° / {dna.skill_right:.0f}°")
    m[2].metric("σ (lean sd)", f"{dna.sigma:.1f}°")
    m[3].metric("Headroom to gate", f"{dna.headroom:.1f}°")
    m[4].metric("ABS limit events", f"{dna.abs_events}",
                help="ridingabsbraking == 3 — the only unambiguous hard-braking code")
    m[5].metric("Bikes / rides", f"{dna.n_bikes} / {dna.n_rides}")
    for note in dna.notes:
        st.info(note)

    c_hist, c_radar = st.columns([3, 2])

    with c_hist:
        left = sub.loc[sub["dir_name"] == "LEFT", "lean_deg"].dropna()
        right = sub.loc[sub["dir_name"] == "RIGHT", "lean_deg"].dropna()
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=left, name=f"LEFT (n={len(left)})", opacity=0.62,
                                   marker_color=BLUE, nbinsx=45, histnorm="probability density"))
        fig.add_trace(go.Histogram(x=right, name=f"RIGHT (n={len(right)})", opacity=0.62,
                                   marker_color=GOLD, nbinsx=45, histnorm="probability density"))
        fig.add_vline(x=dna.skill_left, line_color=BLUE, line_dash="dash",
                      annotation_text=f"L p95 {dna.skill_left:.1f}°", annotation_position="top")
        fig.add_vline(x=dna.skill_right, line_color=GOLD, line_dash="dash",
                      annotation_text=f"R p95 {dna.skill_right:.1f}°", annotation_position="bottom")
        fig.update_layout(barmode="overlay", height=380,
                          margin=dict(l=10, r=10, t=66, b=10),
                          title=dict(text="Lean angle used, left vs right corners", y=0.97),
                          xaxis_title="lean (°, magnitude — sign stripped, + is RIGHT in the raw signal)",
                          yaxis_title="density",
                          legend=dict(orientation="h", y=1.06, x=0))
        st.plotly_chart(fig, config={"displayModeBar": False})

    with c_radar:
        rad = get_radar(scope)
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=rad["score"].tolist() + [rad["score"].iloc[0]],
            theta=rad["axis"].tolist() + [rad["axis"].iloc[0]],
            fill="toself", line=dict(color=BLUE, width=2),
            fillcolor="rgba(28,105,212,0.28)", name=scope,
            hovertext=[f"{a}: {v:.1f}" for a, v in zip(rad["axis"], rad["value"])] + [""],
            hoverinfo="text"))
        fig.update_layout(height=380, margin=dict(l=40, r=40, t=40, b=20),
                          title="Rider profile, six axes",
                          paper_bgcolor="rgba(0,0,0,0)",
                          polar=dict(bgcolor="rgba(127,140,170,0.10)",
                                     angularaxis=dict(gridcolor="rgba(150,160,185,0.35)"),
                                     radialaxis=dict(visible=True, range=[0, 100],
                                                     showticklabels=False,
                                                     gridcolor="rgba(150,160,185,0.30)")))
        st.plotly_chart(fig, config={"displayModeBar": False})
        with st.expander("What each axis actually measures"):
            st.dataframe(rad[["axis", "value", "score", "what"]].round(1),
                         hide_index=True)
            st.caption("Scores are scaled 0–100 against the 5th–95th percentile of the "
                       "**same statistic computed per ride across this dataset** — one "
                       "rider, 15 bikes. It is not a percentile against the human race, "
                       "and we do not pretend it is.")

    st.divider()
    st.markdown("### Is this rider left/right asymmetric?")

    a = get_asymmetry(scope)
    if not a.get("ok"):
        st.info(f"Not enough corners to answer honestly ({a.get('reason')}).")
    else:
        man_a = F.manifest_asymmetry(get_manifest()) if scope == "User A" else None
        verdict_sig = a["significant"]
        # robustness: do the estimators even agree on the SIGN?
        signs = [np.sign(a["diff"])]
        if a["per_ride"]:
            signs.append(np.sign(a["per_ride"]["mean"]))
        if man_a:
            signs.append(np.sign(man_a["mean"]))
        sign_stable = len(set(signs)) == 1
        act = verdict_sig and sign_stable and abs(a["diff"]) >= 2.0

        cc = st.columns([2, 3])
        with cc[0]:  # noqa: SIM117
            st.metric("p95 LEFT − p95 RIGHT", f"{a['diff']:+.2f}°",
                      help="Positive = stronger on left-hand corners")
            st.markdown(f"**95% CI (clustered on ride): [{a['lo']:+.2f}°, {a['hi']:+.2f}°]**")
            if act:
                st.success("Significant, sign-stable and large enough to act on — "
                           "we would flip the loop direction for this rider.")
            elif verdict_sig and not sign_stable:
                st.error("**DO NOT ACT.** The interval clears zero on this estimator, but "
                         "the estimators disagree on the *sign*. That is not an asymmetry, "
                         "that is noise wearing a confidence interval.")
            elif verdict_sig:
                st.warning("Interval clears zero, but the effect is ≈1° — smaller than the "
                           "measurement noise on a single corner. We report it; we do not "
                           "route on it.")
            else:
                st.info("**Not significant.** The interval spans zero. We report the "
                        "interval and refuse to act inside it.")
        with cc[1]:
            st.markdown("**The same quantity, four ways.** If they disagree, the effect "
                        "is not there — and the table is how you find that out before a "
                        "judge does.")
            rows = [{
                "estimator": f"Per-corner p95, bootstrap clustered on ride (n={a['n_rides']} rides, "
                             f"{a['n_left'] + a['n_right']:,} corners)",
                "estimate": a["diff"], "lo": a["lo"], "hi": a["hi"],
                "verdict": "clears 0" if a["significant"] else "spans 0"}]
            rows.append({
                "estimator": "Same thing NOT clustered — corners treated as independent",
                "estimate": a["diff"], "lo": a["naive_lo"], "hi": a["naive_hi"],
                "verdict": "too tight (not independent)"})
            if a["per_ride"]:
                rows.append({"estimator": f"Mean of per-ride p95 differences (n={a['per_ride']['n']} rides)",
                             "estimate": a["per_ride"]["mean"], "lo": a["per_ride"]["lo"],
                             "hi": a["per_ride"]["hi"],
                             "verdict": "clears 0" if a["per_ride"]["lo"] * a["per_ride"]["hi"] > 0 else "spans 0"})
            if man_a:
                rows.append({"estimator": f"BMW's own leanAngleLeftMax − RightMax (n={man_a['n']} rides)",
                             "estimate": man_a["mean"], "lo": man_a["lo"], "hi": man_a["hi"],
                             "verdict": "clears 0" if man_a["significant"] else "spans 0 — SIGN FLIPS"})
            _tbl = pd.DataFrame(rows).round(2)
        st.dataframe(_tbl, hide_index=True,
                     column_config={
                             "estimator": st.column_config.TextColumn("estimator", width="large"),
                             "estimate": st.column_config.NumberColumn("Δ (°)", format="%+.2f", width="small"),
                             "lo": st.column_config.NumberColumn("CI lo", format="%+.2f", width="small"),
                             "hi": st.column_config.NumberColumn("CI hi", format="%+.2f", width="small"),
                             "verdict": st.column_config.TextColumn("verdict", width="medium")})
        st.caption("On user A these estimators disagree on the sign and all sit inside ±1.2°. "
                   "`docs/08_DATA_FINDINGS.md` §2.1 measured exactly this. The mechanism is real "
                   "— BMW store the two maxima themselves — but for **this** rider we report the "
                   "interval instead of claiming the effect.")


# ==========================================================================
# 3 — THRILL DIAL
# ==========================================================================

def _set_dial(value: float):
    st.session_state["z_star"] = value


with TAB_DIAL:
    st.caption(f"Re-scoring all **{len(corners):,}** real road corners on every change. "
               "Same curve, one knob.")

    b = st.columns([1, 1, 1, 4])
    for i, (name, val) in enumerate(F.Z_PRESETS.items()):
        b[i].button(f"{name}  (z★={val})", key=f"preset_{name}", width="stretch",
                    on_click=_set_dial, args=(val,),
                    type="primary" if abs(z_star - val) < 1e-6 else "secondary")
    b[3].markdown(f"<div style='padding-top:6px'>Dial is at <b>z★ = {z_star:.2f}</b>, "
                  f"band width <b>τ = {tau:.2f}</b> — "
                  f"target demand ≈ <b>{dna.skill_all + z_star * dna.sigma:.1f}°</b> of lean "
                  f"(this rider's p95 is {dna.skill_all:.1f}°). "
                  f"Move the sliders in the sidebar for anything in between.</div>",
                  unsafe_allow_html=True)

    corner_scores = F.score_corners(corners, dna, z_star, tau)
    fcol = st.columns([2, 3])
    dial_region = fcol[0].selectbox("Region", list(F.REGIONS.keys()), key="dial_region")
    top_n = fcol[1].slider("How many corners to map", 50, 1000, 300, step=50)
    # the rider's skill is always measured on ALL their corners; the region only
    # decides what we show
    corner_scores = F.apply_region(corner_scores, dial_region)
    best = corner_scores.nlargest(min(top_n, len(corner_scores)), "flow")

    k = st.columns(6)
    k[0].metric("In the flow band", f"{int((corner_scores['band'] == 'FLOW').sum()):,}",
                help="within ±τ of z★")
    k[1].metric("Excluded by the gate", f"{int(corner_scores['gated'].sum()):,}",
                delta="demand > skill + 2σ", delta_color="off")
    k[2].metric("Top-set mean demand", f"{best['req_deg'].mean():.1f}°")
    k[3].metric("Top-set mean elevation", f"{best['elev_m'].mean():.0f} m")
    k[4].metric("Top-set centroid", f"{best['lat'].mean():.2f}°N")
    k[5].metric("…longitude", f"{best['lon'].mean():.2f}°E")
    st.caption("Watch the centroid: the selection walks south out of Munich and into the "
               "Alps as the dial goes up — 47.16°N at Cruise, 46.88°N at Send it. "
               "Nothing about geography is in the model; it falls out of the lean demand.")

    c_map, c_tab = st.columns([3, 2])
    with c_map:
        colors = F.flow_color(best["flow"], alpha=210)
        pts = best[["lat", "lon", "flow"]].assign(
            r=[c[0] for c in colors], g=[c[1] for c in colors], b=[c[2] for c in colors],
            rad=(best["req_deg"] * 22).clip(150, 1400).to_numpy(),
            tip=[f"{r.req_deg:.0f}° demanded · flow {r.flow:.2f} · {r.elev_m:.0f} m · {r.dir_name}"
                 for r in best.itertuples()])
        lat_c, lon_c, zoom = view_for(best["lat"], best["lon"], 700, 430)
        layers = []
        if HAS_PYDECK:
            gated_pts = corner_scores.loc[corner_scores["gated"], ["lat", "lon", "req_deg"]].assign(
                tip="EXCLUDED — over the safety gate")
            layers = [
                pdk.Layer("ScatterplotLayer", data=corner_scores[["lat", "lon"]],
                          get_position=["lon", "lat"], get_fill_color=[90, 96, 110, 55],
                          get_radius=90, radius_min_pixels=1, pickable=False),
                pdk.Layer("ScatterplotLayer", data=gated_pts, get_position=["lon", "lat"],
                          get_fill_color=[232, 82, 63, 150], get_radius=260,
                          radius_min_pixels=3, pickable=True),
                pdk.Layer("ScatterplotLayer", data=pts, get_position=["lon", "lat"],
                          get_fill_color=["r", "g", "b", 220], get_radius="rad",
                          radius_min_pixels=3, radius_max_pixels=16, pickable=True),
            ]
        render_map(layers, lat_c, lon_c, zoom, fallback=pts, color_col="flow",
                   height=430, key="dialmap", crange=(0.0, 1.0))
        st.caption("Grey = every corner user A has ever ridden. Gold = the best fit at this "
                   "dial setting. Red = excluded by the safety gate, at any dial setting.")

    with c_tab:
        show = best.nlargest(15, "flow")[
            ["corner_id", "lat", "lon", "req_deg", "elev_m", "radius_m", "dir_name", "flow"]]
        st.markdown("**The 15 best-fitting corners right now**")
        st.dataframe(show.round({"lat": 4, "lon": 4, "req_deg": 1, "elev_m": 0,
                                 "radius_m": 0, "flow": 3}),
                     hide_index=True, height=330,
                     column_config={"req_deg": st.column_config.NumberColumn("demand °"),
                                    "elev_m": st.column_config.NumberColumn("elev m"),
                                    "radius_m": st.column_config.NumberColumn("radius m"),
                                    "dir_name": "dir"})

    st.divider()
    st.markdown("### Why this corner?")
    pool = pd.concat([best.nlargest(15, "flow"),
                      corner_scores[corner_scores["gated"]].nlargest(5, "req_deg")]).drop_duplicates("corner_id")
    pick = st.selectbox(
        "Corner",
        pool["corner_id"].tolist(),
        format_func=lambda cid: (
            f"{cid} — {pool.loc[pool.corner_id == cid, 'req_deg'].iloc[0]:.0f}° demanded"
            + ("  ⛔ gated" if bool(pool.loc[pool.corner_id == cid, 'gated'].iloc[0]) else "")))
    r = pool[pool["corner_id"] == pick].iloc[0]

    w = st.columns([2, 2, 3])
    with w[0]:
        st.metric("Corner demands", f"{r['req_deg']:.1f}°",
                  help="arctan(v²/(R·g)) measured at the speed real riders took it")
        st.metric("This rider's skill", f"{r['skill']:.1f}°",
                  help=f"lean p95 on {r['dir_name']} corners")
        st.metric("σ", f"{dna.sigma:.1f}°")
    with w[1]:
        st.metric("z", f"{r['z']:+.2f}",
                  help="(demand − skill) / σ")
        st.metric("flow", f"{r['flow']:.3f}")
        st.metric("Safety gate at", f"{r['gate_deg']:.1f}°")
    with w[2]:
        if r["gated"]:
            st.error(f"**SAFETY GATE FIRED.** This corner demands {r['req_deg']:.1f}°, which is "
                     f"more than {r['skill']:.1f}° + 2σ = {r['gate_deg']:.1f}°. "
                     f"It is excluded at every dial setting — the dial cannot unlock it. "
                     f"That is the whole point: the number that measures fun is the same "
                     f"number that measures risk, so the safety rule is *inside* the score, "
                     f"not bolted on afterwards.")
        else:
            st.success(f"**Kept.** {r['req_deg']:.1f}° demanded vs {r['skill']:.1f}° of skill "
                       f"is z = {r['z']:+.2f}, and the dial is set to z★ = {z_star:.2f}. "
                       f"Distance from the target band centre: {abs(r['z'] - z_star):.2f}σ "
                       f"→ flow {r['flow']:.3f}. Band: **{r['band']}**.")
        st.plotly_chart(band_figure(z_star, tau, z_now=float(r["z"]), height=250),
                        key="why_band", config={"displayModeBar": False})
        st.caption(f"{r['lat']:.4f}°N {r['lon']:.4f}°E · {r['elev_m']:.0f} m · "
                   f"radius {r['radius_m']:.0f} m · taken at {r['v_ms'] * 3.6:.0f} km/h · "
                   f"{r['dir_name']} · ridden on bike {r['bike']}")


# ==========================================================================
# 4 — ROAD GRID
# ==========================================================================

with TAB_GRID:
    grid = get_grid()
    st.caption("**Road DNA built from ride telemetry alone — no OpenStreetMap.** "
               "Every cell is a Morton-coded patch of road, and everything in it "
               "(how much lean it demands, how tight, how steep, where riders hit the "
               "limit) was measured by motorcycles going past.")

    f1, f2, f3 = st.columns([2, 2, 3])
    region = f1.selectbox("Region", list(F.REGIONS.keys()))
    min_rides = f2.slider("Minimum rides through the cell", 1, 10, 1,
                          help="More rides = more confidence in the cell's numbers")
    gsub = F.apply_region(grid, region)
    gsub = gsub[gsub["rides"] >= min_rides]
    hazards = gsub[gsub["abs_events"] > 0]
    f3.markdown(f"<div style='padding-top:24px'><b>{len(gsub):,}</b> cells · "
                f"<b>{int(gsub['n_corners'].sum()):,}</b> corners · "
                f"<span style='color:{RED}'><b>{len(hazards)}</b> hazard cells</span> "
                f"(≥1 ABS limit event)</div>", unsafe_allow_html=True)

    if gsub.empty:
        st.info("No cells in this region at this filter.")
    else:
        colors = F.demand_color(gsub["demand_p90"], vmin=float(grid["demand_p90"].quantile(.05)),
                                vmax=float(grid["demand_p90"].quantile(.95)))
        gpts = gsub[["lat", "lon", "demand_p90"]].assign(
            r=[c[0] for c in colors], g=[c[1] for c in colors], b=[c[2] for c in colors],
            tip=[f"demand p90 {x.demand_p90:.0f}° · p50 {x.demand_p50:.0f}° · "
                 f"radius {x.radius_p50:.0f} m · {x.elev:.0f} m · {x.rides} rides"
                 f"{' · ABS LIMIT ×' + str(x.abs_events) if x.abs_events else ''}"
                 for x in gsub.itertuples()])
        lat_c, lon_c, zoom = view_for(gsub["lat"], gsub["lon"], 1200, 470)
        layers = []
        if HAS_PYDECK:
            layers = [
                pdk.Layer("ScatterplotLayer", data=gpts, get_position=["lon", "lat"],
                          get_fill_color=["r", "g", "b", 200],
                          get_radius="demand_p90 * 30", radius_min_pixels=3,
                          radius_max_pixels=18, pickable=True),
                pdk.Layer("ScatterplotLayer", data=hazards[["lat", "lon"]].assign(
                    tip=["⚠ " + str(int(x.abs_events)) + " ABS limit event(s) here"
                         for x in hazards.itertuples()]),
                    get_position=["lon", "lat"], get_fill_color=[255, 60, 40, 240],
                    get_radius=900, radius_min_pixels=8, stroked=True,
                    get_line_color=[255, 255, 255], line_width_min_pixels=2, pickable=True),
            ]
        render_map(layers, lat_c, lon_c, zoom, fallback=gpts, color_col="demand_p90",
                   height=470, key="gridmap")

        lg1, lg2 = st.columns([3, 2])
        lg1.markdown(
            f"{tag('LOW DEMAND', BLUE)} → {tag('HIGH DEMAND', RED)} &nbsp;&nbsp; "
            f"colour and size are the cell's **p90 required lean**. "
            f"{tag('⚠ HAZARD', RED)} = a cell where a rider hit the ABS limit.",
            unsafe_allow_html=True)
        lg2.metric("Most demanding cell here", f"{gsub['demand_p90'].max():.0f}°")

        st.markdown("##### The most demanding cells in view")
        st.dataframe(
            gsub.nlargest(12, "demand_p90")[
                ["cell", "demand_p90", "demand_p50", "radius_p50", "v_p50", "grade",
                 "elev", "n_corners", "rides", "abs_events"]]
            .assign(v_p50=lambda d: d["v_p50"] * 3.6, grade=lambda d: d["grade"] * 100)
            .round({"demand_p90": 1, "demand_p50": 1, "radius_p50": 0, "v_p50": 0,
                    "grade": 1, "elev": 0}),
            hide_index=True,
            column_config={
                "cell": st.column_config.TextColumn("morton cell", width="medium"),
                "demand_p90": st.column_config.NumberColumn("demand p90 °"),
                "demand_p50": st.column_config.NumberColumn("demand p50 °"),
                "radius_p50": st.column_config.NumberColumn("radius m"),
                "v_p50": st.column_config.NumberColumn("speed km/h"),
                "grade": st.column_config.NumberColumn("grade %"),
                "elev": st.column_config.NumberColumn("elev m"),
                "abs_events": st.column_config.NumberColumn("ABS limit"),
            })
        st.caption("Morton codes are read as strings — a 32-digit cell id overflows any "
                   "integer conversion. Demand is the p90 of arctan(v²/(R·g)) over every "
                   "corner recorded in the cell.")

st.divider()
st.caption("FLOWSTATE · 5,253 corners · 508,183 trackpoints · one rider, 15 bikes, 5 years. "
           "Physics bridge validated at corr 0.73 over 5,747 corners (docs/08_DATA_FINDINGS.md). "
           "BMW data under NDA — this app makes no network call other than optional map tiles.")
