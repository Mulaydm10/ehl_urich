# 30 — The live co-pilot: rerouting while the ride is happening

Status: built and shipped.

Everything the assistant did until now was reactive: the rider asks, the model
plans. This adds the other half — the app watching the ride and speaking first.

## The shape of it

```
phone GPS watch (already exists, useLivePosition)
      |  one tick per 20 s, and only if the bike moved 40 m
      v
POST /api/copilot/tick   {lat, lon, speed, heading, thrill, mode, route}
      |
      |  1. TRIGGERS    pure rules over position + the FLOWSTATE engine
      |  2. GATE        cooldowns, dismissals, one suggestion per tick
      |  3. NARRATION   OpenAI phrases it in one sentence — or vetoes it
      v
{suggestion | null}  ->  card on the Ride screen, spoken aloud
```

The split matters more than any single trigger. **The model never plans, never
invents a number and never decides that a road is dull.** A rule did that from
the engine's own output, and the payload handed to the model already contains
the sentence we would have said without it. So with no `OPENAI_API_KEY` the
co-pilot still works; it just sounds like a machine.

The one judgement the model *is* given is relevance: it may answer `SKIP`, and
the suggestion is dropped. "A gem 3 km off your line" is correct and unwelcome
when the rider is eight minutes from home in the rain. The rules are tuned to
over-fire; SKIP is the cheap filter.

## Triggers (`flowstate/app/copilot.py`)

| kind | fires when | offers |
|---|---|---|
| `gate_ahead` | a gate refusal within 2.5 km of the rider | warning only — the gate does not negotiate, so it outranks everything |
| `off_route` | > 150 m off the planned path, two fixes running | a new route to the same destination from here |
| `fuel` | recorded range < 1.2 × the distance left, or tank < 25 % | a fuel stop, labelled as a garage record, not a live sender |
| `dull_ahead` | > 55 % of the next 6 km scores below flow 0.20 | the same destination at thrill + 0.35 |
| `scenic_detour` | a routable, ungated crowd gem 0.5–5 km away while moving | a scenic leg to it |
| `stopped` | under 3 km/h for 4 minutes | a loop back from this spot |

Quiet rules: 150 s between any two suggestions, 10 min before the same kind
repeats, 30 min if the rider dismissed it. A trigger that throws is caught and
reported; a broken rule must not end a ride.

Outside the Bavaria coverage box the co-pilot says so and stays silent — the
engine has no scored cells there, so any suggestion would be invented.

## App side

- `services/copilot.ts` — client, plus the active-route store (Thrill publishes
  whatever plan is on screen; the co-pilot measures the ride against it).
- `components/useCopilot.ts` — the heartbeat. Reuses the existing GPS watch;
  two `watchPosition` calls on one phone is battery the rider notices.
- `components/CopilotCard.tsx` — switch, honest status line, one suggestion,
  "Take it" / "Not now". Accepting runs the suggestion's own tool through
  `/api/assistant/tool` and opens the new plan on Thrill. Every card shows
  which trigger produced it and whether a model worded it.

## What is verified

- Backend, against the mock engine and a live model: off-route after two fixes,
  gate warning, the quiet window holding the next suggestion, dismissal parking
  a kind, and the coverage-box refusal.
- Frontend: lint, typecheck, production build, APK packaging.

Not verified: a real moving ride, and anything bike-sourced. The co-pilot reads
phone GPS only — it does not and must not present that as bike telemetry.
