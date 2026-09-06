# PBPK Trial Tab — Decision Log (branch `muse-spark-pbpk`)

Trial-only. Axe path: revert `backend/agents/agent.py`, `backend/api/main.py`,
`backend/engine/child_pugh.py`, `frontend/index.html`; delete
`backend/engine/pbpk_vancomycin.py` and this file. Nothing else is touched.

## Locked scope decisions (grilling rounds 1–4)

1. **Deliverable = starting regimen + first-TDM timing, decision support only**
   (Q1/Q6). Dose-per-dose + interval + infusion duration + first-TDM timing +
   stated AUC target. No time-course simulator, no full PBPK solver.
2. **First drug = vancomycin IV** (Q2). NTI, TDM standard adult+peds
   (AUC-guided per Rybak 2020), IV avoids oral-F modelling, fits the existing
   NTI→TDM rule. A literature scout ranked gentamicin the easier bundle
   (re-implementable Zazo 2022 minimal ODEs) — vancomycin kept deliberately;
   its value-add over `pk_engine` is narrow: AUC-target integration +
   half-life-anchored interval + first-TDM timing + the Cao two-phase story
   (PBPK initial → Bayesian follow-up).
3. **Branch exception to no-hardcoded-PK** (Q3). A PBPK tab cannot live-fetch
   equations per query — the model lives in papers. Exception is narrow: one
   drug, cited composite source, stated envelope, abstain outside it.
4. **Parallel module, allometry untouched** (Q4). `engine/pbpk_vancomycin.py` is
   deterministic (no I/O, no LLM), keyless, routed by `calculator_mode="pbpk"`
   mirroring the `adult_hi` facade. Same recommendation envelope so
   `renderResult`/chat/streaming work unchanged.
5. **Validation = paper-profile match, checkpoints pre-pinned** (Q5/Q14).
   The trial is falsifiable: named paper checkpoints + tolerances (table below).
   Eyeball-similar curves do not count.
6. **Inputs: WT + PMA + SCr required; rest = surfaced paper medians** (Q7/Q11).
   No assumed-term fill-in for <2 y (abstain), no defaulted-normal kidney
   (abstain without SCr+height). Every defaulted physiology value renders as an
   assumption in the UI.
7. **Abstain outside the envelope** (Q8/Q16). PMA<36 wk, eGFR<15, Child-Pugh B/C,
   ICU/sepsis flagged starting-point-only. Testing-only does not excuse a
   confident wrong NTI dose.
8. **No A–D grade in the trial** (Q9/Q12). Confidence = provenance +
   in-tab checkpoint table, never a letter. Grade deferred to post-trial.
9. **Composite source of truth** (Q10). OSP vancomycin table (params: fu 0.67,
   GFR fraction 1) + Emoto 2018 (developmental renal) + Cao 2024 (neonatal
   envelope PMA 25–45 wk, PMA<36 unsolved). No single paper covers all three.
10. **Target + timing** (Q15). AUC24 400–600 per Rybak 2020 (via accessible
    Brunetti 2022 paraphrase — OUP full text 403s); trough/equation path needs
    steady state (before dose #4), Bayesian AUC may start at interval 1 (R2).
    Neonatal AUC use is labelled adult-target extrapolation (R1).

## Pinned checkpoints (Q14A; rendered in-tab)

| ID | Gate | Status |
|----|------|--------|
| O1 | OSP Table 3-1 GMFE 1.11, trial gate ≤2.0 | conventional band [INFERENCE] |
| E1/E2/E3 | Emoto adult + renal-bin pred/obs within 0.5–2.0× | [INFERENCE]; E3 sets renal floor CCr≥15 |
| E4 | Emoto peds 1.0/2.8 y Cmax+AUC within twofold | **only paper-explicit peds gate** |
| E5 | Schaad peds 2.6 d–7.6 y within 0.5–2.0× | [INFERENCE]; postnatal age, not PMA<36 cover |
| C1-quant | Cao neonatal quant bands | **ABSTAINED — full text paywalled, never reconstructed** |
| C2 | PMA<36 wk out of envelope | paper-explicit; facade abstains |
| R1/R2 | AUC target + Bayesian-first-interval timing | via Brunetti paraphrase |

## Build corrections the checkpoint recon forced

- **Vss 0.7 → 0.37 L/kg** (Emoto Table 1 predicted; observed 0.30–0.43).
- **CL ≈ 0.7×GFR → fu(0.67)×GFR + 1.05×(WT/70)^0.75** (OSP + Emoto Table 1;
  0.7-factor under-read adult CL ~25%). Nonrenal ontogeny unmodelled — stated.
- **Added eGFR<15 and CP-B/C abstains** (E3 floor; hepatic cover is CP-A only).
- **Infusion ≥60 min re-cited to Emoto-cited 1-h regimens** (Rybak rate-cap text
  paywalled — marked unverified, not cited as verified).
- Reference output: 6 y/20 kg/SCr 0.5 → 270 mg q6h, AUC 497, t½ 2.36 h.

## Verification done

`tests.test_pk` passes; page script `node --check` clean; keyless
`/calculate/stream` smoke (regimen + all abstains); headless Chromium
playtest of tab → result with zero page errors (screenshot reviewed).

## Open follow-up (decides live vs axe)

Score E4/E1–E5 pred/obs ratios against the studies' observed numbers (some in
inaccessible supplements) — that analysis is the trial verdict.
