# ETH Agentic Systems Lab — Track Brief for EHL Zurich (12–13 Sep 2026)

Prepared 10 Sep 2026. Sources: agenticsystemslab.org, github.com/Agentic-Systems-Lab, github.com/OpenTSLM, opentslm.com, arXiv 2510.02410, lab/Founderful LinkedIn posts, EHL Zurich Notion page. Anything marked *(inference)* is my read, not a published fact.

---

## 1. Who judges you and what they value

| Person | Role | What they care about (from public record) |
|---|---|---|
| **Dr. Robert Jakob** | Founder/Co-Director; wrote & judged the Colosseum challenge | "Beyond LLM wrappers and vibe coding": orchestration, **fine-tuning**, robust engineering, scalability. Author of OpenTSLM, `rigorous` (multi-agent AI peer reviewer with QC loops). Also co-founder of Aionic Labs (commercial TSLMs). |
| **Dr. Kevin O'Sullivan** | Co-Director | Keynote thesis (Jun 2026): "most businesses need **fewer agents** than they think, each doing far more" — one long-context agent with many turns > swarm of narrow agents; structured output that fits existing systems first pass. |
| **Robin Deuber** | Lead AI in HCI & Robotics | Embodied/physical agents (ZHAW robots at Agentic Hack). |
| Founderful / partner VC | Usually co-judge | Startup potential, "is there a company here". |

Pattern from their two 2026 hackathons: **open brief → you choose problem & data → 24h build → demo + pitch**. No leaderboard, no hidden test set. Winner (Trajecta) = fine-tuned the judge's own model (OpenTSLM) on a new modality + built an **auditor agent** that fact-checks every generated sentence against raw data.

*(inference)* Expect the Zurich brief to read like: "Build an agentic system that reliably performs a real-world task end-to-end, in a domain of your choice (suggested: healthcare / insurance / manufacturing / energy)". Possibly a sample dataset or partner API; not confirmed.

## 2. Their open-source stack (what you can build on)

### 2.1 OpenTSLM — Time-Series Language Models (flagship, ICML 2026, 1.2k stars)
- Repo: https://github.com/OpenTSLM/OpenTSLM · `pip install opentslm` · HF org `OpenTSLM` (51 checkpoints) · site opentslm.com
- What it is: time series as a **native modality** of an LLM (like images in a VLM). Prompt in natural language over one or many series of any length → answer, caption, chain-of-thought rationale.
- Two architectures:
  - `OpenTSLMSP` (soft prompt): TS encoder → learnable tokens concatenated with text. Small, cheap.
  - `OpenTSLMFlamingo`: TS injected via cross-attention (Flamingo-style). Better, more VRAM.
- Backbones: Llama-3.2-1B (default), Llama-3.2-3B, Gemma-3-270m, Gemma-3-1b-pt (gated HF — request access TODAY).
- Checkpoints: `OpenTSLM/{backbone}-{tsqa|m4|har|sleep|ecg}-{sp|flamingo}`.
- Results: 1B models beat GPT-4o on sleep staging / HAR CoT (69.9% vs ~15% F1 for text-only). Key message: **small fine-tuned TSLM >> frontier LLM reading numbers as text**.
- Training: `curriculum_learning.py` with 5 stages (MCQ → captioning → HAR CoT → Sleep CoT → ECG CoT). Adding your own stage = subclass a `*QADataset` (series + question + CoT answer). Fits on one consumer GPU / Colab A100 for the 1B SP variant in ~1–2h for a small dataset.
- Demo scripts: `demo/huggingface/01..05_test_hf_*.py`.
- Use in a hackathon: fine-tune on **your domain's time series** (demand, inventory, sensor, vitals, telemetry) with LLM-generated CoT labels → get an explainable temporal reasoner that a plain GPT call can't match. This is exactly what the winners did.

### 2.2 Agentic-AutoRAG (Feb 2026)
- Repo: https://github.com/Agentic-Systems-Lab/Agentic-AutoRAG (Python 3.12, uv, litellm — works with OpenAI keys)
- Idea: instead of grid search, an LLM **diagnoser** explains why a RAG config failed (retrieval miss vs generation error, per question type) and a **proposer** picks the next config. Fitness = a synthetic exam auto-generated from your corpus (typed questions with ground-truth spans, cached to `exam.json`). Cost-aware Pareto frontier (accuracy vs $/query).
- Supports vector, hybrid BM25+vector, experimental graph RAG. Corpus: PDF/DOCX/XLSX/CSV/MD/HTML/images.
- Hackathon use: drop your domain docs (SOPs, supplier contracts, regulatory PDFs) into the corpus, run it, and you have a *self-optimizing* grounded retrieval layer with an eval harness for free. Mentioning "synthetic exam as optimization signal" will land with Jakob.

### 2.3 `rigorous` — AI peer reviewer (250 stars, Jakob's own)
- https://github.com/Agentic-Systems-Lab/rigorous — multi-agent manuscript review with **quality-control loops**, JSON output, PDF report. Pattern to copy: specialist agents + a critic pass + structured output.

### 2.4 Others
- `AI-Examination` (small), `thesis-template` (shows they use Claude Code heavily). MetaRAG = "orchestrate multiple retrieval strategies" (concept on site, no public repo found).
- Research talk: RLMs (recursive/looped language models) and RecursiveMAS (arXiv 2604.25917) — recursion as a scaling axis for multi-agent systems. Vocabulary only; don't try to implement in 24h.

## 3. Scoring heuristics (derived from what they praised)

