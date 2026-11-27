# PaedScale label benchmark — analysis protocol

Written and committed **before** any prediction was scored against the reference set.
Every later change is logged under "Amendments" with its reason.

## Question

When the only inputs are an adult regimen and a child's age and weight, how close is each
size-scaling method to the dose the FDA label gives that child? The methods are
weight-linear, body-surface-area, allometry alone, and PaedScale (allometry × maturation).

## Reference standard

* **Source.** Public FDA Structured Product Labels (SPL) retrieved from openFDA
  (`/drug/label.json`). Per drug, the label is chosen by a fixed rule: among labels whose
  generic name matches and whose route includes INTRAVENOUS, prefer the one whose Dosage and
  Administration text mentions pediatric or neonatal dosing; break ties by the latest
  `effective_time`. The set ID and effective date are recorded. A text snapshot of the
  Dosage and Administration, Pediatric Use and Clinical Pharmacology sections is stored in
  `labels/`, so the benchmark reruns offline.
* **Verbatim evidence.** Each adult dose, pediatric dose and urinary-excretion value carries
  a quote that must appear verbatim in the stored snapshot. A test enforces this.
* **Reference dose.** The labeled daily maintenance dose in mg/kg/day (units/kg/day for
  penicillin G). A labeled range is scored at its arithmetic midpoint, and the range is
  kept for the within-range endpoint. "Up to X" is scored at X and flagged.

## Candidates and eligibility

Candidates (25, fixed before scoring): vancomycin, gentamicin, tobramycin, amikacin,
ampicillin, cefazolin, ceftazidime, cefepime, meropenem, piperacillin–tazobactam, acyclovir,
fluconazole, levetiracetam, famotidine, daptomycin, digoxin, midazolam, clindamycin,
fentanyl, morphine, zidovudine, cefoxitin, aztreonam, penicillin G potassium, cefuroxime.
They are the PaedScale demo drugs plus commonly used IV anti-infectives, anticonvulsants,
acid suppressants, cardiac glycosides, sedatives and opioids. Candidates were chosen by the
authors, not by a systematic search; selection bias is a stated limitation.

A drug is **included** if all of these hold:

* **E1.** The selected label gives an adult IV *maintenance* regimen (repeated or
  continuous) as machine-readable text. Single induction, premedication or bolus doses do
  not count. Dosing tables published only as images do not count.
* **E2.** The selected label gives at least one pediatric IV maintenance regimen for a
  defined age band, in mg/kg/day or convertible to it.
* **E3.** Elimination maps onto the engine's published curves. Either the label states a
  quantitative fraction excreted unchanged in urine, or it names CYP3A4 or UGT2B7
  (glucuronidation) as the principal clearance route. The enzyme identity may come from
  cited literature.
* **E4.** Clearance is linear at labeled doses (no Michaelis–Menten drugs).

Every excluded candidate is reported with the criterion it failed.

## Pairing the adult and pediatric regimens

1. Where the label gives the same indication for adults and for the pediatric band, use
   that indication for both.
2. When a drug has several indications, use the one with the most labeled pediatric age
   bands; break ties by the most severe indication.
3. If the adult regimen has severity tiers and the pediatric row does not, score the adult
   reference at the midpoint of the union of the tiers. Where the label calls one regimen
   "usual", use the usual regimen instead.
4. If a neonatal band exists only for a neonate-specific indication, pair it with the
   closest adult indication and flag it `indication_mismatch`.
5. An adult dose labeled in mg/kg is converted with a 70 kg reference adult.
6. A pair is flagged `mgkg_shared` when the label gives the adult and that pediatric band
   the same mg/kg/day. Such a pair is weight-linear by construction and is analysed both
   with and without this flag.

## Model inputs (identical for every method)

* **Renal fraction.** fe is the label's fraction of the dose excreted unchanged in urine,
  taken from the longest collection reported. A range is scored at its midpoint. A label
  that is only qualitative ("largely unchanged") gets fe = 0.90 and the flag
  `fe_qualitative`. In PaedScale, fe maps to `renal_gfr`; this applies the GFR curve to
  total renal clearance, including tubular secretion, which is a stated assumption.
* **Non-renal fraction.** If the label or the cited literature names CYP3A4 or UGT2B7 as
  the principal route, `fm[enzyme] = 1 − fe`. Otherwise the non-renal fraction stays
  unattributed and is scaled by size only. If a label names the enzyme but gives no fe,
  fe = 0 and the pair is flagged.
* **Target metric** follows a class rule, never chosen per drug:
  * aminoglycosides use `cmax`;
  * β-lactams (penicillins, cephalosporins, carbapenems, monobactams) use `time_mic`;
  * all other drugs use `css`.
