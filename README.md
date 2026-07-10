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
    ├─ intake (covariates, organ impairment?)
    │
    ├─ solid guideline + normal organ function?
    │      YES → guideline dose  ──┐
    │      NO  → research-agent    │
    │            (PubMed · S2 · web)│
    │            → allometry × maturation (Python)
    │            → safety bounds · concordance
    │                              │
    └──────────── critic-agent ────┘
                    (dose grade)
                         │
              submit_recommendation
                         │
         (fallback: partial recovery from math tools)
```

| Layer | Role |
|-------|------|
| **Orchestrator** (Sonnet) | Plan path, call tools, assemble result |
| **research-agent** (Haiku) | One specialist: pathways (fm), adult PK, safety window, guideline cases |
| **critic-agent** (Sonnet) | Mandatory red-team + `dose_grade` before submit |
| **Python `pk/`** | All numbers: allometry, Hill maturation, organ function, dose solve |

**Golden rule:** the LLM does not invent the mechanistic dose — it feeds structured inputs into
`mcp__paedscale_math__*` tools and explains the result.

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
backend/   FastAPI — Claude Agent SDK orchestrator + deterministic PK (Python)
  app/pk/          pure math
  app/agent/       orchestrator, research/math MCP tools, recovery, stream
  app/data/        maturation.json (pathway curve library)
  tests/           pytest (math + mocked API + recovery)
frontend/  Next.js (App Router, TypeScript) — free-text query + live reasoning sidebar
docs/      Concept brief (paedscale-concept.html), concordance analysis
```

Engineering conventions for agents/IDEs: **`CLAUDE.md`** / **`AGENTS.md`** (full changelog of the
agent reliability rewrite is in `CLAUDE.md`).

---

## Run locally

Requires Python 3.11+, Node 18+, and the Claude Agent SDK runtime (Node `claude` CLI is pulled by
the SDK / Docker image).

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
PAEDSCALE_BUDGET_USD=2.0
PAEDSCALE_MAX_TURNS=14
PAEDSCALE_RESEARCH_MAX_TURNS=7
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL → http://localhost:8000
npm run dev                        # http://localhost:3000
```

Open `http://localhost:3000`, enter a free-text case, watch the **reasoning sidebar** stream, then
read the dose card (source, critic grade, pathways, concordance, disclaimer).

### API

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `POST /extrapolate` | JSON body `{ "query": "..." }` → full `ExtrapolationResponse` |
| `POST /extrapolate/stream` | Same query; SSE events: `trace` · `result` · `error` · `done` |

---

## Demo script (~90s)

1. **Problem (10s).** Linear mg/kg ignores maturation — neonates clear less than weight scaling implies.
2. **Guideline-ish case (25s).** e.g. oral amoxicillin for AOM in a well 1-year-old — often a fast
   **guideline** path + critic; note `source_of_dose`.
3. **Impaired case (25s).** Same drug with renal or hepatic impairment — **must** take the
   mechanistic path (organ modifiers); no guideline short-circuit.
4. **Result card (20s).** Dose mg/mg/kg, method, critic dose grade, safety flags, concordance badge.
5. **Sidebar (10s).** Live research / math / critic tool calls — not a black box.

---

## Deploy

- **Backend (FastAPI):** root `render.yaml` + `backend/Dockerfile` (Python **and** Node/`claude-code`).
  Set `ANTHROPIC_API_KEY`, `ALLOWED_ORIGINS` (your Vercel origin), optional `PAEDSCALE_*` knobs.
- **Frontend (Next.js):** deploy `frontend/` on Vercel. Set `NEXT_PUBLIC_API_BASE_URL` to the
  Render backend URL.

Redeploy after env changes.

---

## Recent reliability work

Live multi-agent runs used to thrash (async task polling, ToolSearch, three overlapping research
agents) and sometimes finished **with no structured result**. The stack now:

- Forces **synchronous** research + critic agents
- Collapses research to **one** specialist
- Raises the hard budget ceiling to **~$2** so critic + submit can finish
- **Recovers** a dose from math tool outputs if submit never fires
- Short-circuits **guidelines only** when organ function is intact

Details and file-level changelog: **`CLAUDE.md`**.

---

## License

Prototype for a hackathon. Not for clinical use.
