# PaedScale — Roadmap

Repo-facing build roadmap. The concept brief lives at `docs/paedscale-concept.html`; engineering
conventions are in `CLAUDE.md`.

## Goal

Turn the PaedScale concept into a working, demoable app: a Next.js UI over a Python FastAPI backend
that pairs Claude reasoning with a deterministic pharmacometric compute layer, shipped to a public
GitHub repo with a commit + push after every phase.

## Stack

- **Frontend:** Next.js (App Router, TypeScript), design tokens ported from the concept.
- **Backend:** Python FastAPI. Deterministic PK math + Claude (`claude-sonnet-5`) agent layer.
- **Model access:** Anthropic Python SDK, `ANTHROPIC_API_KEY` via `.env` (gitignored).

## Scope

Three drugs, one per elimination archetype, each concordance-checked against known guideline doses:

- **Midazolam** — CYP3A4 (hepatic CYP)
- **Vancomycin** — renal GFR
- **Morphine** — UGT2B7 (glucuronidation)

## Pipeline (`POST /extrapolate`)

1. Case input (drug, indication, gestational + postnatal age, weight, renal/hepatic flags).
2. Adult PK retrieval — curated `data/drugs.json` first; Claude fills/annotates.
3. Pathway decomposition (fm split across CYP3A4 / renal / UGT) — **Claude**.
4. Allometry × per-pathway maturation + Vd correction — **deterministic Python**.
5. Dose + interval solve to match adult exposure — **deterministic Python**.
6. Cited rationale, uncertainty/data-gap flags, NTI warnings, concordance check — **Claude**.

## Phases (push to GitHub after each)

- [x] **Phase 0 — Repo, scaffolding, docs.** git init, `.gitignore`, public repo, `docs/`,
      `README.md`, `CLAUDE.md`, `plan.md`.
- [x] **Phase 1 — Pharmacometric core + concordance tests.** `pk/*` + `data/*.json` + pytest
      reproducing known guideline doses for all three drugs.
- [ ] **Phase 2 — Claude agent layer.** `agent/client.py`, `pathways.py`, `adult_pk.py`,
      `rationale.py` with structured JSON outputs.
- [ ] **Phase 3 — FastAPI backend.** `schemas.py` + `main.py` wiring the pipeline behind
      `POST /extrapolate` with CORS.
- [ ] **Phase 4 — Next.js frontend.** Case input form + results (dose, rationale trace, maturation
      chart, concordance badge, disclaimer).
- [ ] **Phase 5 — Integration, demo polish, deploy docs.** End-to-end wiring, error/uncertainty
      states, README run + 90s demo script, deploy notes.

## Verification

- `cd backend && pytest` → concordance tests green.
- `uvicorn app.main:app --reload` + `curl POST /extrapolate` → dose + rationale + concordance for all
  three drugs.
- `cd frontend && npm run dev` → submit neonatal cases end-to-end.

## Non-goals / safety

Decision support, not prescribing. NTI drugs flagged for TDM. Uncertainty always surfaced. Not a
regulatory/validated device.
