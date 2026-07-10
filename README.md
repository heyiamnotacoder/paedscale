# PaedScale

**Dosing children where the guidelines run out.**

PaedScale is a **generalizable multi-agent pediatric dose-extrapolation agent**. You type a free-text
clinical question (drug, age/weight, indication, renal/hepatic notes). A Claude orchestrator either:

1. **Returns a published guideline regimen** when one clearly matches *and* the child has normal
   organ function, or
2. **Researches** adult PK + elimination pathways, then scales with **allometric scaling × organ
   maturation (Anderson–Holford)** in deterministic Python.

Every recommendation is **cited**, **self-critiqued** (mandatory critic with a dose grade), and
optionally **concordance-checked** against published pediatric doses. It works for **any drug** —
there is no fixed demo drug list in the product path.

Built for the **Built with Claude: Life Sciences** hackathon (Claude × Gladstone Institute),
Development Track.

> ⚠️ **Decision support, not prescribing.** PaedScale produces a defensible *starting estimate* for a
> qualified clinician — never an autonomous order. Narrow-therapeutic-index drugs must be confirmed
> with therapeutic drug monitoring. Not a validated clinical-decision-support device.

---

## Why

Drugs are licensed in adults first; pediatric labeling lags by years or never arrives (the
"therapeutic orphan" problem). Where no pediatric data exist, clinicians fall back on linear
`dose = adult_dose × weight/70` — which **overdoses the young**, because the organs that clear the
drug (hepatic enzymes, kidneys) are still maturing. PaedScale encodes that maturation gap.

When a solid guideline *does* exist for an uncomplicated child, PaedScale can return it quickly.
When the child is **renally or hepatically impaired**, or no regimen fits, it always runs the
**mechanistic** path — that individualisation is the product.

---

## How it works

```
Free-text query
    │
    ├─ intake.parse (Python): covariates · organ impairment? · edge case?
    │
    ├─ fetch_drug_pk (openFDA)  ∥  guideline-agent      (run concurrently)
    │
    ├─ orchestrator loop (Sonnet, in-process Messages API):
    │      solid guideline + normal organ function? → guideline dose
    │      else → allometry × maturation via PK-maths tools → safety · concordance
    │      edge case → agentic PubMed / MCP research
    │      → self-critique (dose grade) → submit_recommendation
    │
    └─ (fallback: partial recovery from captured math results)
```

| Layer | Role |
|-------|------|
| **Orchestrator** (Sonnet, one in-process agent loop) | Plan path, call tools, self-critique, assemble |
| **guideline-agent** (Sonnet, parallel) | Published pediatric mg/kg regimens for concordance |
| **edge-research-agent** (edge-only) | PubMed / ClinicalTrials MCP for unlabelled / edge drugs |
| **fetch_drug_pk** (openFDA + seed cache) | Deterministic adult PK on the happy path |
| **Python `pk/`** | All numbers: allometry, Hill maturation, organ function, dose solve |

**Golden rule:** the LLM does not invent the mechanistic dose — it feeds structured inputs into the
deterministic PK-maths tools and explains the result.

### Maturation model (per elimination pathway)

```
CL_child = CL_adult × (WT/70)^0.75 × MF(PMA) × OF
MF(PMA)  = PMA^H / (TM50^H + PMA^H)
```

`WT` weight · `PMA` postmenstrual age · `TM50` age at 50% maturation · `H` Hill coefficient ·
`OF` organ-function modifier.

### Result fields worth knowing

| Field | Meaning |
|-------|---------|
| `source_of_dose` | `guideline` · `mechanistic` · `partial_recovery` |
| `dose_recommendation` | mg, mg/kg, interval, method, safety bounds |
| `critique.dose_grade` | `accept` · `accept_with_caveats` · `revise` |
| `evidence_grade` | high → very-low |
| `concordance` | vs published mg/kg when cases found |
| `cost_usd` | measured inference cost for the run |

Hard cost ceiling defaults to **~$2/query** (`PAEDSCALE_BUDGET_USD`); typical runs should be far lower.

---

## Validation set (offline tests only)

The product researches any drug live. Offline concordance tests still pin the PK engine against
three archetypes:

| Drug        | Archetype               | Pathway  |
|-------------|-------------------------|----------|
| Midazolam   | Hepatic CYP             | CYP3A4   |
| Vancomycin  | Renal                   | GFR      |
| Morphine    | Hepatic glucuronidation | UGT2B7   |

