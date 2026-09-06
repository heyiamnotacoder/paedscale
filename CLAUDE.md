# PaedScale — CLAUDE.md

Pediatric dose-extrapolation agent. Derives a defensible **starting** dose for a child
from adult pharmacokinetics using allometry × organ maturation (Anderson–Holford), with a
cited, auditable rationale. **Decision support, not prescribing.**


## RULES:
1. If you want to check a generated or local site, use the `playwright-web-check` skill (global Playwright).
4. Do not re-add `validation_set/` or `result*.md`. They are completed harness artifacts
   (gitignored). Backend product code must never import, open, or mention `validation_set`.
5. Before making changes to any branches ask user which branch would be suited for changes.

## Core thesis
Drug clearance does not scale linearly with body size in early life — the organs that
eliminate the drug are still maturing. Scaling an adult dose by weight over-doses the young.
PaedScale encodes the gap between the naive linear line and the true maturation curve.

## Architecture
```
frontend/index.html         self-contained UI (form → /calculate/stream → graded result + chat)
backend/                    (run all commands from here; backend/ is the package root)
  engine/                   deterministic backbone (no I/O, no LLM)
    constants.py            MATURATION params (TM50/Hill) ONLY — engine backbone. NO per-drug PK.
    pk_engine.py            DETERMINISTIC math: allometry × maturation, dose solve, oral-F, safety,
                            renal eGFR (bedside Schwartz) → organ-function modifier
    edge_cases.py           deterministic flags: prodrug / obesity / protein-binding / illness
    pk_cache.py             bounded in-process LRU for live dossiers (Render single-dyno shared pool)
    mechanism_score.py      mechanistic-reasoning scorer (6 PRD dimensions)
  retrieval/                retrieval subagent + tools (package; `import retrieval` → __init__.py)
    __init__.py             RETRIEVAL SUBAGENT → live | cache | abstain
    retrieval_tools.py      httpx: PubMed E-utilities + openFDA + web_fetch
  agents/
    agent.py                Opus ORCHESTRATOR: load_skill → retrieve → compute → edge_cases → grade
  api/
    main.py                 FastAPI: /, /calculate, /calculate/stream, /chat, /pk, /health
    mcp_server.py           MCP server for the same retrieval tools (FastMCP, stdio)
  tests/                    test_pk.py / test_agent.py
  skills/                   lean markdown skills (mechanism, pubmed, openfda, webfetch, edge_cases)
  eval_data/                ANSWER KEYS ONLY — harness never product path
```

**On master:** no hardcoded per-drug PK in the product path — live retrieve or abstain.

Split of labour: **Python does the arithmetic; Claude does the judgment** (drug → pathway
→ maturation-curve mapping and the written justification). This is the whole point — the
mapping across the drug space is what a hardcoded calculator cannot do.

## The math (pk_engine.py)
Per elimination pathway:
```
CL_child = CL_adult × (WT/70)^0.75 × MF(PMA) × OF
MF(PMA)  = PMA^H / (TM50^H + PMA^H)      # normalised so adult ≈ 1
```
- `WT` weight (kg), `PMA` postmenstrual age (weeks), `TM50` age at 50% maturation,
  `H` Hill coefficient, `OF` organ-function modifier (renal/hepatic impairment).
- Vd scales linearly (WT^1.0). Half-life = ln2 · Vd/CL.
- Dose solve by effect-driving metric:
  - `css`/`auc` (maintenance): `dose_rate_child = adult_dose_rate × CL_child/CL_adult`
  - `cmax` (peak): `dose_child = adult_dose × Vd_child/Vd_adult`
  - `time_mic` (β-lactams): solved like `css` but **flagged as a proxy** — efficacy is fT>MIC,
    so the interval/infusion governs; grade ceiling B, half-life-anchored interval forced.
- **Oral bioavailability**: `route="oral"` divides the systemic-matched dose by `F` (pediatric
  F assumed = adult → data-gap flag). **Safety bounds**: toxic/effective thresholds, when
  supplied, fire a prominent warning.
- The engine **refuses to invent a maturation curve** for an unknown pathway (raises) and
  **flags** unattributed clearance rather than hiding it. This is cite-or-abstain in code.

Known pathway keys: `renal_gfr` (Rhodin 2009), `cyp3a4` (Anderson/Larsson 2011 midazolam),
`ugt2b7` (Anand 2008 morphine). Extend MATURATION only with **published** TM50/Hill — never invent.

**Skills:** lean files in `backend/skills/` loaded via `load_skill` — keep agent SYSTEM short.
**Edge cases:** `assess_edge_cases` flags prodrug/obesity/high-PB/illness when evidence exists.
**PK cache:** `pk_cache.py` — max entries/bytes/TTL (env); single dyno shared; no multi-dyno Redis yet.

## The agents (multi-agent)
**Orchestrator** (`agent.py`, Opus) tools: `retrieve_drug_data` (→ retrieval subagent),
`compute_pediatric_dose` (engine), `web_search` (guideline only), `submit_recommendation`
(structured, includes the scored `mechanism` object). Steps: 1. record mechanism (elimination,
pathways, enzymes, transporters, active metabolites, protein binding) → 2. retrieve PK LIVE or
abstain → 3. call the engine → 4. web_search the guideline + concordance (0.67×–1.5×) →
5. grade (A/B/C/D) → 6. flags (NTI/TDM, active metabolite, time>MIC, oral-F, data gaps,
"assumed term", PD-target assumption).