* **Adult reference** is 70 kg at postmenstrual age (PMA) 40 years, as in the engine.

## Virtual patient per band

* **Postnatal age.** The arithmetic midpoint of the label's band. An open upper bound is
  16 years (FDA pediatric definition, 21 CFR 201.57). A band starting at "birth" starts at
  0 days.
* **Gestational age.** 40 weeks, unless the band is defined by gestational or
  postmenstrual age:
  * "≤ X" or "< X" weeks uses X − 2;
  * "> X" or "≥ X" weeks uses the midpoint of X and 40;
  * a closed GA range uses its midpoint;
  * a band defined by PMA alone uses PMA midpoint − 2 weeks of PNA.
* **Weight.** The sex-averaged median:
  * WHO Child Growth Standards for 0–5 years;
  * CDC 2000 for older than 5 years;
  * for preterm neonates, the approximate Fenton 2013 50th centile at the infant's PMA.

  Sensitivity analyses vary the weight by ±20% and the representative gestational age by
  ±2 weeks.
* **Stratum.** Each pair is assigned an ICH E11 category from its virtual patient:
  * preterm newborn: GA < 37 weeks and PNA < 28 days;
  * term newborn: 0–27 days;
  * infant/toddler: 28 days–23 months;
  * child: 2–11 years;
  * adolescent: 12–16 years.

## Methods compared

Each method is given the same adult daily dose and the same virtual patient. Predictions
are in mg/kg/day.

| Method | Child daily dose |
|---|---|
| Weight-linear | adult × WT/70 |
| BSA (Costeff, weight-only) | adult × BSA(WT)/BSA(70), BSA = (4·WT+7)/(WT+90) |
| Allometry only | adult × (WT/70)^0.75 |
| PaedScale | `compute_pediatric_dose` with the inputs above |

## Endpoints

The fold error is FE = predicted / reference.

* **Co-primary:**
  * AAFE = 10^mean(|log10 FE|) over all pairs;
  * AAFE over pairs younger than 2 years (newborns and infants). This is where size-only
    methods are expected to fail.
* **Secondary:**
  * AFE (bias) = 10^mean(log10 FE);
  * % of pairs with FE in 0.67–1.5 (the PaedScale concordance band);
  * % with FE in 0.5–2;
  * % with the prediction inside the labeled range;
  * all of the above per ICH stratum.
* **Inference:** PaedScale is compared with each comparator using a paired difference in
  mean |log10 FE|.
  * The 95% CI comes from a cluster bootstrap that resamples drugs (10,000 replicates,
  seed 20261127), because the bands within a drug are not independent.
  * A Wilcoxon signed-rank test on the paired |log10 FE| is reported as a secondary test.
  * Nothing is adjusted for multiplicity; there are three comparisons, and all are
    reported.
* **Uncertainty calibration (exploratory):** the share of reference doses that fall inside
  PaedScale's 90% parameter-uncertainty interval.

## Sensitivity analyses (pre-specified)

* **S1.** Exclude `mgkg_shared` pairs.
* **S2.** Exclude `indication_mismatch`, `fe_qualitative` and "up to X" pairs.
* **S3.** Every drug uses `css`, which ignores the class rule for the target metric.
* **S4.** Weight ±20%.
* **S5.** Representative gestational age ±2 weeks for preterm bands.
* **S6.** Leave one drug out: report the range of the co-primary AAFE difference.

## What this benchmark is not

Label doses are a clinical reference standard, not measured exposure. Many were set by
pediatric PK studies, and some were set by mg/kg convention. Agreement with the label
therefore measures agreement with current practice, not exposure matching. The benchmark
exercises the deterministic engine with label-derived inputs. It does not evaluate the live
LLM retrieval agent, which is reported separately.

## Amendments

### Amendment 1 — 2026-11-27, before any prediction was scored

These changes answer an internal methodological review of the first version of this protocol. They were made after the reference set was curated (`reference_set.json`) and before any scoring code existed. They override the text above wherever the two conflict.

1. **Hypothesis hierarchy, replacing the co-primaries.**
   * **Primary comparator:** "allometry + class rule" (A1 below). It differs from PaedScale *only* by the maturation term, so the comparison isolates maturation.
   * **Hypotheses**, tested in a fixed sequence. Each is tested only if the one before it succeeded, at a two-sided α of 0.05:
     * **H1** (newborns: preterm and term, PNA < 28 d): PaedScale has a lower drug-weighted mean |log10 FE| than A1.
     * **H2:** the same comparison for all pairs under 2 years.
     * **H3:** the same comparison for all pairs.
   * **Other comparators** (weight-linear, BSA, allometry-only): their three all-ages comparisons are secondary and Holm-adjusted.
   * No power calculation is made: the sample is every eligible label. The number of drug clusters is reported with every estimate.
