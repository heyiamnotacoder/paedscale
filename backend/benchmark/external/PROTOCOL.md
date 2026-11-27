# External validation against published pediatric clearance — analysis protocol

Written and committed **before** any study was screened, any clearance value was extracted and
any prediction was computed. Every later change is logged under "Amendments" with its date, its
reason and whether it came before or after scoring. This protocol is separate from the label
benchmark (`../PROTOCOL.md`), which was scored on 2026-11-27 and is not changed by it.

## Question

The label benchmark compares predicted doses with labeled doses. Labels are a clinical
reference, not measured exposure. This validation asks the exposure question directly: given an
adult clearance and a child's age and weight, how close is each scaling method to the total
clearance **measured** in published pediatric pharmacokinetic studies?

Clearance is the quantity the maturation term acts on. Comparing clearance avoids the dose
solve, the target metric and the label's dosing conventions.

## Drugs

The 20 drugs of the label benchmark's reference set (`../reference_set.json`, `included: true`)
other than **morphine**, which is the source drug of the UGT2B7 maturation curve (Anand et al.
2008). Midazolam, the CYP3A4 curve-source drug, is already excluded from that set. For
piperacillin–tazobactam the analyte is piperacillin. For penicillin G it is benzylpenicillin.

The engine inputs are frozen as recorded in `../reference_set.json` before this protocol: the
fraction excreted unchanged in urine (fe) and the non-renal enzyme. They are not re-curated.

## Literature search

* **Source.** PubMed, through the NCBI E-utilities (`esearch`, `efetch`). The search date is
  the date of the committed search snapshot.
* **Pediatric query, one per drug:**
  `<term>[tiab] AND clearance[tiab] AND pharmacokinetic*[tiab] AND (neonat*[tiab] OR infant*[tiab]
  OR child*[tiab] OR pediatric*[tiab] OR paediatric*[tiab]) AND humans[mh] AND english[la] AND
  hasabstract`
* **Adult query, one per drug:**
  `<term>[tiab] AND clearance[tiab] AND pharmacokinetic*[tiab] AND (healthy[tiab] OR
  volunteer*[tiab] OR adult*[tiab]) AND humans[mh] AND english[la] AND hasabstract`
* `<term>` is the drug name. For piperacillin–tazobactam it is `piperacillin`, and for
  penicillin G it is `(benzylpenicillin[tiab] OR "penicillin G"[tiab])`.
* The full list of PMIDs returned by each query and every abstract's text are saved, with the
  retrieval date, before screening starts. Screening uses only that snapshot. The abstract
  texts are kept out of the repository (copyright); the PMID lists, the extracted quotes and a
  SHA-256 of each screened abstract are committed, and a script re-verifies every quote against
  PubMed.

## Mechanical pre-filter

An abstract goes to screening only if it contains a numeric clearance with units, matched by a
regular expression fixed in `curation/prefilter.py` before screening. The accepted units are
L/h, l/h, L/hr, L h−1, mL/min, ml/min, L/h/kg, mL/min/kg, L/h/70 kg, mL/min/1.73 m², and the same
with "per", "·" or exponent notation. Abstracts without a match are not read. This keeps
screening tractable and reproducible, and it means the validation uses only values printed in
abstracts.

## Screening and eligibility

Abstracts that pass the pre-filter are screened **in ascending PMID order**. Screening of a drug
stops in a given ICH E11 stratum once **two** studies have been included for that drug and
stratum. The strata are:

* preterm newborn: GA < 37 weeks and PNA < 28 days;
* term newborn: 0–27 days;
* infant/toddler: 28 days–23 months;
* child: 2–11 years;
* adolescent: 12–17 years.

A pediatric study is **included** when its abstract:

* **P1.** studies patients younger than 18 years given the drug intravenously;
* **P2.** reports a numeric total (systemic) clearance for a defined group, or the typical value
  of a population model at a stated covariate point (a weight and an age);
* **P3.** states the group's age: postnatal age, gestational age or postmenstrual age, as a
  central value or a range. Weight is optional;
* **P4.** does not restrict the population to extracorporeal support (ECMO, CRRT, dialysis),
  therapeutic hypothermia, stated renal or hepatic impairment, burns, cystic fibrosis or
  obesity. Critically ill or septic populations are included and flagged `critically_ill`.

