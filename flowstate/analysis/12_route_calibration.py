"""
12_route_calibration.py — why the router runs on 16-character cells and why
LAMBDA is 10.

Phase 2 of the execution plan ends with a stop-check: route Munich->Tegernsee
at z* = 0.15 and 0.9, and tune LAMBDA until "Send It" is 1.5-1.8x the direct
distance. That target cannot be met, and this script is the evidence for why.
It is not a tuning failure. It is a property of a graph built from ride traces.

Run:
    V=/Users/mulaydm10/ehl_urich/.venv/bin/python
    $V analysis/12_route_calibration.py

Needs crowd_grid_s2 / graph_edges_s2 (18 chars) and crowd_grid_c16 /
graph_edges_c16 (16 chars). Build the 16-char pair with:
    FS_CELL_CHARS=16 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _c16
    FS_CELL_CHARS=16 $V analysis/11_build_graph.py --set trips-samples-2 --tag _c16
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import router as R           # noqa: E402
import flowstate as fs       # noqa: E402

PAIRS = {
    "Bad Tolz -> Tegernsee":  ((47.76, 11.56), (47.85, 11.85)),
    "Kochel -> Tegernsee":    ((47.66, 11.35), (47.85, 11.85)),
    "Starnberg -> Schliersee": ((47.95, 11.35), (47.85, 11.85)),
}


def topology(tag: str) -> None:
    """How much routing freedom does the graph at this resolution have?"""
    e = R.load_edges(tag, symmetrise=False)
    u = pd.DataFrame({"a": np.minimum(e.ci, e.cj), "b": np.maximum(e.ci, e.cj)})
    u = u.drop_duplicates()
    u = u[u.a != u.b]
    nodes = sorted(set(u.a) | set(u.b))
    ix = {c: i for i, c in enumerate(nodes)}
    m = csr_matrix((np.ones(len(u)), (u.a.map(ix), u.b.map(ix))),
                   shape=(len(nodes), len(nodes)))
    nc, lab = connected_components(m, directed=False)
    V, E = len(nodes), len(u)
    big = int(np.bincount(lab).max())
    print(f"  {tag}: V={V:,}  E={E:,}  components={nc:,}  LCC={big:,} "
          f"({big/V:.1%})  independent loops = E-V+C = {E-V+nc:,}")


def disjoint_second_path(tag: str) -> None:
    """
    The decisive test. Find the shortest path by length, delete exactly those
    edges, and ask for a path again. If there is no second path, there is one
    corridor, and no cost function can route around anything.
    """
    cells, edges = R.load_cells(tag), R.load_edges(tag)
    rider = R.calibrate_rider(fs.load_corners(True), cells, "A")
    g = R.build_graph(edges, cells, rider, 0.15, lam=0.0)
    L = R._csr_aligned_lengths(g)
    m = csr_matrix((L, g.matrix.indices, g.matrix.indptr), shape=g.matrix.shape)

    for name, (A, B) in PAIRS.items():
        a = R.snap(*A, cells, nodes=g.nodes)
        b = R.snap(*B, cells, nodes=g.nodes)
        si, ti = g.index[a], g.index[b]
        idx = R._shortest(g, si, ti, weights=L)
        if idx is None:
            print(f"  {tag} {name}: unreachable")
            continue
        tot = sum(m[idx[k], idx[k + 1]] for k in range(len(idx) - 1))
        used = {(idx[k], idx[k + 1]) for k in range(len(idx) - 1)}
        used |= {(y, x) for x, y in used}
        co = m.tocoo()
        keep = np.array([(i, j) not in used for i, j in zip(co.row, co.col)])
        m2 = csr_matrix((np.where(keep, co.data, 0.0), (co.row, co.col)),
                        shape=m.shape)
        m2.eliminate_zeros()
        alt = dijkstra(m2, directed=True, indices=si)[ti]
        txt = f"{alt/1000:6.1f} km  ({alt/tot:.2f}x)" if np.isfinite(alt) \
              else "  NONE — A and B are disconnected"
        print(f"  {tag} {name:24s} shortest {tot/1000:6.1f} km over "
              f"{len(idx):4d} cells | 2nd disjoint {txt}")


def lambda_ceiling(tag: str) -> None:
    """
    cost = L * (1 + lam*(1-flow)) -> lam * L * (1-flow) as lam grows, so the
    RANKING of paths stops changing above some lam. Find where.
    """
    cells, edges = R.load_cells(tag), R.load_edges(tag)
    rider = R.calibrate_rider(fs.load_corners(True), cells, "A")
    A, B = (47.59, 11.75), (47.73, 11.37)
    prev = None
    for lam in (0, 1, 3, 6, 10, 20, 40, 80):
        g = R.build_graph(edges, cells, rider, 0.90, lam=lam)
        r = R.route_a_to_b(A, B, rider, 0.90, graph=g, cells=cells, edges=edges)
        same = " (identical to previous)" if prev == tuple(r.cells) else ""
        print(f"  lam {lam:>3}: {r.summary['km']:6.2f} km  "
              f"mean flow {r.summary['mean_flow']:.3f}{same}")
        prev = tuple(r.cells)


def od_scan(tag: str, lam: float = R.LAMBDA_DEFAULT) -> pd.DataFrame:
    """
    Route every anchor pair 25-75 km apart at both dial settings and measure
    what the dial actually changes.
    """
    import itertools
    cells, edges = R.load_cells(tag), R.load_edges(tag)
    rider = R.calibrate_rider(fs.load_corners(True), cells, "A")
    gC = R.build_graph(edges, cells, rider, 0.15, lam=lam)
    gS = R.build_graph(edges, cells, rider, 0.90, lam=lam)

    anchors = [(round(float(la), 3), round(float(lo), 3))
               for la in np.arange(47.45, 48.01, 0.14)
               for lo in np.arange(10.80, 11.95, 0.19)]
    rows = []
    for A, B in itertools.combinations(anchors, 2):
        if not 25 < 111 * np.hypot(B[0]-A[0], (B[1]-A[1]) * 0.67) < 75:
            continue
        rC = R.route_a_to_b(A, B, rider, 0.15, graph=gC, cells=cells, edges=edges)
        rS = R.route_a_to_b(A, B, rider, 0.90, graph=gS, cells=cells, edges=edges)
        if not (rC.ok and rS.ok) or rC.note or rS.note:
            continue
        d = R.direct_route(A, B, gC)
        if not d.ok:
            continue
        c = R.compare_routes(rC, rS)
        rows.append(dict(A=A, B=B, direct=d.summary["km"],
                         cruise_km=rC.summary["km"], send_km=rS.summary["km"],
                         ratio=rS.summary["km"] / d.summary["km"],
                         overlap=c["overlap"], demand_gain=c["demand_gain"],
                         dem_C=rC.summary["mean_demand"],
                         dem_S=rS.summary["mean_demand"],
                         peak_C=rC.summary["peak_flow"],
                         peak_S=rS.summary["peak_flow"]))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    t0 = time.time()

    print("\n[1] routing freedom, undirected, before any costing")
    for tag in ("_s2", "_c16"):
        topology(tag)

    print("\n[2] is there a second corridor at all?")
    for tag in ("_s2", "_c16"):
        disjoint_second_path(tag)

    print("\n[3] where LAMBDA stops mattering (_c16, Send It)")
    lambda_ceiling("_c16")

    print(f"\n[4] what the dial moves, across every routable O-D pair "
          f"(_c16, lam={R.LAMBDA_DEFAULT})")
    df = od_scan("_c16")
    print(f"  {len(df)} routable pairs")
    print(f"  detour ratio  : median {df.ratio.median():.3f}  "
          f"p90 {df.ratio.quantile(.9):.3f}  MAX {df.ratio.max():.3f}")
    print(f"  cell overlap  : p10 {df.overlap.quantile(.1):.3f}  "
          f"median {df.overlap.median():.3f}")
    print(f"  demand gain   : median {df.demand_gain.median():+.2f} deg  "
          f"p90 {df.demand_gain.quantile(.9):+.2f} deg")
    print("\n  best demo pairs — most road changed for least distance added:")
    best = df[df.demand_gain > 2.0].nsmallest(5, "overlap")
    cols = ["A", "B", "direct", "cruise_km", "send_km", "ratio", "overlap",
            "dem_C", "dem_S"]
    print(best[cols].round(2).to_string(index=False))

    out = Path(R.OUT) / "route_calibration.csv"
    df.round(4).to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(df)} pairs)  in {time.time()-t0:.1f} s")