2. **Added comparator A1, allometry + class rule.**
   * Drugs using `cmax` get adult × WT/70 (volume-matched, as in the engine).
   * All other drugs get adult × (WT/70)^0.75.
   * Plain allometry-only is kept as a secondary comparator.
3. **PaedScale equals weight-linear for aminoglycosides, by construction.**
   * The engine's `cmax` solve is adult × Vd ratio, and Vd scales with WT^1.0, so the two methods give identical predictions for aminoglycosides. These ties are reported as ties.
   * The engine's interval suggestion is not part of the mg/kg/day endpoint.
4. **Fixed engine inputs.** `cl_adult_l_h = 10` and `vd_adult_l = 50` for every drug. Both cancel out of the css/auc/time_mic dose ratio (CL_child/CL_adult) and out of the cmax ratio, so they affect only the reported half-life.
5. **Drug-weighted aggregation.** Each metric is computed per drug (the mean over that drug's bands), then averaged over drugs. Pair-weighted values are reported as a sensitivity analysis.
6. **Age grid instead of a single child per band.**
   * Each band is scored at 7 postnatal ages log-spaced between max(lower bound, 1 day) and the upper bound. A band with a single age is scored at that age.
   * The band's prediction is the geometric mean across the grid; its reference dose is constant.
   * The single arithmetic-midpoint child is kept as sensitivity analysis S10.
   * The ICH stratum is assigned from the band's arithmetic midpoint.
7. **Confidence intervals.**
   * Every reported metric gets a 95% CI from a cluster bootstrap that resamples drugs (10,000 replicates, seed 20261127).
   * The CI is BCa, falling back to percentile where BCa is undefined.
   * The Wilcoxon signed-rank test is run on drug-level mean differences, not on pairs.
8. **E3 contradiction removed.** E3 now reads: "the label states that the drug is eliminated predominantly unchanged in urine (quantitatively or qualitatively), or names CYP3A4 or UGT2B7 (glucuronidation) as the principal clearance route". A qualitative statement gives fe = 0.90 and the flag `fe_qualitative`.
9. **Enzyme identity sources are fixed.**
   * Morphine → UGT2B7: Coffman et al., Drug Metab Dispos 1997;25:1–4.
   * Zidovudine → UGT2B7: Barbier et al., Drug Metab Dispos 2000;28:497–502.
   * Midazolam and clindamycin → CYP3A4: their labels.
10. **Label selection regex.**
    * "Mentions pediatric dosing" means the regex `pediatric|neonat` (case-insensitive) matches the Dosage and Administration text.
    * Retrieval date: 2026-11-27.
    * Generic (ANDA) labels must carry the same labeling as their reference listed drug (21 CFR 314.94(a)(8)), so repackager and ANDA labels are accepted. The SPL `version` is recorded.
11. **Indication choices are fixed in the data.** Each drug's paired indication, the reason for it and the verbatim quotes are recorded in `reference_set.json` before scoring. Any later change counts as an amendment.
12. **Titrated infusions.** For midazolam and morphine the label gives a starting infusion rate for adults and children, and that starting rate is the reference. S8 excludes these titrated drugs.
13. **Circularity.** The CYP3A4 curve was fitted to midazolam clearance and the UGT2B7 curve to morphine clearance. S7 excludes these curve-source drugs (midazolam, morphine).
14. **Tubular secretion.** S9 keeps only the renally cleared drugs whose selected label names glomerular filtration as the renal mechanism and does not mention tubular secretion. This is decided from the label wording alone and is recorded per drug as `renal_mechanism` in `reference_set.json`.
15. **Dose caps.** Labeled absolute caps ("not to exceed the adult dose", mg/day maxima) are not applied to the reference or to any prediction, so all methods are treated alike.
16. **Units.** Penicillin G is in units. It enters only through the dimensionless fold error.
17. **Reproducibility.**
    * The growth table (`data/weight_median.csv`) and the label snapshots are committed.
    * Interpolation is linear in age.
    * Every output records the git commit of the engine.
    * Product code must never import `benchmark`, and a test enforces this.
    * One command regenerates every number, table and figure: `python3 -m benchmark.run` from `backend/`. It writes to `benchmark/output/`.
    * CI runs the benchmark tests.
18. **Rationale for GA X − 2.** It places the representative infant inside the band, just below the cut-off. S5 varies it by ±2 weeks.
