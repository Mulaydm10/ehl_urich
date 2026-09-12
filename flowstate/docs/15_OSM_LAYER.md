# 15 — the external source: OpenStreetMap

`analysis/13_osm_layer.py`. Raw Overpass JSON over `requests`, snapped with
`scipy.spatial.cKDTree`. **No new dependencies** — osmnx and geopandas drag in
GDAL and were not worth the risk this close to a freeze.

53 tiles, 29 MB, cached under `flowstate/data/osm/` (gitignored). Fetch took
~15 min against rate-limited public mirrors; the join and report take seconds.
Once cached the demo needs no network.

## Why we needed it

We have claimed from slide one that FLOWSTATE never scores speed and only
recommends roads within the posted limit. **We had no way to check that.** The
telemetry knows how fast the crowd rode; it does not know what the sign said.
That was a hole in our own argument and a judge was entitled to walk into it.

## What it found, and it is not cosmetic

On the cells where a posted limit is known:

```
posted limit known                       39% of cells
crowd p85 above the limit by >10%        1,172 of 2,237  =  52%
median crowd p85 as a share of the limit             1.11x
```

**On half the roads where we know the limit, the crowd habitually exceeds it.**
So a little over half our demand numbers were, in part, describing what people
do when they speed.

## The fix: re-price the road, do not refuse it

Refusing those cells would be crude — a road can be excellent at 80. Instead
`apply_legal_speed` recomputes the demand at the **posted** speed. Since
`tan(theta)` goes as `v^2` at fixed radius:

```
tan(theta_legal) = tan(theta_crowd) * (v_limit / v_p85)^2
```

Effect on the 1,172 re-priced cells: **mean demand falls 9.67 -> 5.60 deg
(-4.07 deg).** The road still competes; it just competes on what it legally
offers. A cell with no posted limit (German autobahn, `maxspeed=none`) parses
to NaN and is left alone — its road class carries the meaning instead.

This is the honest version of "we never recommend speeding": not a promise on
a slide, a term in the cost function.

## BMW's RED and GREEN flags stop being inferences

Until now these were guessed from telemetry, which cannot see them — a
motorway and a fast country road look alike in a lean channel, and gravel and
tarmac look identical. Now they are tags (18-char grid, 26,987 cells):

```
RED   motorway / trunk              876 cells   3.2%   flow x0.45
RED   residential / living street 1,319 cells   4.9%   flow x0.45
RED   unpaved or cobbled              82 cells   0.3%   flow x0.55
GREEN country road, paved        14,710 cells  54.5%
```

Match quality: 17,034 of 26,987 cells (63%) found a road within 80 m, median
snap **6 m**. The unmatched third gets no flags and no penalty — absence of a
tag is never treated as evidence.

## What it did to the router

```
                     before OSM        after OSM
rider skill           12.63 deg        11.40 deg
safety gate           23.01 deg        22.59 deg
gate / hardest ridden  0.992x           1.063x
Cruise  mean demand    8.01 deg         7.02 deg
Send it mean demand   11.02 deg         9.71 deg
dial effect          +3.01 deg        +2.69 deg
```

Everything moved down, which is what re-pricing at the legal speed should do.
The gate-vs-hardest-road agreement loosened from 0.992x to 1.063x — still
within 6%, and still not something the construction forces.

## Temperature — tested, and it did NOT replicate

`sensorsoutsidetemperature` is present on 100% of corners, spanning 8.5 to
33 deg C, so the obvious idea was to derate grip on cold tarmac. We tested
whether these riders actually lean less when it is cold:

```
spearman(lean_deg, temp_c)                     -0.016   (n = 5,253)
spearman(lean/demand ratio, temp_c)            +0.040
per-trip, median lean/demand vs temp           +0.224   p = 0.24  (n = 29)
median use-ratio, <=12 C vs >24 C        0.772 vs 0.801
```

**The direction is right and the magnitude is undetectable at this sample
size.** So `mu_for_temp` ships as an explicitly labelled engineering
assumption from tyre behaviour, it feeds the **safety readout only** — grip
headroom — and it never touches the fun score. Do not claim our data
validates it. Say: "physics says cold tarmac has less grip; our 29 trips
cannot resolve it either way, so we show it as a caution, not a score."

## NDA

Nothing about BMW's data was transmitted. The query box is **rounded outward**
to generic southern Bavaria (47.3-48.1 N, 10.6-12.0 E) rather than our
measured coverage box, so not even the boundary we asked about is derived from
BMW rides. Responses are cached to disk; the demo makes no network call.

## Reproducing

```bash
cd ~/ehl_urich/flowstate
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
$V analysis/13_osm_layer.py          # cached; --refetch to ignore the cache
$V app/router.py                     # now reports the OSM block
```
