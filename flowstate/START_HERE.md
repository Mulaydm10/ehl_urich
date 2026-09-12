# FLOWSTATE — BMW Motorrad Route Challenge · session package (no data)

**TUM.AI Hackathon Zürich 2026 · 12–13 September 2026.** Packaged 12 September 2026.

> ### ⚠️ This zip deliberately contains NO BMW DATA.
> The BMW telemetry is under NDA. Every `.parquet`, the `data/` folder and all source archives are
> excluded. What is here is the **thinking, the code and the findings** — everything regenerates from the
> raw data by re-running `analysis/01…10` in order.

---

## The idea in one sentence

**Fun is not a property of a road. Fun is a property of the fit between a road and a rider — and the same
number that measures the fit also measures the risk.**

A corner of radius `R` at speed `v` demands `theta = arctan(v²/(R·g))`. A rider's telemetry shows the lean
they actually use. Same unit, both sides. Then:

```
z    = (challenge − skill) / sigma_rider
flow = exp( −(z − z*)² / (2·tau²) )        z* > 0 is the Thrill Dial
```

Below the band: boredom. Far above: anxiety, which on a motorcycle precedes a crash. **One curve produces
both of BMW's separate criteria — Fun Score and Rider Safety.**

## What was proven on the real data

| Finding | Evidence |
|---|---|
| The physics bridge is real | corr **0.73** over **5,747 corners**; errors-in-variables slope **1.08** using raw GPS heading |
| Risk rises with demand above skill | monotonic across six z bands, **3.6×** risk ratio — *but 13 events, p = 0.071, CI [0.0, 17.1]* |
| …confirmed independently at crowd scale | cells with a hard-braking event demand **13.3°** vs **12.5°**, **p = 4.9e-3**, n = 6,912 cells |
| Warm-up is measurable, not folklore | use-ratio 0.768 ±0.034 in the first 5 km vs 0.813 ±0.007 after 15 km |
| The bike reports the rider's mood | corr(rpm-per-kmh, median lean) = **0.54** across rides |
| ⛔ Left/right asymmetry | **tested and rejected** on 2 riders / ~21,000 corners. Pitch the method, not the feature |

## Reading order

1. `project/README.md` — concept and status
2. `project/HANDOFF.md` — **the session log; decisions not to reverse, and what is still open**
3. `project/docs/02_CONCEPT.md` — the idea in full
4. `project/docs/08_DATA_FINDINGS.md` → `09_DATA_MAP.md` → `11_ARCHIVE_SALVAGE.md` → `12_CROWD_LAYER.md` —
   what the data actually supports, in the order it was learned. **These override docs 02–07 wherever they
   disagree.**
5. `project/docs/10_LIVE_DEMO.md` — the demo design and the five-beat script
6. `project/docs/06_PITCH.md` — the pitch (⚠️ slide 2 needs replacing; the asymmetry moment is dead)

## To pick this up with the data

1. Get the BMW archives and the password, extract to `F:\bmw\data\raw\`.
   If the 384 MB download is truncated again, `analysis/08_salvage_archive.py` documents the full recovery
   (WinZip AES is AES-CTR, so a truncated prefix still decrypts — see `docs/11_ARCHIVE_SALVAGE.md`).
2. Run `analysis/01_profile.py` → `02` → `03` → `04_master_table.py` → `05` → `06` → `07_risk_validation.py`
   → `09_userC_asymmetry.py` → `10_crowd_layer.py`.
3. `streamlit run app/streamlit_app.py --server.headless true --server.port 8502`

Run everything with `PYTHONIOENCODING=utf-8` — the Windows console is cp1252 and umlauts in route names
will crash an otherwise-working script.

## Known open items

- `exampleUserB` (73 rides), user C's manifest, and 98% of `trips-samples-1` are past the truncation point
  of the 384 MB download. Everything so far is **Bavaria-only**.
- `analysis/04_master_table.py` still uses `positionmapmatchedheading`; switching to `positionrawheading`
  improves every downstream number (see `HANDOFF.md` entry 3b).
- Two bugs in the M1 conversion label: no time ordering, and home-adjacent cells inflate coverage.

## Non-negotiables

- **Never score speed or lap times.** Lean, smoothness, rhythm, flow — always within posted limits.
- **The BMW data never leaves the machine.** No hosted demo, no cloud notebook, no third-party API.
