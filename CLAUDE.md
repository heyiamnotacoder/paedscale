# CLAUDE.md — PaedScale

Guidance for Claude Code sessions working in this repo.

## What this is

PaedScale is a **generalizable multi-agent pediatric dose-extrapolation agent** for the "Built with
Claude: Life Sciences" hackathon. A free-text clinical query drives an Opus/Sonnet orchestrator that
spawns specialist subagents (pathway / PK / safety) to research the literature (PubMed · Semantic
Scholar · web), decomposes the drug's **multiple** elimination pathways, scales adult PK by
**allometric scaling × organ maturation (Anderson–Holford)**, picks the right dosing method,
self-critiques, and self-checks against known guideline doses. It generalizes to any drug — there is
no prefill drug set.

The authoritative concept brief is `docs/paedscale-concept.html` — read it before making product
decisions. This file is the engineering guide.

## Golden rule: keep the LLM and the math separate

- **Deterministic Python (`backend/app/pk/`)** owns ALL numbers: allometry, maturation, Vd
  correction, dose solve. No LLM calls here. This is what tests pin.
- **Claude (`backend/app/agent/`)** owns judgment and language: mapping a drug to its elimination
  pathways (fm split), retrieving/annotating adult PK, and writing the cited rationale. It must NOT
  invent the final dose — it feeds structured inputs to `pk/` and explains the result.

If you find yourself asking Claude to "compute the dose," stop — that belongs in `pk/`.

## Architecture

```
backend/app/
  pk/          allometry · maturation · distribution · methods · organ_function ·
               safety · concordance · pipeline            (pure functions — ALL the math)
  agent/       orchestrator.py  (Agent SDK: subagents + run loop + budget guard)
               math_tools.py    (in-process MCP: pk/ exposed as tools — golden rule)
               research_tools.py(in-process MCP: PubMed + Semantic Scholar)
               stream.py        (SDK messages → SSE trace events)
               intake.py        (free-text → covariates)  · adult_pk.py/pathways.py (legacy helpers)
  data/        maturation.json  (drug-agnostic pathway curve library — the ONLY data file)
  schemas.py   pydantic QueryRequest / ExtrapolationResponse
  main.py      FastAPI: POST /extrapolate (JSON) · POST /extrapolate/stream (SSE) · CORS
backend/tests/fixtures/  validation_drugs.json · validation_guidelines.json  (test-only)
frontend/      Next.js (App Router, TS). Free-text box + live reasoning sidebar; teal/paper tokens.
```

## Conventions

- **Models (tiered for cost, env-configurable):** Sonnet orchestrator + critic, Haiku subagents —
  see `PAEDSCALE_*` in `.env.example`. A query must stay **≤ $0.50** (budget guard + turn caps).
  Read `ANTHROPIC_API_KEY` from env (`.env`, gitignored). Never hardcode or commit keys.
- **Deployment needs the Claude CLI runtime:** the Agent SDK spawns the `claude` Node binary, so the
  backend deploys via `backend/Dockerfile` (Python + Node + `@anthropic-ai/claude-code`), wired in
  `render.yaml`. A plain Python runtime will not work.
- **Pipeline** (backend `/extrapolate[/stream]`): free-text query → intake → parallel subagents
  (pathway / PK / safety) → method choice → `extrapolate_dose` → `check_safety_bounds` →
  `find_concordance` → critic → `submit_recommendation`. Mirrors concept §04, generalized.
- **Generalizable, not prefill:** there is no curated drug set. Agents research each drug live;
  `data/maturation.json` is the drug-agnostic pathway curve library. The three former demo drugs live
  only in `tests/fixtures/` as a validation set.
- **Safety must surface in output:** decision-support-only disclaimer, NTI→TDM warnings, safety-bounds
  clamp/flag, evidence grade, and assumed-default flags. Never emit a false-confident number.
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
