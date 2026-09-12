# 01 — THE BRIEF (extracted from both BMW decks)

**Event:** TUM.AI Hackathon Zürich 2026 · **12–13 September 2026**
**Sponsor track:** BMW Motorrad — "FIND YOUR THRILL — ROUTE CHALLENGE"
**BMW people named:** Alexander Thoelke (presenter), Manhardt, Bäuml.
**Source files:** `20260912 Hackathon BMW Motorrad short.pdf` (7pp) and
`20260912 Hackathon Presentation Zürich Short 2.pdf` (4pp), both in `C:\Users\HP\Favorites\Downloads\`.
Text extracted with PyMuPDF — full content reproduced below so nobody needs the PDFs again.

---

## 1. Who BMW Motorrad says they are (deck 1, p2)

> "BMW MOTORRAD IS A LIFESTYLE — MOTORCYCLES AND CARS ARE NOT THE SAME THING!"

- **BMW Motorrad:** "We don't just build transportation. We create experiences that turn free time into lasting memories."
- **ConnectedRide App:** "We own the digital riding companion: before, during and after every ride."
- **Mission:** "Make riding safer, simpler and more exciting, an experience people love spending their free time on."

> **Read this as the scoring subtext.** They are not asking for a navigation app. They are asking for
> something that belongs in ConnectedRide and serves *before / during / after* the ride. Any concept that
> only does "during" (turn-by-turn) is half a product to them. Safety is in their mission statement, not
> a footnote — a solution that trades safety for thrill is off-brand and loses.

## 2. The mission (deck 1, p5–6; deck 2, p1–2)

> "YOUR MISSION: FIND THE BEST ROUTE — BUT WHAT IS THE 'BEST' ROUTE?"

**Two use cases. Pick one or both:**
1. Rider is getting **from A to B**.
2. Rider wants to **ride around their current location for X hours** (round trip / loop).

**Your mission — provide the best route, considering these metrics:**
- Usage of **BMW Crowd Data**
- Usage of **BMW Personal Rider Data**
- Usage of **external sources**
- **Scalability & Efficiency**
- **Calculation of Fun Score**
- **Consideration of Rider Safety**

**What to develop (deliverables, literally listed):**
- The **exact definition of "good route"** in your solution.
- An **overview of all used data sources and how they are weighted and combined**.
- A **visual representation of the data and algorithm** (e.g. route planning tool).

**And the result?**
- A **dynamic** solution planning a route for one or two of the use cases with maximum consideration of all success metrics.
- A **presentation & showcase** of the overall solution.

## 3. The data they hand over (deck 1, p6; deck 2, p4)

- **Provided:** anonymized **rider profiles** (internal testers) + **BMW test-ride snippets**.
- **Key signals:** GPS tracks, motorcycle sensor data — **speed, G-forces, lean angle, etc.**
- **Creativity welcome:** weather, rain radar, scenic viewpoints, traffic, etc. — "enrich your algorithm with any external source."
- **Handover:** cloud share, **NDA signed before access**.
- **BMW on-site** throughout — ask them anything.

## 4. Their own definition of good and bad road (deck 2, p3)

> "MOTORCYCLE RIDING IS NOT LIKE DRIVING A CAR — THINK OUTSIDE OF THE BOX, CHALLENGE YOUR IDEA OF NAVIGATION"

| GREEN FLAGS | RED FLAGS |
|---|---|
| Curves | Inner city |
| High lean angle | Standstills |
| Speed between 50 and 120 | Bad weather (rain & temperature) |
| Scenic views | Bad road conditions |
| **Flow** | |
| Elevation | |
| Clear road view | |

## 5. How they will judge (deck 1, p6; deck 2, p4)

- **Success metric:** "Generate personalized **awesome** routes! **You define 'fun', we evaluate.** Most exciting solution wins."
- "**Think beyond GPS** — elevation, curves per km, road surface type."
- "**Define your KPI** — lean angle × acceleration? Smile factor? You decide."
- "**Impress us** — **explainability + live demo will score bonus points**."
- **Final pitch:** demo + **algorithm walk-through**.

---

## 6. What the brief is really telling us (inference, not quoted)

Six things are load-bearing and most teams will miss at least three:

1. **"You define 'fun', we evaluate"** is an invitation to be opinionated *and* an invitation to be
   measured. A defended, falsifiable definition of fun beats a prettier map. See `07_VALIDATION.md`.
2. **Fun Score and Rider Safety are listed as two separate criteria.** Teams will score fun and then
   subtract a safety penalty. Whoever shows one model that produces both wins that whole section. Our
   concept does exactly this (see `02_CONCEPT.md`).
3. **"Personalized"** appears in the success metric and **Personal Rider Data** is its own criterion.
   A generic "scenic route finder" scores near zero on two criteria at once.
4. **"Clear road view"** in the green flags means they care about **sight distance / blind corners** —
   almost nobody computes this. It is cheap to approximate and is an instant credibility signal.
5. **"Flow"** is in their green flags. They mean rhythm and no forced stops. We take the word literally
   and build the whole product on flow theory — which is also the user's original instinct.
6. **Scalability & Efficiency is a graded criterion at a hackathon**, which is unusual. It means they are
   thinking about ConnectedRide with millions of users. Have a real answer (we do: offline Road DNA
   tensor + one dot product per edge at query time).

## 7. Hard constraints to respect

- **Speed is a brand landmine.** BMW cannot ship a product that gamifies going fast on public roads.
  Everything we score must be expressible as *lean, smoothness, rhythm, flow* — never lap time, never
  "beat your record". Say this out loud in the pitch; it reads as maturity, and it is genuinely the
  safer product.
- **GDPR.** German OEM. Telemetry is personal data. Have a privacy story (on-device profile, aggregate-only
  uploads, k-anonymity on crowd layers, home geofence). One slide, thirty seconds, big credibility.
- **Swiss/Bavarian geography is seasonal.** Alpine passes close in winter. A demo that routes over a closed
  pass in front of a Zürich audience is an own goal — handle or at least name it.
- **NDA on the data.** Do not push BMW telemetry to a public repo, a hosted demo, or any third-party API.
  Keep the demo local. This also means: do not publish the data in an Artifact or any cloud service.
