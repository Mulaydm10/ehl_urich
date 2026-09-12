"""
14_bake_demo.py — freeze the demo into one file.

The repo cannot reproduce a demo on its own: the BMW lake and every derived
parquet are gitignored and stay on this machine. This writes the one artefact
the app actually needs — data/cache/demo.pkl — holding the scored cells, the
graph edges, the OSM join, the calibrated rider profiles, a grey road basemap
for drawing with the network unplugged, and the preset routes already solved.

After this, `service.init()` loads in well under a second, touches no raw
data, and makes no network call. That is the T-4h freeze artefact.

Run:
    V=/Users/mulaydm10/ehl_urich/.venv/bin/python
    $V analysis/14_bake_demo.py
"""

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import router as R          # noqa: E402
import service as S         # noqa: E402

OUT = ROOT / "data" / "cache" / "demo.pkl"
OSM_CACHE = ROOT / "data" / "osm"

# only the roads worth drawing as context — residential clutters the map and
# triples the file
BASEMAP_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary",
                   "unclassified", "motorway_link", "trunk_link"}
SIMPLIFY_M = 60.0          # drop basemap vertices closer together than this


def build_basemap() -> list:
    """Road polylines from the cached OSM tiles, simplified for drawing."""
    out = []
    for p in sorted(OSM_CACHE.glob("tile_*.json")):
        for el in json.loads(p.read_bytes()).get("elements", []):
            if el.get("tags", {}).get("highway") not in BASEMAP_CLASSES:
                continue
            g = el.get("geometry") or []
            if len(g) < 2:
                continue
            la = np.fromiter((x["lat"] for x in g), float)
            lo = np.fromiter((x["lon"] for x in g), float)
            keep = [0]
            for k in range(1, len(la)):
                d = np.hypot((la[k] - la[keep[-1]]) * 110540.0,
                             (lo[k] - lo[keep[-1]]) * 74000.0)
                if d >= SIMPLIFY_M or k == len(la) - 1:
                    keep.append(k)
            if len(keep) < 2:
                continue
            out.append({"cls": el["tags"]["highway"],
                        "path": [[round(float(lo[k]), 5), round(float(la[k]), 5)]
                                 for k in keep]})
    return out


if __name__ == "__main__":
    t0 = time.time()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print("[1] cells + edges + OSM")
    cells = R.load_cells()
    osm = R.load_osm()
    if osm is None:
        print("    WARNING: no OSM layer. Run analysis/13_osm_layer.py first.")
    cells = R.apply_legal_speed(cells, osm)
    edges = R.load_edges()
    print(f"    {len(cells):,} cells, {len(edges):,} edges, "
          f"OSM {'yes' if osm is not None else 'NO'}")

    print("[2] calibrating riders")
    riders = S._build_riders(cells)
    for k, v in riders.items():
        r = v["rider"]
        print(f"    {k:<16s} skill {r.skill:5.2f}  sigma {r.sigma:4.2f}  "
              f"gate {r.gate:5.2f}  ({r.n_cells} cells)")

    print("[3] basemap from cached OSM tiles")
    basemap = build_basemap()
    print(f"    {len(basemap):,} ways, "
          f"{sum(len(w['path']) for w in basemap):,} vertices")

    print("[4] pre-solving the presets")
    payload = {"cells": cells, "edges": edges, "osm": osm, "riders": riders,
               "basemap": basemap, "precomputed": {}}
    S._S = {**payload, "graphs": {}, "source": "bake(build)",
            "loaded_s": 0.0}

    pre = {}
    for p in S.PRESET_ROUTES:
        for name, z in S.Z_PRESETS.items():
            r = S.route(p["a"], p["b"], "userA", z)
            pre[f"route:{p['key']}:{z}"] = r
            print(f"    route {p['key']:<22s} {name:<8s} "
                  f"{'ok' if r['ok'] else 'FAIL'} "
                  f"{r['summary'].get('km', 0):6.1f} km")
    for p in S.PRESET_LOOPS:
        for hours in (1.0, 2.0, 3.0):
            r = S.loop(p["start"], hours, "userA", 0.5)
            pre[f"loop:{p['key']}:{hours}"] = r
            print(f"    loop  {p['key']:<22s} {hours:.0f}h      "
                  f"{'ok' if r['ok'] else 'FAIL'} "
                  f"{r['summary'].get('km', 0):6.1f} km")
    payload["precomputed"] = pre

    with open(OUT, "wb") as f:
        pickle.dump(payload, f, protocol=5)
    mb = OUT.stat().st_size / 1e6
    print(f"\nwrote {OUT}  {mb:.1f} MB  in {time.time()-t0:.1f} s")
    print(f"  {len(pre)} pre-solved answers, {len(basemap):,} basemap ways")