Fixtures live under `backend/tests/fixtures/` — not loaded as a product prefill catalog.

---

## Repo layout

```
backend/   FastAPI — in-process Messages-API agent loop + deterministic PK (Python)
  app/pk/          pure math
  app/agent/       orchestrator, math/research tools, intake, recovery
  app/data/        maturation.json (pathway curve library)
  app/report.py    PDF export via the pdf Agent Skill
  skills/          custom pediatric-pk methodology Skill
  tests/           pytest (math + mocked API + offline agent loop + recovery)
frontend/  Next.js (App Router, TypeScript) — dark search home, collapsible reasoning, inline cites
docs/      Concept brief (paedscale-concept.html), concordance analysis
```

Engineering conventions for agents/IDEs: **`CLAUDE.md`** / **`AGENTS.md`** (see the changelog
"in-process Messages-API rewrite" in `CLAUDE.md`).

---

## Run locally

Requires Python 3.11+ only — the orchestrator runs in-process on the Anthropic Messages API
(`anthropic` Python SDK). No Node, no Claude Code CLI.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # set ANTHROPIC_API_KEY; ALLOWED_ORIGINS for the frontend origin
pytest                        # offline suite (no live agent spend)
uvicorn app.main:app --reload # http://localhost:8000
```

Useful env knobs (see `.env.example`):

```
ANTHROPIC_API_KEY=...
ALLOWED_ORIGINS=http://localhost:3000
PAEDSCALE_ORCH_MODEL=claude-sonnet-5
PAEDSCALE_MAX_TURNS=8
PAEDSCALE_GUIDELINE_AGENT=1          # parallel guideline sub-agent (0 to disable)
OPENFDA_API_KEY=                     # optional; raises the openFDA rate limit
PAEDSCALE_MCP_SERVERS=               # optional JSON: route edge literature via an MCP server
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL → http://localhost:8000
npm run dev                        # http://localhost:3000
```

Open `http://localhost:3000`, enter a free-text case, expand the **one-line reasoning** trace as it streams, then
read the dose card (source, self-critique grade, pathways, concordance, disclaimer).

### API

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `POST /extrapolate` | JSON body `{ "query": "..." }` → full `ExtrapolationResponse` |
| `POST /extrapolate/stream` | Same query; SSE events: `trace` · `result` · `error` · `done` |
| `POST /report` | JSON recommendation → PDF dosing report (via the `pdf` Agent Skill) |

---

## Demo script (~90s)

1. **Problem (10s).** Linear mg/kg ignores maturation — neonates clear less than weight scaling implies.
2. **Guideline-ish case (25s).** e.g. oral amoxicillin for AOM in a well 1-year-old — often a fast
   **guideline** path; note `source_of_dose`.
3. **Impaired case (25s).** Same drug with renal or hepatic impairment — **must** take the
   mechanistic path (organ modifiers); no guideline short-circuit.
4. **Result card (20s).** Dose mg/mg/kg, method, self-critique dose grade, safety flags, concordance badge.
5. **Sidebar (10s).** Live drug-data / math / self-critique tool calls — not a black box.

---

## Deploy

- **Backend (FastAPI):** root `render.yaml` (`runtime: python` — plain Python, no Node). Set
  `ANTHROPIC_API_KEY`, `ALLOWED_ORIGINS` (your Vercel origin), optional `PAEDSCALE_*` / `OPENFDA_API_KEY`.
- **Frontend (Next.js):** deploy `frontend/` on Vercel. Set `NEXT_PUBLIC_API_BASE_URL` to the
  Render backend URL.

Redeploy after env changes.

---

## Recent work

The 2026-07-11 rewrite dropped the Claude Agent SDK (which cold-spawned a Node `claude` CLI
subprocess per request, ~20s) for an **in-process Anthropic Messages-API agent loop**. The stack now:

- Runs entirely in Python — no Node, no subprocess; Sonnet 5 for everything.
- **Deterministic happy path** (openFDA drug data + PK-maths tool) with the **agentic Web/PubMed loop
  gated to edge cases** (MCP connector).
- Folds the critic into the orchestrator's **self-critique**; runs a **parallel guideline sub-agent**.
- Adds Skills: a custom `pediatric-pk` methodology Skill and a `POST /report` PDF export.
- Prompt caching, adaptive thinking, and partial-recovery fallback retained.

Details and file-level changelog: **`CLAUDE.md`** → "Changelog: in-process Messages-API rewrite".

---

## License

Prototype for a hackathon. Not for clinical use.
