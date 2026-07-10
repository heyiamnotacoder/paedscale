# CLAUDE.md — PaedScale

Guidance for Claude Code sessions working in this repo.

## What this is

PaedScale is a **generalizable multi-agent pediatric dose-extrapolation agent** for the "Built with
Claude: Life Sciences" hackathon. A free-text clinical query drives a Sonnet orchestrator that either
returns a **published guideline dose** (when solid and the child has normal organ function) or spawns
a single **research-agent** (Haiku) to gather pathways + adult PK + safety bounds from the literature
(PubMed · Semantic Scholar · web). Mechanistic doses use **allometric scaling × organ maturation
(Anderson–Holford)** in deterministic Python. A mandatory **critic-agent** grades every dose before
submit. It generalizes to any drug — there is no prefill drug set.

The authoritative concept brief is `docs/paedscale-concept.html` — read it before making product
decisions. This file is the engineering guide.

## Golden rule: keep the LLM and the math separate

- **Deterministic Python (`backend/app/pk/`)** owns ALL numbers: allometry, maturation, Vd
  correction, dose solve. No LLM calls here. This is what tests pin.
- **Claude (`backend/app/agent/`)** owns judgment and language: mapping a drug to its elimination
  pathways (fm split), retrieving/annotating adult PK, and writing the cited rationale. It must NOT
  invent the final dose — it feeds structured inputs to `pk/` and explains the result.
- **Exception (guideline short path):** when a solid published regimen matches and the child is
  **not** renally/hepatically impaired, the orchestrator may return that mg/kg (converted to mg for
  weight) with `source_of_dose="guideline"`. No fake allometry. Critic still runs.

If you find yourself asking Claude to "compute the dose," stop — that belongs in `pk/`.

## Architecture

```
backend/app/
  pk/          allometry · maturation · distribution · methods · organ_function ·
               safety · concordance · pipeline            (pure functions — ALL the math)
  agent/       orchestrator.py  (Agent SDK: research + critic, budget, partial recovery)
               math_tools.py    (in-process MCP: pk/ exposed as tools — golden rule)
               research_tools.py(in-process MCP: PubMed + Semantic Scholar)
               recovery.py      (assemble payload if submit never fires)
               stream.py        (SDK messages → SSE trace events)
               intake.py        (free-text → covariates)  · adult_pk.py/pathways.py (legacy helpers)
  data/        maturation.json  (drug-agnostic pathway curve library — the ONLY data file)
  schemas.py   pydantic QueryRequest / ExtrapolationResponse
  main.py      FastAPI: POST /extrapolate (JSON) · POST /extrapolate/stream (SSE) · CORS
backend/tests/fixtures/  validation_drugs.json · validation_guidelines.json  (test-only)
frontend/      Next.js (App Router, TS). Free-text box + live reasoning sidebar; teal/paper tokens.
```

### Runtime pipeline

```
free-text query
    → intake (covariates + organ_impaired?)
    → solid published regimen AND not organ-impaired?
         YES → guideline dose (source_of_dose=guideline)
         NO  → research-agent (pathways + adult PK + safety + guideline cases)
               → extrapolate_dose → check_safety_bounds → find_concordance?
               → source_of_dose=mechanistic
    → critic-agent (mandatory; dose_grade: accept | accept_with_caveats | revise)
    → submit_recommendation
    → if submit missing: recovery.assemble_partial_payload (source_of_dose=partial_recovery)
```

**Organ impairment veto:** renal or hepatic impairment (stated, low eGFR, high SCr for age,
Child-Pugh ≥7, liver disease, AKI) **always** forces the full mechanistic path. Guidelines are
population averages; PaedScale exists to individualise.

## Conventions

- **Models (tiered for cost, env-configurable):** Sonnet orchestrator + critic, Haiku research-agent —
  see `PAEDSCALE_*` in `.env.example`. Hard budget ceiling **~$2** (`PAEDSCALE_BUDGET_USD`); typical
  runs should stay much lower. Read `ANTHROPIC_API_KEY` from env (`.env`, gitignored). Never hardcode
  or commit keys.
