# EHL Zurich (12–13 Sept 2026) — Research Brief & Win Strategy

Legend: **[CONFIRMED]** = found in a public source (linked). **[INFERRED]** = my reasoning from evidence. **[NOT PUBLIC]** = looked for it, could not find it.

---

## 1. The event

| Item | Status | Detail |
|---|---|---|
| Organizer | CONFIRMED | TUM.ai (founder of EHL) together with **J floor** (Zurich builder community). [Source](https://www.linkedin.com/posts/tum-ai_ehl-europeanhackathonleague-tumai-activity-7500250584864940032-kalD), [ehl.gg](https://www.ehl.gg) |
| Format | CONFIRMED | 75 hand-picked participants, teams of 3–5, one night (~24 h), Zurich city centre. "No massive crowd… very little time to turn ideas into something real." |
| League | CONFIRMED | Stop in a season: Paris (research-focused) → Makeathon Munich (Apr) → Munich (22–23 Aug, 200 people) → **Zurich** → Grand Finale Munich. Points per challenge placement feed a leaderboard. |
| Named partners | CONFIRMED | **Entire** and **BMW Group**, "more coming soon". Exact venue and full partner list: **NOT PUBLIC** as of 10 Sept. |
| Partner model | CONFIRMED | EHL sells "Challenge Partner" slots = *own challenge track with dedicated teams, jury seats, branded prizes*. So expect **one BMW track + one Entire track (+ any late-joining partner tracks)**, you pick/get assigned one. [ehl.gg/partners](https://www.ehl.gg/partners) |

**What EHL challenges look like (Munich stop, Aug 2026 — same organizers, 3 weeks ago):**

| Partner | Challenge (public) | Style |
|---|---|---|
| QuantCo | "Claim to Fame" — process complex multimodal invoice data across **100 fast-paced rounds** | Scored, benchmark-style, measurable |
| viktor.com | Build an **LLM model router** balancing cost vs quality when historical data only shows one model's output per step (counterfactual problem) | Hard ML/eval problem, metric-driven |
| Cognition | "Find an Industry, Give it an Engineer" — pick an industry where an autonomous agent (Devin) can run a full inspect→verify→improve loop | Open agentic, judged on real workflow value |
| Entire | Use Entire checkpoints to track agentic development (prompts, sessions, commit intent) | Tooling / process side-challenge |
| OpenAI, Dryft | Tech/API partners | Credits & tools |

[Munich winners post](https://www.linkedin.com/posts/tum-ai_ehl-europeanhackathonleague-tumai-activity-7499524128064966656-OzU8) · [router write-up](https://www.linkedin.com/posts/rohan-patil18_ai-machinelearning-buildinpublic-activity-7497613683489968128--_Zb) · [Cognition track write-up](https://www.linkedin.com/posts/cyprian-szejnfeld-b8273b288_we-took-3rd-place-in-cognitions-find-an-activity-7497729426059595776-SzQJ)

**Takeaway [INFERRED]:** EHL partner challenges are concrete and often *quantitatively scored*, not "innovate around mobility" fluff. Winners ship a working system plus numbers.

---

## 2. Sponsor-by-sponsor

### BMW Group — CONFIRMED challenge partner
Who at BMW runs student hackathons with TUM.ai: **BMW Open Innovation / Startup Garage** (Garching). Names that recur: Dominik Pietsch (Manager Innovations & Piloting), Dr. Manuel Schneider, Patrick Lanners (also appeared as BMW contact at the humanoid hackathon), Michal Kuemmel (mentor), Marco Goergmaier (VP Data/AI, keynote). [Source](https://www.linkedin.com/posts/marco-goergmaier_exciting-weekend-ahead-at-bmw-group-activity-7387076794924900352-ZuaJ)
→ **[INFERRED]** the Zurich BMW track is very likely run by this same Open Innovation team, i.e. the same people who ran the Oct 2025 "Robotics AI Hackathon" with TUM.ai.

### Entire — CONFIRMED (league partner, Paris + Munich + Zurich)
Dev platform by ex-GitHub CEO Thomas Dohmke; CLI stores agent prompts/transcripts as "Checkpoints" in git. In Munich it was a side-challenge: **use Entire throughout your build**. Cheap points: install Entire CLI on day 0, commit with checkpoints from minute one, show the history in your pitch. [Source](https://www.linkedin.com/posts/tum-ai_ehl-europeanhackathonleague-tumai-activity-7494070551485779968-IUof)

### Likely late additions — NOT PUBLIC / INFERRED
Recurring EHL partners: Cognition, OpenAI, QuantCo, viktor.com, Reply, ElevenLabs (Makeathon). Zurich-local guess: J floor's network (ETH spinouts). Don't plan around these.

---

## 3. BMW's previous hackathon problem statements (all found, newest first)

| # | Event | Date | BMW's problem statement | Exactness |
|---|---|---|---|---|
| 1 | **BMW Plant Landshut physical-AI announcement** (not a hackathon, but the newest signal) | 21 Jul 2026 | Landshut builds the *software stack* for humanoid robotics in component production: VLA models + deterministic programming, demonstration-based learning (motion-capture suits, data gloves), sim/motion planning, "perceive environment → evaluate situation → derive actions". Partner: Athenyx Robotics. [Press release](https://www.press.bmwgroup.com/global/article/attachment/T0459467EN/652563) | Official |
| 2 | **Figure 03 @ Spartanburg** | 25 Jun 2026 | New use case: **logistics sequencing** — parts arrive unsorted in large containers, robot picks & sorts into a sequencing trolley, trolley moves to a collection point, tugger/STR delivers "just in sequence" to the line. [Press release](https://www.press.bmwgroup.com/global/article/detail/T0458778EN/bmw-group-advances-the-use-of-physical-ai-in-production-with-figure-03-project-in-spartanburg?language=en) | Official |
| 3 | **Hack‑N‑Agent / "Hack an Agent"** (internal, Plant Spartanburg) | Apr–May 2026 | 72 h, 15 teams, 17 PoCs: map a real manufacturing/business process, rebuild it as an **agentic workflow in n8n**. Example: IT-ticket triage agent that routes tickets & forces a Teams call for P1s. [Source](https://www.linkedin.com/posts/bmw-manufacturing_bmwmanufacturing-plantspartanburg-ai-activity-7458173952012570624-JisE) | Exact theme; individual tasks were team-chosen |
| 4 | **Constructor GenAI Hackathon 2026** (Bremen, with Lovable) | Apr 2026 | BMW track "**AI for People & Leadership Strategy**": AI decision tools & multi-agent systems for leadership/talent management (~200 students). [Source](https://constructor.university/news/hack-build-repeat-constructor-genai-hackathon-powers-48-hours-innovation) | Track title exact |
| 5 | **AEON humanoid @ Plant Leipzig** (with Hexagon Robotics, **Zurich**) | Dec 2025 → pilot summer 2026 | Multifunctional humanoid on wheels with swappable grippers/scanning tools; tasks in **high-voltage battery assembly and component manufacturing**; material delivery, obstacle navigation. [Press release](https://www.press.bmwgroup.com/global/article/detail/T0455864EN/bmw-group-to-deploy-humanoid-robots-in-production-in-germany-for-the-first-time?language=en) | Official |
| 6 | **BMW Open Innovation AI Hackathon x TUM.ai** (Startup Garage, Garching) — *closest analogue to Zurich* | 24–26 Oct 2025 | Brief: "Build AI systems that **act, not just answer**" — use cases in **robotics** and **innovation management**. 40 people, 13–14 teams, 3 challenge tracks/winners. Known track: **"Contact Retrieval Challenge"** (AI to analyze/extract/make sense of contact-related data; business purpose confidential). Another team built "Quant", a quantitative-analysis tool. Co-sponsors OpenAI, Vercel, MCML, CDTM. [TUM.ai](https://www.tum-ai.com/events) · [winner post](https://www.linkedin.com/posts/sshibinthomass_bmw-tumai-hackathon-activity-7388553987920179200-e1rP) · [BMW recap](https://www.linkedin.com/posts/dominikpietsch_bmwhackathon2025-ai-robotics-activity-7392217955289354240-tq2V) | Themes exact; full prompts **NOT PUBLIC** |
| 7 | **Munich Humanoid Manipulation & AI Hackathon** (RoboTUM / MIRMI / Poke & Wiggle; sponsors NVIDIA, Siemens, BMW) | 15–21 Sep 2025 | BMW task: **an assembly task normally done by multiple robots on the line**, to be solved by a humanoid-like bimanual system (2× Franka 7‑DOF, humanoid camera placement); train policies. Winners: LLM-orchestrated multi-expert agent (deterministic skills + learned policies), solved half the task, only team whose model **detected task completion and moved to the next task**. [Winner 1](https://www.linkedin.com/posts/oliver-sanchez-532433111_just-won-the-munich-humanoid-manipulation-activity-7375858041134596096-N86-) · [Winner 2](https://www.linkedin.com/posts/abheeman_last-week-i-had-the-chance-to-take-part-in-activity-7375955631855398932-78ff) · [Sponsor post](https://www.linkedin.com/posts/nicolas-m-keller_were-excited-to-welcomebmw-groupas-a-sponsor-activity-7371796870710415361-w-Pj) | Task category exact; specific part **NOT PUBLIC** |
| 8 | **robo.innovate Hackathon 2025** (MIRMI/TUM) | 17–20 Mar 2025 | "**#02 BMW Automated Unpacking**": design a robot gripper (+ optional external device) to **unpack individually packaged car parts in a pick‑and‑place task** — a side process of robotic kitting in production logistics. Winner ExVO: Franka arm + vision + ML pinch‑point detection, Robot‑as‑a‑Service. [Challenge page](https://roboinnovate.mirmi.tum.de/roboinnovate-hackathon-2025/) · [MIRMI recap](https://www.mirmi.tum.de/en/mirmi/news/article/roboinnovate-hackathon-2025-advancing-robotics-and-ai-solutions/) | **Exact wording public** |
| 9 | **Constructor Univ. BMW Causal ML Hackathon** | Nov 2024 | Causal ML / advanced analytics on real automotive (engine manufacturing / e‑mobility) data; judged on visualization, explainability, model quality, prescriptive analytics. Data released on GitHub at kickoff. [Page](https://constructor.university/lp/causal-machine-learning-hackathon) | Theme exact |
| 10 | Smart City Hack (TUM/Devpost) | Oct 2021 | "Park & Charge" — EV charging-station data analysis for city planning. [Devpost](https://devpost.com/software/park-charge-bmw-challenge-smart-city-hack) | Exact |
| 11 | Clemson Deep Orange 17 (not hackathon) | 2024–26 | "Can a vehicle generate more energy than it consumes?" | Exact |

**Pattern [INFERRED]:**
1. Since 2025 BMW's external student hackathons are **either (a) robotics/physical-AI on real production-logistics tasks (unpacking, kitting, assembly sub-steps, sequencing) or (b) agentic AI that "acts" on an enterprise workflow (retrieval, routing, decision support).**
2. BMW always frames it as *a real, unsolved problem from a plant/business unit*, judged by practitioners; business value + scalability count as much as tech.
3. Exact prompts are revealed at kickoff and often confidential afterwards — **expect a challenge you first read on Saturday morning**.

---

## 4. The "physical AI" tip — how credible, and what it would look like

Evidence that supports your source **[CONFIRMED context]**:
- BMW has a **Center of Competence for Physical AI in Production** (Feb 2026), humanoid pilots in Spartanburg (Figure), Leipzig (Hexagon **AEON — Hexagon Robotics is headquartered in Zurich**), and a software hub in Landshut (Jul 2026).
- BMW's *last* TUM.ai hackathon (Oct 2025) was literally titled "Open Innovation **Robotics** AI Hackathon", and BMW's other 2025 hackathons were robot-manipulation tasks.
- BMW's stated production-AI stack: digital twins/virtual factory, **AIQX** visual+acoustic quality inspection, autonomous Smart Transport Robots, unified data platform → "digital AI agents take on increasingly challenging tasks autonomously".

Reality check **[INFERRED]**: it's a 24‑hour, 75‑person, city-centre hackathon with no robotics lab. So "physical AI" almost certainly means **software around robots/production**, not driving a Franka arm. Most plausible forms:

| Rank | Plausible BMW Zurich problem statement | Why |
|---|---|---|
| 1 | **Task planning / orchestration for humanoids or mobile robots in logistics**: given a scene (images/video/sim/synthetic data) and a job (e.g. sequencing unsorted parts into a trolley, kitting), produce a verified plan, detect task completion, handle failure & re-plan. VLM/LLM orchestrating deterministic skills. | Exactly the Figure 03 sequencing use case + Landshut "perceive → evaluate → act" + what won the 2025 humanoid hackathon |
| 2 | **Data flywheel for robot learning**: turn demonstration data (video, mocap, teleop logs) into structured training data; auto-label, segment into skills, generate sim scenarios, evaluate VLA policies offline. | Landshut press release is all about training data, sim, and "generalisable policies"; 2025 winners said data collection & policy evaluation were the bottlenecks |
| 3 | **AI quality inspection / anomaly detection** (visual/acoustic) with explainability and operator feedback loop | AIQX is a BMW standard; classic hackathon-sized CV task |
| 4 | **Digital twin / simulation agent**: LLM agent that queries a factory digital twin or logistics data and recommends/executes decisions (STR routing, line balancing, sequencing) | "AI agents operating on unified production data" is BMW's stated direction |
| 5 | **Agentic enterprise workflow** (non-physical): retrieval over messy docs/contacts, process automation, decision copilots for innovation management / people strategy | Every non-robotics BMW hackathon since 2025 (Contact Retrieval, Hack‑N‑Agent, Leadership Strategy) |
| 6 | Vehicle/software-side (ADAS agents, cockpit AI, EV charging analytics) | Older pattern; less likely from the Open Innovation team but possible |

My probability split [INFERRED]: ~60% one of #1–#4 (physical-AI-flavoured software), ~30% #5, ~10% other.

---

## 5. How to prepare (next 2 days)

**Reusable scaffold to have in a repo before Friday** (can adapt to #1–#5 in an hour):
- Agent loop: **perceive → plan → act (tool calls) → verify → recover**, with an explicit *task-completion detector* and *failure/recovery* path — this is the exact thing BMW's 2025 winners were praised for. Log every step (traceability = safety story for BMW).
- Pluggable "environment": one adapter for a **simulator** (e.g. MuJoCo / Isaac Sim / PyBullet / even a 2D grid mock of a sequencing trolley), one for image/video input. Being able to show a robot *doing* the plan in sim beats slides.
- VLM/LLM pipeline (OpenAI/Anthropic; OpenAI credits likely available) for scene understanding + structured JSON plans; small CV utilities (SAM/YOLO/CLIP) ready.
- Eval harness that spits out **numbers** (success rate, cycle time, cost, error rate) — EHL Munich challenges were scored; judges love a chart.
- Dashboard shell (Next.js/Streamlit) for the demo + a 2-minute pitch template: problem → why it's unsolved at BMW → live demo → metrics → scaling path (BMW always judges business value/scalability).
- Entire CLI installed and checkpointing from the first commit (free side points).

**Domain knowledge to read (1 hour):** the three BMW press releases above (Leipzig, Figure 03, Landshut) + AIQX + Smart Transport Robots. Use BMW's own vocabulary in the pitch: *sequencing, kitting, just‑in‑sequence, STR, iFACTORY, AIQX, Center of Competence for Physical AI, VLA, policies, multifunctional humanoid*.

**Team roles (3–5):** 1 agent/LLM engineer, 1 CV/robotics-sim person, 1 data/eval person, 1 full-stack demo + pitch. Decide roles now.

**On-site tactics:** talk to the BMW mentors in the first hour and ask "what does the plant actually struggle with here?" — the Oct 2025 winners credited their mentor; the humanoid winners won by solving *more of the real task* (partial but autonomous) rather than a polished fake.

---

## 6. Gaps (could not find publicly)
- Full Zurich partner list, venue, and any challenge text (not released as of 10 Sept 2026).
- Exact prompt text for BMW's Oct 2025 TUM.ai tracks (only "Contact Retrieval Challenge" name is public) and the exact assembly part in the Sept 2025 humanoid task.
- No statement from BMW/EHL that the Zurich challenge is about physical AI — your tip is consistent with all the evidence but remains unconfirmed.
