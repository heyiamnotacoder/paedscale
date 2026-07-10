# AGENTS.md — PaedScale

Guidance for Codex / coding-agent sessions working in this repo.

This file mirrors the engineering guide in **`CLAUDE.md`**. Prefer **`CLAUDE.md`** for full
changelogs (agent reliability rewrite `cd74841`, Perplexity-style frontend UX, and later diffs).
Keep both docs aligned when you change pipeline or frontend shell behaviour.

## What this is

PaedScale is a **generalizable pediatric dose-extrapolation agent** for the "Built with Claude: Life
Sciences" hackathon. A free-text query is parsed in Python, then an **in-process Sonnet Messages-API
agent loop** (`anthropic.AsyncAnthropic` — no Node, no Agent SDK) either returns a **published
guideline dose** or runs the mechanistic path, scaling adult PK by **allometry × organ maturation
(Anderson–Holford)** through deterministic PK-maths tools. Adult drug data comes from a deterministic
**openFDA** fetch (happy path); the **agentic Web/PubMed loop is gated to edge cases** (MCP). The
orchestrator **self-critiques** in its submit payload (no critic subagent). No prefill drug set.

Authoritative concept brief: `docs/paedscale-concept.html`. Full detail + changelog: `CLAUDE.md`
("Changelog: in-process Messages-API rewrite, 2026-07-11"). Older sections describe the superseded
Agent-SDK design.

## Golden rule: keep the LLM and the math separate

- **Deterministic Python (`backend/app/pk/`)** owns ALL numbers. No LLM calls here.
- **Agent layer (`backend/app/agent/`)** owns judgment and language. It must NOT invent the
  mechanistic dose — it feeds structured inputs to `pk/` (via the PK-maths tools) and explains it.
- **Guideline short path:** published mg/kg allowed only when solid **and** not renally/hepatically
  impaired; the orchestrator self-critiques on both paths.

## Architecture

```
backend/app/
  pk/          allometry · maturation · distribution · methods · organ_function ·
               safety · concordance · pipeline            (pure functions — ALL the math)
  agent/       orchestrator.py  (AsyncAnthropic Messages-API loop, guideline-agent, self-critique)
               math_tools.py    (PK-maths tool dicts + async dispatch)
               research_tools.py(fetch_drug_pk = openFDA + seed cache; pubmed_search = edge)
               intake.py        (deterministic parse → covariates + organ_impaired + edge_case)
               recovery.py      (partial payload from captured math results)
               {client,adult_pk,pathways,rationale}.py  (legacy helpers, unused by the loop)
  data/        maturation.json  (only production data file)
  report.py    POST /report → PDF via the `pdf` Agent Skill (off hot path)
  schemas.py   QueryRequest / ExtrapolationResponse (+ source_of_dose, dose_grade)
  main.py      POST /extrapolate · POST /extrapolate/stream · POST /report
  skills/pediatric-pk/SKILL.md   custom methodology skill (the "moat")
backend/tests/fixtures/  validation_* (test-only + drug seed cache)
frontend/      Next.js dark shell: landing composer, collapsible reasoning, inline cites
```

### Pipeline

```
query → intake.parse → drug + covariates + organ_impaired + edge_case
  fetch_drug_pk (openFDA) ∥ guideline-agent        (asyncio.gather)
  → orchestrator loop (Sonnet, adaptive thinking, prompt-cached):
       PK Maths tools (deterministic) + research tools (edge-gated: pubmed / MCP)
       → submit_recommendation (with self-critique)
  → else recovery.assemble_partial_payload
```

## Conventions

- **Model:** Sonnet 5 for everything (`PAEDSCALE_ORCH_MODEL`); no Haiku, no critic subagent. Config in
  `.env.example` (`PAEDSCALE_MAX_TURNS`, `PAEDSCALE_GUIDELINE_AGENT`, `PAEDSCALE_MCP_SERVERS`,
  `OPENFDA_API_KEY`). Never commit API keys.
- **Deploy:** plain Python (`render.yaml` `runtime: python`; `backend/Dockerfile` = `python:3.12-slim`).
  No Node, no `claude-agent-sdk`.
- **Agents:** orchestrator + parallel `guideline-agent` + edge-only research; MCP connector
  (`mcp-client-2025-11-20`) gated on `PAEDSCALE_MCP_SERVERS`.
- **Safety in output:** disclaimer, NTI→TDM, bounds, evidence grade, assumed defaults,
  `source_of_dose`, self-critique `dose_grade`.
- **Tests** offline only (`pytest` → 49 passed); never loop the live orchestrator in CI.

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

- **In-process Messages-API rewrite (2026-07-11):** **`CLAUDE.md` → “Changelog: in-process
  Messages-API rewrite”** — dropped the Agent SDK / Node; openFDA happy path; MCP + Skills.
- Perplexity-style frontend: **`CLAUDE.md` → “Changelog: Perplexity-style frontend UX”**
- Agent reliability rewrite: **`CLAUDE.md` → “Changelog: agent reliability rewrite”**

Public product overview: **`README.md`**.