- **Deployment needs the Claude CLI runtime:** the Agent SDK spawns the `claude` Node binary, so the
  backend deploys via `backend/Dockerfile` (Python + Node + `@anthropic-ai/claude-code`), wired in
  `render.yaml`. A plain Python runtime will not work.
- **Subagents:** only `research-agent` and `critic-agent`. Both `background=False` (synchronous Task).
  Async team tools are disallowed (`ScheduleWakeup`, `TaskOutput`, `SendMessage`, `ToolSearch`, …).
- **Generalizable, not prefill:** there is no curated drug set. Agents research each drug live;
  `data/maturation.json` is the drug-agnostic pathway curve library. The three former demo drugs live
  only in `tests/fixtures/` as a validation set.
- **Safety must surface in output:** decision-support-only disclaimer, NTI→TDM warnings, safety-bounds
  clamp/flag, evidence grade, assumed-default flags, critic `dose_grade`, `source_of_dose`. Never emit
  a false-confident number.
- **Concordance = the test suite:** `backend/tests/test_concordance.py` asserts the PK math reproduces
  known guideline doses (from `tests/fixtures/`) within tolerance. Keep it green. Live agent runs cost
  money — validate with the offline/mocked suite; never run the orchestrator ad hoc in a loop.

## Working style

- **Phased delivery with a push after every phase.** Commit and `git push` when a phase is done;
  don't batch phases. Repo: `github.com/heyiamnotacoder/paedscale` (public).
- Use `gh` CLI for GitHub operations.
- Co-author trailer on commits:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

## Commands

```bash
# backend
cd backend && pytest
cd backend && uvicorn app.main:app --reload
# frontend
cd frontend && npm run dev
```

---

## Changelog: agent reliability rewrite (`cd74841`, 2026-07-10)

Problem: live runs took >1 min, cost ~$0.7+, often returned **no result**. Trace showed `ToolSearch`,
generic `local_agent`, `ScheduleWakeup` / `TaskOutput` thrash, overlapping literature calls, and
exit without `submit_recommendation` (budget interrupt at $0.40 left an empty payload).

### Behaviour before → after

| Area | Before | After |
|------|--------|--------|
| Research agents | 3 parallel: pathway / pk / safety (Haiku) | 1× `research-agent` (Haiku, maxTurns≈7) |
| Critic | Optional / often skipped under turn pressure | **Mandatory** `critic-agent` with `dose_grade` |
| Guideline use | Concordance only after full research | **Short path** if solid regimen **and** no organ impairment |
| Organ impairment | Not a path gate | Always full mechanistic path |
| Subagent mode | Default could be background (async thrash) | `background=False` always |
| Tools | Deferred ToolSearch; team tools usable | Disallow ToolSearch / ScheduleWakeup / TaskOutput / SendMessage / file tools |
| Budget | Default $0.40 soft interrupt | Default **$2.0** + native `max_budget_usd` |
| Empty result | 502 / blank UI if no submit | `recovery.py` assembles dose from math tool results |
| Result metadata | — | `source_of_dose`: guideline \| mechanistic \| partial_recovery |

### Diff by file

#### New files

| File | Purpose |
|------|---------|
| `backend/app/agent/recovery.py` | Scan SDK messages for last `extrapolate_dose` / `check_safety_bounds` / `find_concordance` JSON; build minimal recommendation if `submit_recommendation` never ran. Sets `source_of_dose=partial_recovery`, `evidence_grade=very-low`, safety flag `assembled_from_partial_run`. |
| `backend/tests/test_recovery.py` | Unit tests: math extraction, partial payload shape, budget default ≥$2, only research+critic agents, `background=False`, disallowed tools, prompt organ-impairment + critic invariants. |
| `AGENTS.md` | Codex-oriented twin of this engineering guide (kept in sync on agent architecture). |

#### `backend/app/agent/orchestrator.py` (major rewrite)

