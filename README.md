![PaedScale](docs/banner.png)

# PaedScale

[![Live demo](https://img.shields.io/badge/live-paedscale.by--dhruvik.in-0E7A6B?logo=safari&logoColor=white)](https://paedscale.by-dhruvik.in)
![Claude Life Sciences Hackathon 2026](https://img.shields.io/badge/Claude%20Life%20Sciences-Hackathon%202026-0E7A6B)
![License: MIT](https://img.shields.io/badge/license-MIT-1a6ee0)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![Decision support](https://img.shields.io/badge/status-decision%20support-B9760A)

### A pediatric dose, extrapolated from adult pharmacokinetics — with a cited, graded, auditable rationale.

> 🔗 **Live at [paedscale.by-dhruvik.in](https://paedscale.by-dhruvik.in)** — built at the **2026 Claude: Life Sciences Hackathon**.

PaedScale derives a defensible **starting** dose for a child from published adult PK, using
**allometry × organ maturation** (Anderson–Holford), and returns a graded A→D recommendation with the
reasoning, the guideline concordance, and every uncertainty made explicit — not a black-box number.

> **Medication errors harm an estimated 1.5 million people a year in the United States alone**, and
> children are disproportionately exposed — because nearly every pediatric dose is a weight-based
> calculation done by hand, for a body whose organs are still maturing.
> <br><sub>Sources: Institute of Medicine, *Preventing Medication Errors* (2006); Kaushal et al., *JAMA* 2001;285:2114 (pediatric medication-error rate).</sub>

![PaedScale graded output — grade A, concordant with guideline](docs/screenshot.png)
<sub>A real graded run: clindamycin, 6 yr — the estimate, the grade, the guideline concordance (1.14×), and the flags, all in one auditable view.</sub>

---

## Why pediatric dosing is hard — and where guidelines run out

Drug clearance does **not** scale linearly with body size in early life: the organs that eliminate the
drug are still maturing, so scaling an adult dose by weight **over-doses the young.** Published pediatric
labels cover the common drug × age combinations — but they *run out* for neonates, off-label drugs,
organ impairment, and narrow-therapeutic-index agents, where clinicians today extrapolate by hand from
sparse references.

PaedScale encodes the distance between the naïve weight-linear line and the true maturation curve, and —
the whole point — maps each drug to its elimination pathway so a single deterministic engine extrapolates
**across the drug space** without a hardcoded per-drug lookup table.

## What makes it more than an LLM wrapper

- **Multi-agent by design** — an **Opus orchestrator** (`agents/agent.py`) drives a cheaper **Sonnet
  retrieval subagent** (`retrieval/`) that gathers cited adult PK **live from PubMed + openFDA**.
- **Python does the arithmetic; Claude does the judgment** — a deterministic engine does the math; the
  model maps drug → pathway → maturation curve and writes the justification. The mapping across the drug
  space is what a hardcoded calculator cannot do.
- **Cite-or-abstain, enforced in code** — the engine *raises* rather than invent a maturation curve for an
  unknown pathway, and *flags* unattributed clearance instead of hiding it. No unsourced PK value drives a
  confident point estimate — it grades **D** and abstains instead.
- **Organ function, from real inputs** — renal impairment derives its clearance modifier from a **bedside
  Schwartz eGFR** (serum creatinine + height), not a flat guess; hepatic adjustment is surfaced as a
  drug-specific note rather than a silent reduction.
- **MCP server** (`api/mcp_server.py`) exposes the same retrieval tools over FastMCP (stdio).

## See it reason — including when it *shouldn't* be confident

The differentiator isn't a confident number; it's a number that knows its own limits.

| Confident & concordant | Honest under uncertainty |
|---|---|
| ![Grade A](docs/screenshot.png) | ![Grade C](docs/screenshot-uncertain.png) |
| Clindamycin — clean CYP3A4 pathway, concordant with the guideline (1.14×) → **grade A**. | Neonatal vancomycin — a narrow-TI renal drug where allometry under-predicts; it flags the discordance, recommends TDM, anchors to the guideline, and caps the grade at **C**. |

## The science

Per elimination pathway:

```
CL_child = CL_adult × (WT/70)^0.75 × MF(PMA) × OF
MF(PMA)  = PMA^H / (TM50^H + PMA^H)      # maturation, normalised so adult ≈ 1
```

`WT` weight (kg) · `PMA` postmenstrual age (weeks) · `TM50` age at 50% maturation · `H` Hill coefficient ·
`OF` organ-function modifier (renal from Schwartz eGFR / hepatic). Vd scales linearly; the dose is solved
by the effect-driving metric (`css`/`auc` for maintenance, `cmax` for peaks, `time_mic` flagged as a proxy
for β-lactams). Oral doses are corrected by bioavailability `F`; toxic/effective bounds fire a prominent
safety warning.

<sub>Allometric ¾-power scaling and sigmoidal maturation: Anderson & Holford, *Annu. Rev. Pharmacol. Toxicol.* 2008;48:303. GFR maturation model: Rhodin et al., *Pediatr. Nephrol.* 2009;24:67. Bedside eGFR: Schwartz et al., *J. Am. Soc. Nephrol.* 2009;20:629.</sub>

## Grading & concordance

| Grade | Meaning |
|-------|---------|
| **A** | Passes concordance vs a real published guideline |
| **B** | Solid PK / guideline-anchored, honestly caveated |
| **C** | Sparse / uncertain — directional only |
| **D** | Insufficient data or a safety stop (dose withheld) |

Concordance = the recommended dose ÷ a guideline dose, reported as a ratio inside a **strict 0.67×–1.5×**
band (and a **wider clinical 0.5×–2×** band).

The deterministic engine is unit-tested and **reproducible with no API key**
(`python3 -m tests.test_pk`): maturation monotonicity, cite-or-abstain, safety hard-stops, oral-F,
time>MIC, LRU cache, and the mechanism scorer.

## Architecture

```
frontend/index.html          self-contained UI (form → /calculate/stream → graded result + chat)
backend/                     run all commands from here (backend/ is the package root)
  engine/                    deterministic backbone — no I/O, no LLM
    constants.py             MATURATION params (TM50/Hill) ONLY. NO per-drug PK.
    pk_engine.py             allometry × maturation, dose solve, oral-F, safety, Schwartz eGFR → OF
    edge_cases.py            deterministic flags: prodrug / obesity / protein-binding / illness
    pk_cache.py              bounded in-process LRU for live dossiers
    mechanism_score.py       mechanistic-reasoning scorer (6 dimensions)
    uncertainty.py           seeded 90% parameter-uncertainty interval from the published curve CIs
  retrieval/                 retrieval subagent + tools (import retrieval → __init__.py)
    __init__.py              RETRIEVAL SUBAGENT (Sonnet) → cited dossier, cache hit, or abstain
    retrieval_tools.py       httpx: PubMed E-utilities + openFDA + web_fetch
  agents/agent.py            Opus ORCHESTRATOR: load_skill → retrieve → compute → edge_cases → grade
  api/main.py                FastAPI: /, /calculate, /calculate/stream, /chat, /pk, /health
  api/mcp_server.py          MCP server for the same retrieval tools (FastMCP, stdio)
  tests/                     pytest suite; everything except test_agent.py runs in CI without a key
  benchmark/                 pre-registered benchmark against FDA labels (harness only)
  skills/                    lean markdown skills loaded on demand
  eval_data/                 ANSWER KEYS ONLY — harness, never the product path
```

**No hardcoded per-drug PK in the product path.** The agent retrieves adult PK live (PubMed + openFDA),
serves a TTL-bounded cache hit, or **abstains** (grade D). `eval_data/` is harness-only.

## Benchmark and uncertainty

**How wide is the answer?** Each dose comes with a 90% *parameter-uncertainty interval*. It comes from a
seeded Monte Carlo over the published 95% confidence intervals of the maturation curves (TM50 and Hill).
It shows how much the dose moves when the curve parameters move, and which pathway drives that. It is
not the range of doses that suit different children.

**Does maturation help?** `backend/benchmark/` scores PaedScale against FDA-approved pediatric label
doses for 21 IV drugs (46 age bands).
- **Comparators:** weight-linear, BSA, allometry, and allometry with a class rule. The last of these
  differs from PaedScale only by the maturation term.
- **Pre-registration:** the protocol (`benchmark/PROTOCOL.md`) was committed before any scoring, and
  every change since then is a dated amendment.
- **Traceability:** every reference dose carries a verbatim label quote that a test checks.
- **Reproducing it:** `python3 -m benchmark.run` regenerates every number and figure.
- **Results (first scoring, 10,000 bootstrap replicates):** against allometry + class rule, PaedScale's
  typical fold error was 0.77× in newborns and 0.78× under 2 years, both with 95% CIs below 1. Across all
  ages it was 0.91× and the CI reached 1.0004, so that hypothesis was not supported. Weight-linear scaling
  matched newborn labels at least as well. Full numbers: `backend/benchmark/output/results.json`.
- **Manuscript:** `paper/manuscript.md`. Every number is filled in from the committed outputs. Build it
  from the repo root with `python3 -m paper.build --pdf` (needs pandoc and Node Playwright).

## Run

**Hosted:** the live app is at **[paedscale.by-dhruvik.in](https://paedscale.by-dhruvik.in)**. To run locally:

```bash
cd backend                         # backend/ is the package root — run everything from here
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m tests.test_pk           # deterministic core + scorers — NO key needed
pip install -r requirements-dev.txt -r benchmark/requirements.txt
python3 -m pytest -q tests --ignore=tests/test_agent.py   # the CI suite (no key)
python3 -m benchmark.run           # regenerate the benchmark (benchmark/output/)
cp .env.example .env               # ANTHROPIC_API_KEY (+ optional OPENFDA_API_KEY / NCBI_API_KEY)
uvicorn api.main:app --reload --port 8000
# open http://localhost:8000
python3 -m tests.test_agent        # end-to-end eval (needs key + network)
python3 -m api.mcp_server          # optional: the retrieval MCP server (stdio)
```

`/pk` and `tests/test_pk` run **without a key**. `/calculate`, the orchestrator and the retrieval subagent
need the key **and network** (live PubMed/openFDA); expect ~60–95 s/query for the full live path.

## Where it's headed

From one maturation curve per pathway to a **physiologically-based PK (PBPK) "digital twin"** of the
child — validated against real clinical concentrations, then personalised to the patient's genotype and
measured organ function. This is the path from careful extrapolation to **individualised pediatric dosing.**

## Disclaimer

PaedScale is a research prototype. Its output is a defensible **starting estimate** for a qualified
clinician — not an autonomous order, and not a validated clinical-decision-support device.
Narrow-therapeutic-index drugs require therapeutic drug monitoring.

## License

[MIT](LICENSE).
