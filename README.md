# PaedScale

**Dosing children where the guidelines run out.**

PaedScale is a pediatric dose-extrapolation agent. Given a drug and a child's covariates
(gestational + postnatal age, weight, renal/hepatic flags), it derives a defensible pediatric
starting dose from adult pharmacokinetics using **allometric scaling × organ maturation
(Anderson–Holford)** — with a cited, auditable rationale, and a **concordance check** against
published guideline doses where they exist.

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

## How it works

```
Case input ─▶ adult PK ─▶ pathway split (fm) ─▶ allometry × maturation ─▶ dose solve ─▶ rationale + concordance
             (Claude)      (Claude)              (Python, deterministic)   (Python)      (Claude)
```

- **Claude (`claude-sonnet-5`)** does the hard mapping — drug → elimination pathways, adult PK
  retrieval, and the written, cited justification.
- **Deterministic Python** does the pharmacometric math (allometry, per-pathway Hill maturation,
  volume-of-distribution correction, dose solve) so the numbers are reproducible and testable.

### Maturation model (per elimination pathway)

```
CL_child = CL_adult × (WT/70)^0.75 × MF(PMA) × OF
MF(PMA)  = PMA^H / (TM50^H + PMA^H)
```
`WT` weight · `PMA` postmenstrual age · `TM50` age at 50% maturation · `H` Hill coefficient ·
`OF` organ-function modifier.

## Scope (7-day build)

Three drugs, one per elimination archetype, each concordance-checked against known guideline doses:

| Drug        | Archetype            | Pathway  |
|-------------|----------------------|----------|
| Midazolam   | Hepatic CYP          | CYP3A4   |
| Vancomycin  | Renal                | GFR      |
| Morphine    | Hepatic glucuronidation | UGT2B7 |

## Repo layout

```
backend/   FastAPI — Claude agent layer + deterministic PK compute (Python)
frontend/  Next.js (TypeScript) UI
docs/      Original concept brief (paedscale-concept.html)
```

## Run locally

Requires Python 3.11+ and Node 18+.

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # add your ANTHROPIC_API_KEY; keep ALLOWED_ORIGINS for local frontend
pytest                        # concordance tests
uvicorn app.main:app --reload # http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL, defaults to localhost:8000
npm run dev                        # http://localhost:3000
```

With both running, open `http://localhost:3000`, pick a drug, and submit a case.

## 90-second demo script

1. **The problem (10s).** Point at the maturation-vs-linear gap: a neonate's clearance sits far
   below the naive `weight/70` line. That gap is what gets an adult dose scaled straight into an
   overdose in the young.
2. **Submit a case (20s).** Pick **Vancomycin** (renal, narrow-therapeutic-index) for a **term
   neonate** (3.5 kg, 40 wk gestational + 2 wk postnatal age). Hit *Extrapolate dose*.
3. **Read the result card (20s).** Recommended dose in mg and mg/kg, the elimination pathway and fm
   split, the maturation fraction actually applied at this age, and the concordance badge comparing
   it to the published neonatal guideline dose.
4. **Show the maturation curve (15s).** The chart is the real Hill curve for this drug's pathway —
   not illustrative — with the case's own point marked on it.
5. **Show the rationale (15s).** Scroll to the full auditable derivation: assumptions, uncertainty
   flags, and (for vancomycin/morphine) the narrow-therapeutic-index → TDM warning.
6. **Toggle renal impairment (10s)** and resubmit to show the dose drop — the organ-function
   modifier only touches the matched pathway (try it on midazolam too: no change, since it's
   hepatically cleared).

## Deploy

- **Backend (FastAPI):** Render can use the root `render.yaml`. Set `ANTHROPIC_API_KEY` and
  `ALLOWED_ORIGINS` in the Render service environment. `ALLOWED_ORIGINS` should be your deployed
  Vercel origin, for example `https://paedscale.vercel.app` (comma-separated if you need multiple
  origins).
- **Frontend (Next.js):** Vercel can deploy from the `frontend/` directory. Set
  `NEXT_PUBLIC_API_BASE_URL` to the deployed Render backend URL, for example
  `https://paedscale-backend.onrender.com`.

After changing environment variables on either platform, redeploy that service so the new values are
picked up.

## License

Prototype for a hackathon. Not for clinical use.
