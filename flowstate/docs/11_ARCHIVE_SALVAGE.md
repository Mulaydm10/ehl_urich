# 11 — THE ARCHIVE SALVAGE, AND WHAT IT SETTLED

The 384 MB `exd_download (1).zip` was never re-downloaded. It did not need to be.
**9,694 files (1.77 GB) were recovered from the truncated download**, including one complete dataset.

---

## 1. What was wrong, and why it was recoverable

The download is cut off mid-transfer: no end-of-central-directory record, no central directory, so every
normal zip tool refuses the file. But a zip's **local file headers are interleaved with the data**, so a
truncated archive still describes itself — you just have to read it forwards instead of backwards.

The nesting was three deep:

```
exd_download (1).zip
└── datasetHackathon.zip.zip      deflate, streamed (flag bit 3, sizes in a trailer that never arrived)
    └── datasetHackathon.zip      WinZip AES-256 (method 99), actual method deflate
        └── 10,216 entries        plain deflate — no further encryption
```

**The key fact: WinZip AES is AES-CTR, a stream cipher.** A truncated prefix decrypts perfectly; the only
thing lost is the 10-byte HMAC at the end, which authenticates but is not needed to decrypt. So:

1. Raw-inflate the outer entry from byte 54 → 384.3 MB of the inner zip.
2. Parse its AES extra field (0x9901): version 2, vendor AE, **strength 3 → AES-256, 16-byte salt**,
   actual method 8. PBKDF2-HMAC-SHA1(password, salt, 1000 iters, 66 bytes) → key, HMAC key, and a 2-byte
   verifier. **The verifier matched (`cd0f`), which proves the password and the derivation before
   decrypting a single byte of payload.**
3. AES-CTR decrypt (little-endian counter starting at 1) and raw-inflate → 384.6 MB starting `PK\x03\x04`.
4. Scan for local file headers, then inflate each entry until its deflate stream ends naturally
   (`decompressobj.eof`), bounding each read by the next header.

Reproduce with `analysis/08_salvage_archive.py`. Runtime: about 30 seconds.

## 2. What came out

| Folder | Files recovered | Of the documented total | Status |
|---|---|---|---|
| `anonymizedDataLake/trips-samples-2` | **7,999** | **7,999** | ✅ **COMPLETE — 100%** |
| `anonymizedDataLake/trips-samples-1` | 1,468 | 77,700 | ⚠️ 1.9%, cut off at the truncation point |
| `exampleUserC/recordedTrips` | **224** | 224 | ✅ **COMPLETE — 100%** |
| Totals | **9,691 CSVs, 1.77 GB** | | 1 truncated entry, 521 skipped (dirs, `__MACOSX`) |

All parse cleanly at the full 43-column schema. `exampleUserB` and the `cloudRecordedTracks` manifest for
user C are **not** in the recovered range — they sit past the truncation point, so user C has no `bikeId`,
no `isFavorite` and no `leanAngleLeftMax`/`RightMax`.

> **The one that matters: `trips-samples-2` is complete.** That is BMW's own tighter box — Munich and the
> Alpine foothills, 7,999 rides, ~2.4 M trackpoints — and it is the dataset they curated as the
> interesting one. **It unblocks F29–F33 and the entire "Usage of BMW Crowd Data" judging criterion.**

## 3. What it settled: the asymmetry is dead, and now we can prove it

User C gives a second rider with **15,810 corners across 214 rides** — three times user A's sample.

| | LEFT corners | RIGHT corners |
|---|---|---|
| n | 7,762 | 8,048 |
| lean p50 | 16.4° | 16.1° |
| **lean p95** | **32.6°** | **33.0°** |
| required p50 | 16.4° | 16.4° |

**L − R = −0.40°, cluster-bootstrapped 95% CI [−1.04, +0.26] over 214 rides → not significant.**

This is **not** an underpowered null. The interval is ±0.65° — tight. Combined with user A, we have
**~21,000 corners from two riders and no asymmetry above about 1°.**

### What to do about it

**Kill it as a headline claim.** The "ride the loop counter-clockwise because you are 7° stronger on
left-handers" demo moment does not survive contact with the data. Do not pitch it.

**Keep it as a method, and pitch that instead** — it is now a *stronger* story, not a weaker one:

> *"Our first instinct was that riders are asymmetric — stronger on left-handers than right — so we would
> pick the direction of your loop to suit. BMW store left and right maximum lean as separate fields, so
> they clearly wondered too. We tested it on twenty-one thousand corners from two riders, bootstrapped
> over rides because corners inside one ride are not independent, and the effect is under one degree with
> the interval straddling zero. **So we do not use it.** The feature is in the system, it runs per rider,
> and it only acts when the interval clears zero. That is the difference between a personalisation
> feature and a horoscope."*

That paragraph demonstrates the thing BMW actually asked for — *"you define fun, we evaluate"* — better
than any surviving feature would have.

## 4. Consequences for the rest of the project

| Was | Now |
|---|---|
| Demo moment B = the asymmetry reveal (`docs/02_CONCEPT.md` §4B, `docs/06_PITCH.md` slide 2) | **Replace.** Use the crowd layer and the risk-ratio result instead. |
| F01 asymmetry marked "WORKS" | Computable, yes — but the effect is absent in both riders. Reclassify as *measured and rejected*. |
| F43 loop direction by handedness | **Drop from P1.** It has no measured basis. |
| F29–F33 crowd features "BLOCKED" | **Unblocked** — 7,999 complete rides. See `analysis/10_crowd_layer.py`. |
| "the crowd lake would carry ~10,000 ABS events" (`docs/10_LIVE_DEMO.md` §1) | Now testable on real data, at least at trips-samples-2 scale. |
| Users B and C unavailable for validation | **User C available** (224 rides); user B still missing. |

## 5. Still missing, and still worth re-downloading

`trips-samples-1` at full size (77,700 rides), `exampleUserB` (73 rides), and user C's manifest — all past
the truncation point. Everything in §2 above is enough to build and pitch on, so the re-download is no
longer a blocker; it is an upgrade.

**One caveat to carry into the validation:** the anonymized lake's `timestampinmillis` is shifted by a
random per-trip offset, so crowd rides cannot be joined to weather or to time of day. Example-user
timestamps are real. Do not mix the two in one analysis without saying which is which.
