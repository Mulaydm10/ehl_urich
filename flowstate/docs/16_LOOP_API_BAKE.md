# 16 — use case B, the service API, and the baked demo

Covers commits `2161c65` (X-hour loop), `ae9a975` (service + bake).
Written 2026-09-13 ~02:00 CEST on the Mac.

## `route_loop` — "a loop for the next X hours from here"

The half of BMW's brief we had not answered at all. Choosing the best closed
tour under a time budget is the orienteering problem, which is NP-hard, so
this is a heuristic and says so out loud:

1. Dijkstra out from the start, and a second one on the **transposed** graph
   for the time to get *back*. A node is a feasible turnaround only if
   out + back fits the budget.
2. Rank that ring by **fit cost per second** — a low cost per second is
   exactly "this direction is full of roads that suit this rider".
3. Ride out, make every edge just used **6x** expensive, and route home
   again, so the return leg finds different roads instead of retracing.
4. Keep the loops inside budget; pick the best by
   `flow x distinctness x how well it fills the time asked for`.

Time comes from the edge table's own median speeds, so the budget is real
riding minutes, not an assumed average.

**Measured, 4 starts x {1, 1.5, 2, 3} h = 16/16 succeed, 106-221 ms:**

```
Kochel       2.0h   133.4 km  118.7/120 min  fill  99%  distinct 94%
Holzkirchen  3.0h   192.9 km  176.5/180 min  fill  98%  distinct 88%
Schliersee   1.0h    69.9 km   59.6/60  min  fill  99%  distinct 91%
Lenggries    2.0h   134.3 km  120.8/120 min  fill 101%  distinct 92%
```

Every loop closes on the start cell. `distinct` is the share of cells ridden
once — 86-100%, so these are genuine loops, not out-and-back retraces.

### Two things that had to be fixed
**It failed outright on Holzkirchen at 2 h** while succeeding at 1 h and 3 h.
On stage that reads as a crash. The search now widens its tolerance once and
**labels the result honestly** rather than returning nothing.

**Candidates are scored on flat NumPy arrays, never assembled.** Assembling
each candidate means a pandas merge at ~5 ms, which capped the search at a
few dozen. Scoring off arrays lets us try 160 and still finish in ~150 ms.

## `app/service.py` — the only module the UI talks to

Everything above this line is physics and graphs. Everything below it is
pixels. The UI never sees a DataFrame, never builds a graph, never learns what
a morton code is.

```
init() riders() presets() route() loop() compare() explain()
basemap() cells_layer() status()
```

`compare(A, B)` is the demo's money shot and writes its own headline:

> Same two points. 1.13x the distance, 83% of it on different roads,
> +2.7 deg more lean asked of you.

Show both dial settings at once. **Do not make a judge drag a slider and
hope** — across 200 O-D pairs the median demand gain is -0.00 deg, so on a
randomly clicked pair nothing visible happens (doc 14).

`explain()` returns sentences, not numbers, because explainability is judged
and the reason belongs beside the answer:

```
This road asks a mean 9.7 deg of lean and peaks at 22.4 deg. Your gate is
22.6 deg, which is 2 sigma above the road you habitually ride.
Cornering asks about 33% of the tyre's grip here, against the 53% you have
already used on your own rides.
REFUSED - the crowd leans 24 deg here, past your gate of 23 deg (11 + 2 sigma).
```

## `data/cache/demo.pkl` — the freeze artefact

**The repo cannot reproduce a demo on its own.** The lake and every derived
parquet are gitignored and stay on this Mac. `analysis/14_bake_demo.py` writes
the one file the app needs: scored cells, edges, the OSM join, calibrated
riders, a **17,345-way grey road basemap** for drawing with the network
unplugged, and 21 pre-solved preset answers.

```
5.2 MB, built in 2.4 s
init() from the bake      12 ms
dial change            20-37 ms     <- live enough for a slider on a phone
loop                     146 ms
```

Rebake after ANY change to the router, the cell table or the OSM layer.

## Riders

Three profiles. There is no user B in the data — only `exampleUserA` — but
User A rode 15 bikes, and lean p95 on an S1000RR and on an R18 are not the
same measurement. So the honest second rider is the same human on a different
machine:

```
userA           skill 11.40  sigma 5.59  gate 22.59  agree 1.063x  grip 53%
bike_da67fa06   skill 10.10  sigma 6.57  gate 23.25  agree 0.901x  grip 48%
bike_4e1a9d64   skill 13.25  sigma 5.32  gate 23.89  agree 1.169x  grip 58%
```

**Known weakness: switching rider does not change the route** on the preset
pairs — all three return 53.0 km with identical mean demand. Not a caching
bug; their gates differ but none bites on that road, and with one corridor per
O-D pair the same path wins for everyone.

> **Superseded by doc 17.** That was measured on the wrong pair. Phase 3 found
> one where the gate does bite: on **Kochel → Tegernsee** cell overlap between
> `userA` and `bike_4e1a9d64` is 0.730 at Cruise and **0.105 at Send it**, with
> 3–5 roads refused outright depending on the profile. The rider switch is
> demonstrable on the map after all — on that pair. The warning above still
> holds for Lenggries → Bad Tölz and Lenggries → Kochel.

## The grip bug, and why it matters

Rider grip utilisation was being reported as **104% of available grip**. That
is not a hard rider, it is a bug: it combined each corner's peak lean with
that corner's peak |a_long|, and those happen at different instants — you
brake hard upright on the way in and lean hard off the brakes at the apex. The
corner table has no per-sample pairing to recover simultaneity.

Now reports **lateral only**, on exactly the same basis as the route's
`grip_lat_p95`, so the two are comparable: rider 53%, this route 33%. The
longitudinal term stays in `grip_used` for anywhere we do have simultaneous
samples.

## Reproducing

```bash
cd ~/ehl_urich/flowstate
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
$V analysis/14_bake_demo.py      # 2.4 s -> data/cache/demo.pkl
$V -c "import sys;sys.path.insert(0,'app');import service as S;print(S.init())"
```