Renal clearance, clearance of a metabolite, clearance after oral, intramuscular or
intraperitoneal dosing, and clearance normalized only to BSA without a weight or age that allows
conversion are not total IV clearance and are not extracted.

An **adult** reference is the first abstract, in ascending PMID order, that passes the
pre-filter and reports a mean or typical total IV clearance in adults (18 years or older) who are
healthy or have normal renal function. If no adult abstract qualifies, the drug is excluded from
this validation. The second qualifying adult abstract is kept for sensitivity analysis E4.

## Extraction

For each included group the following are recorded, each with a quote copied **verbatim** from
the abstract: the clearance value and its units, the central age (or age range) and, if stated,
the central weight. One observation is recorded per age group or covariate point that the
abstract reports. A test checks that every quote is a substring of the abstract whose SHA-256 is
committed.

* **Central values.** A mean or median is used as reported. A range alone is scored at its
  midpoint (arithmetic for weight and gestational age; geometric for postnatal age, as in the
  label benchmark's age grid).
* **Missing weight.** The sex-averaged median weight from the label benchmark's growth table at
  the group's age is used, flagged `weight_imputed`.
* **Missing gestational age.** 40 weeks, unless the population is described as preterm. Then it
  is the midpoint of the stated GA range, or 32 weeks when no GA is stated, flagged `ga_imputed`.
* **Unit conversion to L/h:** per-kg values × weight; mL/min × 0.06; per-1.73 m² values ×
  BSA/1.73, where BSA uses the Costeff weight-only formula as in the label benchmark; per-70 kg
  allometric values × (WT/70)^0.75, flagged `allometric_standardized`.

Extraction is finished and committed before any prediction is computed. The extraction code does
not import the engine.

## Predictions

Every method gets the same adult clearance and the same child (weight, postnatal age,
gestational age). Predicted child clearance in L/h:

| Method | Child clearance |
|---|---|
| Weight-linear | CL_adult × WT/70 |
| BSA | CL_adult × BSA(WT)/BSA(70), Costeff |
| Allometry | CL_adult × (WT/70)^0.75 |
| PaedScale | `cl_child_l_h` from `compute_pediatric_dose`, with fe and the enzyme from `../reference_set.json` |

Allometry is the primary comparator: it differs from PaedScale only by the maturation term.

## Endpoints

The fold error is FE = predicted / observed clearance. Each drug's metric is the mean over its
observations, and drugs are then averaged (drug-weighted), as in the label benchmark.

* **Primary hypothesis HE1:** in observations from children under 2 years, PaedScale has a lower
  drug-weighted mean |log10 FE| than allometry.
* **HE2**, tested only if HE1 succeeds: the same comparison for all ages.
* Success is a 95% BCa interval for the paired difference that excludes zero. The interval comes
  from a cluster bootstrap over drugs, 10,000 replicates, seed 20261127, with the same BCa rules
  as the label benchmark.
* **Secondary:** AAFE, AFE, the share of observations within 0.5–2× and within 0.67–1.5× for every
  method, each with a 95% interval; the all-ages comparisons of PaedScale against weight-linear and
  BSA, with Holm-adjusted Wilcoxon p-values on drug-level differences; all of the above by ICH
  stratum.
* **Exploratory:** the share of observed clearances inside PaedScale's 90% parameter-uncertainty
  interval.

## Sensitivity analyses (pre-specified)

* **E1.** Exclude observations flagged `weight_imputed` or `ga_imputed`.
* **E2.** Exclude `critically_ill` observations.
* **E3.** Exclude `allometric_standardized` observations. Those values come from a model that
  already assumed allometric size scaling.
* **E4.** Use the second qualifying adult reference where one exists.
* **E5.** Weight each study equally within a drug, instead of each observation.
* **E6.** Leave one drug out; report the range of the HE1 and HE2 point estimates.
* **E7.** Exclude studies by authors of the maturation-curve sources (Rhodin, Anderson, Holford,
  Anand, Larsson as an author), which may share data with the curves.

## What this validation is not

Abstract values are summaries of small studies with their own designs and assay methods. Typical
values from population models depend on those models. Observed clearance is closer to exposure
than a labeled dose, but it is not an individual patient's clearance. The validation tests the
deterministic engine with fixed inputs, not the live retrieval agent. Curation is done by the
study team with AI assistance; every value carries a verbatim quote that is checked by script.

## Amendments

None yet.
