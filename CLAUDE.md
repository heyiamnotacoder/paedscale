# CLAUDE.md — PaedScale

Guidance for Claude Code sessions working in this repo.

## What this is

PaedScale is a **pediatric dose-extrapolation agent** for the "Built with Claude: Life Sciences"
hackathon. It extrapolates a pediatric starting dose from adult pharmacokinetics using **allometric
scaling × organ maturation (Anderson–Holford)**, and self-checks against known guideline doses.

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
  pk/          allometry.py · maturation.py · distribution.py · dose_solve.py   (pure functions)
  agent/       client.py · pathways.py · adult_pk.py · rationale.py             (Claude calls)
  data/        drugs.json · maturation.json · guidelines.json                    (curated reference)
  schemas.py   pydantic request/response
  main.py      FastAPI, POST /extrapolate, CORS
frontend/      Next.js (App Router, TS). UI ports the concept's teal/paper design tokens.
```

## Conventions

- **Model:** `claude-sonnet-5`. Read `ANTHROPIC_API_KEY` from env (`.env`, gitignored). Never
  hardcode or commit keys. `.env.example` documents required vars.
- **Pipeline** (backend `/extrapolate`): case input → adult PK → pathway split → allometry ×
  maturation → dose solve → rationale + concordance. Mirrors concept §04.
- **Data-first:** the three in-scope drugs (midazolam/CYP3A4, vancomycin/renal GFR,
  morphine/UGT2B7) have curated entries in `data/`. Claude fills gaps and annotates; curated values
  win for the demo path.
- **Safety must surface in output:** decision-support-only disclaimer, NTI→TDM warnings, explicit
  uncertainty and data-gap flags. Never emit a false-confident number.
- **Concordance = the test suite:** `backend/tests/test_concordance.py` asserts the PK math
  reproduces known guideline doses within tolerance. Keep it green.

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
