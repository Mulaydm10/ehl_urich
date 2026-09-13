"""
Routing through stops the rider picked.

FLOWSTATE plans A -> B. A rider who wants a lake on the way is asking for
A -> lake -> B, which is two plans ridden back to back, so that is exactly what
this does: one engine call per leg, stitched into a single plan the map and the
co-pilot can read without knowing it was assembled.

What is *not* done here is as important. The legs are not re-optimised as a
travelling-salesman problem — the order is the rider's, because he is the one
who knows why that stop is on the list. And the stitched summary is arithmetic
over the legs, never a re-scored whole: distance and time add up, demand is the
worst of the legs, and the fun score is a distance-weighted mean of them. The
route's own peak-end fun score cannot be recovered from its parts, so it is not
claimed to be.
"""
from __future__ import annotations

from typing import Any, Callable

MAX_VIA = 6


def plan_via(
    route: Callable[..., dict],
    points: list[list[float]],
    rider_key: str = "userA",
    z_star: float = 0.5,
    mode: str = "flow",
) -> dict:
    """
    Plan `points[0] -> points[1] -> ... -> points[-1]` with the given engine's
    `route`. Fails as a whole when any leg fails: half a route to a stop the
    rider asked for is worse than being told the stop cannot be reached.
    """
    if len(points) < 2:
        return _refused("Give me at least a start and an end.")
    if len(points) - 2 > MAX_VIA:
        return _refused(f"That is more than {MAX_VIA} stops on the way; "
                        f"the legs stop being one ride.")

    legs: list[dict] = []
    for i in range(len(points) - 1):
        leg = route(points[i], points[i + 1], rider_key, z_star, mode=mode)
        if not leg.get("ok"):
            which = "the first leg" if i == 0 else f"leg {i + 1}"
            return _refused(f"{which} could not be planned: "
                            f"{leg.get('note') or 'no route between those points'}",
                            legs=len(points) - 1, failed_leg=i + 1)
        legs.append(leg)

    return _stitch(legs, points, rider_key, z_star)


def _refused(note: str, **extra: Any) -> dict:
    return {"ok": False, "note": note, "path": [], "segments": [],
            "refusals": [], "summary": {}, "explain": [note], **extra}


def _stitch(legs: list[dict], points: list[list[float]],
            rider_key: str, z_star: float) -> dict:
    path: list[list[float]] = []
    cells: list[str] = []
    segments: list[dict] = []
    refusals: list[dict] = []
    for i, leg in enumerate(legs):
        # The end of one leg is the start of the next: the same point twice
        # would draw a zero-length segment and count a cell twice.
        p = leg.get("path") or []
        path += p[1:] if i and p else p
        c = leg.get("cells") or []
        cells += c[1:] if i and c else c
        segments += leg.get("segments") or []
        refusals += leg.get("refusals") or []

    km = sum(_num(leg, "km") for leg in legs)
    summary = {
        "km": km,
        "minutes": sum(_num(leg, "minutes") for leg in legs),
        "mean_demand": _weighted(legs, "mean_demand", km),
        "max_demand": max((_num(leg, "max_demand") for leg in legs), default=0.0),
        "peak_flow": max((_num(leg, "peak_flow") for leg in legs), default=0.0),
        "fun_score": _weighted(legs, "fun_score", km),
        "gate_deg": max((_num(leg, "gate_deg") for leg in legs), default=0.0),
        "is_loop": False,
        "legs": len(legs),
        "via": [list(p) for p in points[1:-1]],
    }
    grips = [_num(leg, "grip_lat_p95", none_ok=True) for leg in legs]
    grips = [g for g in grips if g is not None]
    if grips:
        summary["grip_lat_p95"] = max(grips)

    stops = len(points) - 2
    explain = [
        f"{summary['km']:.0f} km through {stops} stop{'' if stops == 1 else 's'} "
        f"you picked, about {summary['minutes']:.0f} minutes of riding.",
        "Each leg was planned on its own and they are shown as one ride. "
        "Distance and time add up; the fun score is the legs' distance-weighted "
        "mean, not a score for the whole line.",
    ]
    for i, leg in enumerate(legs, start=1):
        explain.append(f"Leg {i}: {_num(leg, 'km'):.0f} km, "
                       f"{_num(leg, 'minutes'):.0f} min, "
                       f"peak lean {_num(leg, 'max_demand'):.1f} deg.")
    if refusals:
        explain.append(f"{len(refusals)} road(s) across the legs were refused by "
                       f"your safety gate, not just made expensive.")
    else:
        explain.append("Nothing on these legs crosses your safety gate.")

    return {"ok": True, "note": "", "cells": cells, "path": path,
            "segments": segments, "refusals": refusals, "summary": summary,
            "rider": rider_key, "z_star": float(z_star), "explain": explain,
            "legs": [{"km": _num(leg, "km"), "minutes": _num(leg, "minutes"),
                      "points": len(leg.get("path") or [])} for leg in legs]}


def _num(leg: dict, key: str, none_ok: bool = False) -> Any:
    value = (leg.get("summary") or {}).get(key)
    if value is None:
        return None if none_ok else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None if none_ok else 0.0


def _weighted(legs: list[dict], key: str, total_km: float) -> float:
    if total_km <= 0:
        values = [_num(leg, key) for leg in legs]
        return sum(values) / len(values) if values else 0.0
    return sum(_num(leg, key) * _num(leg, "km") for leg in legs) / total_km