- Replaced `pathway-agent` / `pk-agent` / `safety-agent` with single **`research-agent`** (tools: literature MCP + WebSearch + WebFetch; compact JSON out: adult_pk, pathways, safety, guideline_cases, citations).
- **`critic-agent`**: tools=[], maxTurns=1, Sonnet default; returns objections + `dose_grade` (`accept` \| `accept_with_caveats` \| `revise`) + residual risks.
- Both agents: **`background=False`**.
- System prompt: intake → organ impairment gate → guideline short path vs full research → math once → **mandatory critic** → `submit_recommendation`. Ban ToolSearch / waiting / re-spawn.
- `ClaudeAgentOptions`: `max_budget_usd=BUDGET_USD` (default **2.0**), `disallowed_tools` (async team + ToolSearch + Bash/Read/Write/…), `strict_mcp_config=True`.
- Soft interrupt only if over budget **and** no payload **and** math has not already succeeded (prefer finishing critic+submit).
- After stream ends without payload: call `assemble_partial_payload(messages, query)`.
- `SUBMIT_SCHEMA`: added `source_of_dose`, `critique.dose_grade`; critic required in prompt before submit.
- Env: `PAEDSCALE_RESEARCH_MAX_TURNS` (default 7); `PAEDSCALE_BUDGET_USD` default **2.0**.

#### `backend/app/agent/research_tools.py`

- Process-level **query cache** (TTL 10 min) for PubMed + Semantic Scholar.
- Shared **`httpx.AsyncClient`** (no new client per call).
- Semantic Scholar **429**: clear error — do not retry; use PubMed/WebSearch.
- `clear_research_cache()` for tests.

#### `backend/app/agent/math_tools.py`

- **In-memory cache** of `maturation.json` (`_MATURATION_LIBRARY`) — load once per process.

#### `backend/app/agent/stream.py`

- Labels for `ToolSearch`, `ScheduleWakeup`, `TaskOutput`, `TaskGet`, `SendMessage`.
- Agent labels: `research-agent`, `critic-agent` (+ legacy pathway/pk/safety/local_agent).
- Attribute Task children from tool input `subagent_type` / `agent` when present.

#### `backend/app/schemas.py`

- `CritiqueOut.dose_grade: str | None`
- `ExtrapolationResponse.source_of_dose: str` (default `"mechanistic"`)

#### `backend/app/main.py`

- Comment only: streaming is UX for multi-agent runs (not fixed 25–40s claim).

#### `backend/.env.example`

```
PAEDSCALE_BUDGET_USD=2.0
PAEDSCALE_RESEARCH_MAX_TURNS=7
PAEDSCALE_SUBAGENT_MAX_TURNS=7
# (models + MAX_TURNS unchanged in spirit; budget no longer 0.40)
```

#### Tests

| File | Change |
|------|--------|
| `backend/tests/test_recovery.py` | **New** — recovery + orchestrator invariants |
| `backend/tests/test_api.py` | CANNED payload includes `source_of_dose`, `critique.dose_grade`; asserts on response |
| `backend/tests/test_stream.py` | Trace uses `research-agent` instead of `pk-agent` / `pathway-agent` |

#### Frontend

| File | Change |
|------|--------|
| `frontend/lib/types.ts` | `source_of_dose?`, `Critique.dose_grade?` |
| `frontend/components/DoseResult.tsx` | Shows dose source (guideline / mechanistic / partial recovery) |
| `frontend/components/CritiquePanel.tsx` | Shows critic dose grade |
| `frontend/components/ReasoningSidebar.tsx` | Chips for `research-agent` / `local_agent`; keep legacy agents |

#### Docs (this rewrite session + prior)

| File | Change |
|------|--------|
| `CLAUDE.md` | Architecture, pipeline, conventions, **this changelog** |
| `AGENTS.md` | Engineering guide aligned with agent rewrite |
| `README.md` | Public product + run docs aligned with free-text multi-agent flow |

### What not changed

- `backend/app/pk/*` pure math (still golden rule / concordance tests).
- HTTP API shape: still `POST /extrapolate` and `POST /extrapolate/stream`.
- Validation fixtures for midazolam / vancomycin / morphine (test-only).
- No live orchestrator loops in CI (mocked API tests only).

### Verification

```bash
cd backend && pytest   # expect 51+ passed
```

Live smoke (manual): well child + common antibiotic → often guideline path; same + renal/hepatic
impairment → mechanistic; unlabeled drug → research → math → critic → submit.