**Retrieval subagent** (`retrieval.py`, Sonnet): tight-budget loop over `pubmed_search` /
`pubmed_fetch` (NCBI E-utilities) + `openfda_label` → cited PK+mechanism dossier. openFDA label
is pre-fetched; `submit_dossier` is forced on the final turn. On failure it returns a **null
dossier** (`source_mode="unavailable"`) — never a fabricated fallback. Same tools are exposed
over MCP by `mcp_server.py`.

Grades: **A** passes concordance vs a real guideline · **B** solid PK, no guideline ·
**C** sparse/uncertain, directional only · **D** insufficient data / safety stop.

## Rules that must not regress
- **Live retrieval or abstain.** Product path never reads `eval_data/`; unretrievable PK → grade D.
- **Cite-or-abstain.** No unsourced PK value drives a confident point estimate (null it instead).
- **Concordance band is 1.5× / 0.67×** . Report the ratio.
- **Mechanism is scored.** 6 dimensions vs `eval_data/mechanism_truth.json`; empty lists are
  correct-negatives — the model must not invent transporters/metabolites.
- **PMA for under-2s.** If unknown, assume term AND surface that assumption.
- **Safety bounds.** Never present a dose above toxic / below effective without a prominent flag.
- **NTI drugs (vancomycin, aminoglycosides) recommend TDM**; **active metabolites (M6G) flagged.**
- **Known engine limits** (engine kept as-is):
  - allometry×Cmax **underdoses concentration-dependent aminoglycosides** — agent must
    guideline-anchor + flag exposure-target mismatch + TDM (verified gentamicin/amikacin).
  - **time_mic** daily-dose match is a **proxy** for fT>MIC — grade ceiling B; interval/infusion matters.
  - **Michaelis–Menten** drugs (phenytoin): no linear CL invent; guideline-only or abstain.
  - **Titration** drugs without adult mg/day (midazolam/fentanyl): no false absolute dose.
  - Pediatric CL may exceed adult allometry for some drugs (e.g. fluconazole) — flag discordance.
  - Obesity: flag only; do not silently rewrite weight in the engine.
- **Validation harness** (`validation_set/`, `result*.md`, `results.csv`) is completed and
  removed from the product tree — do not re-add; product path never imports them.

## Run
```bash
cd backend                         # backend/ is the package root — run everything from here
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m tests.test_pk           # deterministic core + scorers — NO key needed
cp .env.example .env               # ANTHROPIC_API_KEY (+ optional OPENFDA_API_KEY / NCBI_API_KEY)
uvicorn api.main:app --reload --port 8000
# open http://localhost:8000
python3 -m tests.test_agent        # end-to-end eval (needs key + network); --full for all drugs
python3 -m api.mcp_server          # optional: run the retrieval MCP server (stdio)
```
`/pk` and `test_pk.py` run without a key (they read the `eval_data/` oracle). `/calculate`,
`agent.py`, `retrieval.py` need the key **and network** (live PubMed/openFDA).
**Budget note:** live retrieval on every query is real — expect ~60–95 s/query (retrieval
subagent + orchestrator + guideline search). The <60 s target is the tuning goal, not yet met.

## Budget / scope
Target < $1 and < 60 s per query. Default model `claude-opus-4-8` (override via
`ORCHESTRATOR_MODEL`; `claude-sonnet-5` is the cheaper option). 

## Agent skills

### Issue tracker

Issues live in heyiamnotacoder/dosagecalc GitHub Issues (gh CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default roles: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: CONTEXT.md + docs/adr/ at the repo root. See `docs/agents/domain.md`.

## Branch note: `muse-spark-pbpk` (trial — do not merge to master as-is)
Vancomycin-IV PBPK-translation tab ("PBPK trial" nav). Whole-branch trial:
axe = revert `agent.py`, `api/main.py`, `child_pugh.py`, `index.html`; delete
`engine/pbpk_vancomycin.py` + `docs/pbpk-trial-decisions.md`. Full decision log
in `docs/pbpk-trial-decisions.md` (grill-me session Q1–Q16). Code review: the
following are deliberate trial decisions, not regressions —
- **Bundled cited params, not live retrieval.** A PBPK model lives in papers and
  cannot be re-fetched per query; narrow branch exception (one drug, composite
  OSP table + Emoto 2018 + Cao 2024, stated envelope, abstain outside it).
- **No A–D grade, no concordance band.** Grade deferred post-trial; confidence is
  provenance + the in-tab checkpoint table (`pbpk_checkpoints`). Do not flag the
  missing grade/mechanism-score as a bug.
- **Stricter than base rules on purpose:** refuses assumed-term for <2 y
  (abstains), requires SCr+height (abstains), abstains PMA<36 wk / eGFR<15 /
  CP-B/C. Flags (not models) ICU/sepsis and CP-A.
- **Trial heuristics, labelled:** CL = 0.67×GFR + 1.05×(WT/70)^0.75,
  Vss 0.37 L/kg, half-life-snapped interval. Checkpoint-gated, grade deferred.
- **Honesty markings are load-bearing:** `[INFERENCE]` 2-fold gates and the
  ABSTAINED Cao-quant checkpoint must survive any edit; paywalled numbers are
  never reconstructed.
