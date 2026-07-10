# AGENTS.md — PaedScale

Guidance for Codex / coding-agent sessions working in this repo.

This file mirrors the engineering guide in **`CLAUDE.md`**. Prefer **`CLAUDE.md`** for the full
**changelog of the agent reliability rewrite** (`cd74841`) and file-level diffs. Keep both docs
aligned when you change pipeline behaviour.

## What this is

PaedScale is a **generalizable multi-agent pediatric dose-extrapolation agent** for the "Built with
Claude: Life Sciences" hackathon. A free-text clinical query drives a Sonnet orchestrator that either
returns a **published guideline dose** (solid regimen + normal organ function) or spawns one
**research-agent** (Haiku) to research literature (PubMed · Semantic Scholar · web), then scales
adult PK by **allometric scaling × organ maturation (Anderson–Holford)** in Python. A mandatory
**critic-agent** grades the dose before submit. No prefill drug set.

Authoritative concept brief: `docs/paedscale-concept.html`. Engineering detail + changelog: `CLAUDE.md`.

## Golden rule: keep the LLM and the math separate

- **Deterministic Python (`backend/app/pk/`)** owns ALL numbers. No LLM calls here.
- **Agent layer (`backend/app/agent/`)** owns judgment and language. It must NOT invent the
  mechanistic dose — it feeds structured inputs to `pk/` (via math MCP tools) and explains the result.
- **Guideline short path:** published mg/kg allowed only when solid **and** not renally/hepatically
  impaired; critic still runs.

## Architecture

```
backend/app/
  pk/          allometry · maturation · distribution · methods · organ_function ·
               safety · concordance · pipeline            (pure functions — ALL the math)
  agent/       orchestrator.py  (research + critic, budget ~$2, partial recovery)
               math_tools.py    (in-process MCP: pk/)
               research_tools.py(PubMed + Semantic Scholar, cached)
               recovery.py      (payload if submit never fires)
               stream.py        (SSE trace events)
               intake.py        · adult_pk.py/pathways.py (legacy helpers)
  data/        maturation.json  (only production data file)
  schemas.py   QueryRequest / ExtrapolationResponse (+ source_of_dose, dose_grade)
  main.py      POST /extrapolate · POST /extrapolate/stream
backend/tests/fixtures/  validation_* (test-only)
frontend/      Next.js free-text + reasoning sidebar
```

### Pipeline

```
query → intake → (guideline if solid & not organ-impaired)
              OR research-agent → extrapolate_dose → safety → concordance?
      → critic-agent (dose_grade) → submit_recommendation
      → else recovery.assemble_partial_payload
```

## Conventions

- **Models:** Sonnet orch + critic, Haiku research — `PAEDSCALE_*` in `.env.example`.
  Hard budget **~$2** (`PAEDSCALE_BUDGET_USD`). Never commit API keys.
- **Deploy:** needs Claude CLI runtime (`backend/Dockerfile` + Node `@anthropic-ai/claude-code`).
- **Subagents only:** `research-agent`, `critic-agent`; both `background=False`. Disallow
  ToolSearch / ScheduleWakeup / TaskOutput / SendMessage thrash tools.
- **Safety in output:** disclaimer, NTI→TDM, bounds, evidence grade, assumed defaults,
  `source_of_dose`, critic `dose_grade`.
- **Concordance tests** offline only; do not loop live orchestrator in CI.

## Working style

- Commit + `git push` after each phase. Repo: `github.com/heyiamnotacoder/paedscale`.
- Use `gh` for GitHub ops.
- Co-author trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (or session agent).

## Commands

```bash
cd backend && pytest
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev
```

## Changelog

Full file-level diff of the reliability rewrite: **`CLAUDE.md` → section “Changelog: agent
reliability rewrite”**. Public product overview: **`README.md`**.