1. **A trained component**, not only prompts — fine-tuned TSLM / small classifier / LoRA. Show before/after numbers.
2. **Verification layer** — an auditor agent that checks every claim against raw data; uncertainty flag ("I'm not sure enough to act").
3. **Acts, not answers** — the system takes an action in a workflow (creates an order, triggers a transfer, files a claim) with structured output that fits an existing schema.
4. **Evaluation harness** — synthetic exam / held-out set / ablation. Even 50 test cases with a table impresses.
5. **Fewer, deeper agents** (O'Sullivan) — one orchestrator with long context + tools beats 8 micro-agents. If you use multiple agents, justify each.
6. **Real environment** — real or realistic data, real constraints (latency, cost per query), a path to deployment.
7. **Startup story** — who pays, why now.

## 4. Upgrading your supply-chain work into a track-winning build

You already have: synthetic supply/demand data generation, agent loop for supply-chain decisions. Here is the "crazy version" that maps onto the lab's stack. *(All inference/design proposal.)*

### Concept: **Pharma cold-chain / hospital drug-supply autonomous controller**
Domain choice: medical supply chain (drug shortages, cold-chain vaccines, hospital pharmacy stock). High impact, time-series-heavy, regulatory docs exist (RAG), and matches the lab's healthcare DNA and Zurich Insurance's risk angle.

Architecture (one deep orchestrator + specialised tools, TSLM + AutoRAG inside):

```
                ┌──────────────────────────────────────────────┐
 streams ──────▶│  Signal layer: fine-tuned OpenTSLM (1B, SP)    │──▶ "demand for insulin at site B will
 (demand,       │  input: multivariate series per SKU/site       │     spike 40% in 5d; cold-chain sensor
  inventory,    │  output: natural-language finding + CoT + conf │     drift at truck 7 → spoilage risk 0.7"
  temp sensors) └──────────────────────────────────────────────┘
                                   │
                ┌──────────────────▼───────────────────────────┐
 docs ─────────▶│  Knowledge layer: Agentic-AutoRAG over SOPs,   │──▶ "per SOP 4.2 transfers >500 units
 (SOPs, supplier│  supplier contracts, regulatory constraints    │     need pharmacist sign-off; supplier
  contracts)    └──────────────────────────────────────────────┘     X lead time 3d, penalty clause..."
                                   │
                ┌──────────────────▼───────────────────────────┐
                │  Orchestrator agent (OpenAI, long context,     │──▶ structured ACTION JSON:
                │  tool-calling): plans re-allocation / reorder  │     {transfer, qty, from, to, reason,
                │  / reroute; simulates outcome on digital twin  │      confidence, requires_human: bool}
                └──────────────────────────────────────────────┘
                                   │
                ┌──────────────────▼───────────────────────────┐
                │  Auditor agent: re-derives every numeric claim │──▶ pass / block / escalate
                │  from raw series + checks SOP compliance       │     (Trajecta-style fact-check)
                └──────────────────────────────────────────────┘
                                   │
                        digital twin (your synthetic sim) executes → new state → loop
```

Why it scores:
- Fine-tuned model (TSLM on your synthetic + a public demand dataset, e.g. M5/Favorita or WHO shortage data) with a before/after table vs GPT-4o-as-text.
- Auditor + uncertainty → "controllable AI in real workflows" (their AI-transformation pillar).
- AutoRAG → their own repo, self-optimizing, with a synthetic exam = built-in eval.
- Closed loop on a simulator → "acts, not answers", measurable KPI (stockouts avoided, spoilage avoided, cost).
- One orchestrator, few agents → matches O'Sullivan's thesis.
- Zurich Insurance angle in pitch: cold-chain spoilage is an insured loss; the system reduces claims.

### Alternatives if the brief forces another domain
- **Energy**: same loop on grid load/solar series → dispatch decisions.
- **Manufacturing**: machine sensor series → predictive maintenance work orders (BMW Motorrad crossover!).
- **Insurance ops**: claims documents (RAG) + telematics series (TSLM) → automated first-notice-of-loss triage with auditor.
- **Robotics/embodied** (if ZHAW robots appear again): TSLM on robot joint/IMU series for anomaly → agent re-plans.

## 5. Pre-hackathon checklist (do tonight / tomorrow)

- [ ] Request HF access to `meta-llama/Llama-3.2-1B` and `google/gemma-3-270m` (gated; can take hours).
- [ ] `git clone https://github.com/OpenTSLM/OpenTSLM && uv sync`; run `demo/huggingface/03_test_hf_har_cot.py` on CPU to confirm the pipeline.
- [ ] Write a `SupplyChainCoTQADataset` stub: (series[], question, CoT answer). Generate CoT labels with GPT for ~2–5k windows from your synthetic generator. Have a Colab/Lambda GPU ready (A100 ≈ $1–2/h; €75 OpenAI credits cover the labelling).
- [ ] `git clone https://github.com/Agentic-Systems-Lab/Agentic-AutoRAG`; run `uv run agentic-autorag info` with your OpenAI key; try on 10 PDFs.
- [ ] Port your digital-twin simulator into a clean `step(state, action) -> state, kpis` interface.
- [ ] Prepare the auditor prompt: "given raw arrays + claim, recompute and return {claim, recomputed_value, verdict}".
- [ ] Eval table template: metric | GPT-4o-text | fine-tuned TSLM | Δ.
- [ ] Install Entire (`curl -fsSL https://entire.io/install.sh | bash && entire enable`) — mandatory for submission; it records your agentic dev sessions, so commit often with clear intent.
- [ ] Pitch skeleton (3 min): problem & cost → live demo of one incident handled end-to-end → eval table → architecture (1 slide) → business/next steps → "we'd like to continue this as a thesis with ASL".

## 6. Gaps / unknowns
- Exact brief, dataset, and whether robots/partner APIs are provided: revealed Sat 11:00.
- MetaRAG public code: not found.
- Whether judges will include Zurich Insurance or Founderful this time: not announced.
