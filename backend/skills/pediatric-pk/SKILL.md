---
name: pediatric-pk
description: >
  Methodology for extrapolating a pediatric starting dose from adult pharmacokinetics using
  allometric scaling × organ maturation (Anderson–Holford), with per-pathway ontogeny and organ-
  function correction. Load when reasoning about which elimination pathways apply to a drug, the
  fm split, the maturation curve to use, or how to grade the resulting dose.
---

# Pediatric dose extrapolation — methodology

You are deriving a **defensible pediatric STARTING dose** from adult PK. All arithmetic is done by
PaedScale's deterministic `extrapolate_dose` / `check_safety_bounds` / `find_concordance` tools — your
job is the **drug → model mapping and the justification**, not the calculation.

## 1. Decompose clearance into elimination pathways (the fm split)
Attribute the adult clearance across specific routes, as fractions `fm` that sum to ~1. Use only these
library pathway names (each has a curated maturation curve): `CYP3A4, CYP1A2, CYP2C9, CYP2C19,
CYP2D6, CYP2E1, UGT1A1, UGT2B7, sulfation, renal_GFR, hepatic_other`.

Guidance:
- Read the label/PK: "metabolized by CYP3A4", "excreted unchanged in urine" (→ `renal_GFR`),
  "glucuronidation" (→ `UGT1A1`/`UGT2B7`), "sulfation".
- If a route is known but the enzyme is not, use `hepatic_other`.
- fm's are normalised by the tool — approximate splits are fine; flag low confidence.

## 2. Allometry sets the scale, ontogeny bends it
- Clearance scales with weight to the power **0.75**; volume of distribution ≈ linear (power **1.0**).
- Each pathway has its own sigmoidal maturation `MF(PMA) = PMA^H / (TM50^H + PMA^H)` on
  **postmenstrual age** (gestational + postnatal). CYP3A4, UGT1A1 and renal GFR mature at different
  rates — so the correct maturation factor depends on the fm split. Do not invent TM50/Hill; the
  library curve is applied per pathway automatically.
- Volume is corrected for the neonate's higher body-water fraction and lower protein binding.

## 3. Choose the method from the PK/PD driver
Pick the dosing method that matches what drives the drug's effect:
- `auc` — total-exposure drugs (match adult AUC).
- `css` — steady-state concentration targets (e.g. infusions).
- `cmax` — peak-driven efficacy (e.g. aminoglycoside peak).
- `trough` — trough-driven (e.g. vancomycin AUC/trough).
- `loading` — a one-off loading dose to a target concentration.
- `mgkg_linear` — only when no mechanistic PK is available (naive linear fallback; grade low).

## 4. Organ impairment veto
Renal or hepatic impairment (stated, low eGFR, high SCr for age, Child-Pugh ≥7, liver disease, AKI)
**forces the full mechanistic path** — never the guideline short path. Pass eGFR / Child-Pugh so the
organ-function modifier is applied to the right pathways.

## 5. Grade honestly and self-critique
- Evidence grade reflects data quality: solid adult PK + clear fm split → moderate; sparse/assumed
  → low/very-low. Every assumed covariate lowers the grade.
- Narrow-therapeutic-index drugs (vancomycin, aminoglycosides, digoxin, phenytoin, morphine in
  neonates) → recommend **TDM**; never present a stand-alone number as definitive.
- Before submitting, argue against your own dose: is the path right, the method matched to the driver,
  the fm split complete, the dose inside the safe/effective window, the assumptions acknowledged?
