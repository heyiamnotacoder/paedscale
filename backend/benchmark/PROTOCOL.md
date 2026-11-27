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

### Amendment 2 — 2026-11-27, before any prediction was scored

An internal standards and data audit of the curated reference set found that the label-selection code did not follow Amendment 1 §10, and found curation and harness errors. Every change below was made before `benchmark/run.py` was first executed. No fold error, AAFE or test statistic had been computed for any method. These changes override the text above where they conflict.

1. **Label selection rule as implemented.**
   * The openFDA query is `openfda.generic_name` AND `openfda.route:INTRAVENOUS`, paged through every result (100 per page). There is no route-less fallback.
   * Among the results, the label is the one where the Amendment 1 regex matches the Dosage and Administration text, then the latest `effective_time`. The regex match is a yes/no test, not a score.
   * Applying this rule changed the selected label for six drugs: ampicillin, clindamycin, daptomycin, fluconazole, levetiracetam and midazolam. Their snapshots in `labels/` were replaced and their bands recurated from the new text.
2. **Exclusions after recuration.**
   * **Midazolam** is excluded under E1. Its newly selected label gives no continuous-infusion or other maintenance regimen in machine-readable text. Midazolam is also the CYP3A4 curve-source drug, so S7 now removes only morphine.
   * **Clindamycin** keeps its child and under-1-month bands. Its PMA-based neonatal bands are dropped because that table is an image in the selected label (E1 text rule).
   * **Cefazolin** stays excluded under E1. The adult treatment table is an image; only perioperative prophylaxis is text, so no adult regimen can be paired with the pediatric treatment text.
   * **Digoxin** stays excluded under E2, and it also fails E1: the adult and over-10-year maintenance doses are in image tables.
   * **Fentanyl** stays excluded under E1 (bolus doses only).
   * The reference set is now 21 drugs and 46 bands.
3. **Indication and severity pairing fixes.** The audit applied one tie-break rule throughout: pair the adult and pediatric regimens of the same indication at the same severity tier. Where the label gives several tiers for one severity, use the union of those tiers.
   * **Fluconazole:** paired on systemic *Candida* infection. That is the indication with the most pediatric bands, and the label says its pediatric regimens were chosen to match adult AUC. The adult reference is "up to 400 mg daily" (flag `adult_up_to`). Bands are ≥3 months 12 mg/kg/day, plus two newborn bands to 3 months: GA ≥30 wk at 12 and GA <30 wk at 9 mg/kg/day.
   * **Ceftazidime:** the child reference is the "usual" 30 mg/kg q8h (90 mg/kg/day), matching the adult "usual" regimen. The label's higher dose is reserved for immunocompromised children, cystic fibrosis and meningitis.
   * **Cefepime:** paired on empiric therapy for febrile neutropenia (adult 2 g q8h, child 50 mg/kg q8h).
   * **Piperacillin–tazobactam:** paired on nosocomial pneumonia, the most severe indication with pediatric rows (adult 16 g/day piperacillin; children 2–9 months 320 and over 9 months 400 mg/kg/day, piperacillin component). The child band's upper bound is 16 years, per the label.
   * **Penicillin G:** paired on meningococcal meningitis, the most severe indication with a pediatric row (adult 24 MU/day; children 250,000 U/kg/day).
   * **Aztreonam:** the adult reference is the union of the moderately severe to severe tiers (5 g/day, range 2–8 g/day).
   * **Famotidine:** the reference is the midpoint of the labeled titration (0.25 mg/kg q12h, titrated to 0.5 mg/kg q12h), which is 0.75 mg/kg/day. Famotidine is added to the S8 titrated-drug set.
4. **Excretion fractions corrected to the label's text.**
   * Meropenem fe = 0.625.
   * Amikacin fe = 0.94.
5. **Flags added.**
   * Tobramycin newborn band: `mgkg_shared`, in addition to `up_to`.
   * Zidovudine newborn band: `indication_mismatch`, in addition to `mgkg_shared`.
6. **Growth reference.**
   * WHO medians are used for 0–1826 days (5 years exactly), not 0–1856 days, and the CDC 2000 medians from there on.
   * For preterm infants between 40 and 50 weeks PMA, weight is a linear bridge from the Fenton 40-week value to the WHO median at 10 weeks corrected age. This removes a 5% weight drop at the Fenton→WHO handover.
7. **S5 varies GA only for preterm bands.** Term bands (GA ≥ 37 weeks, or no GA) keep GA 40 under S5.
8. **The concordance band is 0.67–1.5 everywhere.** The harness had used 1/1.5 as the lower bound in one place.
9. **BCa details.** Ties between a bootstrap replicate and the point estimate count half when estimating the bias correction z0. The interval falls back to the percentile method when there are fewer than 3 drug clusters, when z0 is undefined, or when the acceleration adjustment is undefined.
10. **S3 and the primary comparator.** Under S3 every drug uses `css`, so A1 becomes plain allometry for aminoglycosides. This follows from the definition of A1 in Amendment 1 §2.
11. **S9 is applied literally.** The `renal_mechanism` regex finds "tubular secretion" in the levetiracetam label, in a sentence about its metabolite ucb L057. The parent drug is filtered and partly reabsorbed. Under the Amendment 1 §14 wording, the label mentions tubular secretion, so levetiracetam is left out of S9. This makes S9 smaller and more conservative, and it is reported as a known limitation of the text rule.

### Amendment 3 — 2026-11-27, before any prediction was scored

A code review of the Amendment 2 commit found the defects below. They were fixed before `benchmark/run.py` was first executed; no fold error, AAFE or test statistic had yet been computed on the reference set. These changes override the text above where they conflict.

1. **Combination products are not candidates.** The openFDA phrase query for a single drug also matches combination products (for example, "ampicillin" matches ampicillin and sulbactam). A label is a candidate only if its active ingredients are exactly the candidate's. Salt forms and dosage-form words are allowed (ampicillin sodium; vancomycin injection, USP), and premix diluents (dextrose, sodium chloride, water) are not active ingredients. The label's generic name is split into components on the word "and" and on commas, and a component made only of dosage-form words ("injection", "USP") is dropped. Each of the candidate's ingredients must match a different component as whole words. `fetch_labels.py` overwrites a committed snapshot only when run with `--write-snapshots`.
2. **Deterministic tie-break.** openFDA does not guarantee result order, and six drugs had several candidates with the same regex result and the same latest `effective_time`. Ties now go to the highest SPL `version` (the most-revised document), then to the highest `set_id`. The rule was chosen before the tied labels' doses were read.
   * Under rules 1 and 2, the selected label changed for meropenem, cefazolin, midazolam and fentanyl. Ampicillin keeps its Amendment 2 label once the combination products are removed, and fluconazole keeps its label under the tie-break.
   * Meropenem's new label has the same regimens, fe text and quotes, so its reference values do not change.
   * Cefazolin, midazolam and fentanyl remain excluded under E1 for the reasons recorded in `reference_set.json`. On their new labels the adult regimens are still image tables or induction doses only.
   * The reference set stays at 21 drugs and 46 bands.
3. **Cluster bootstrap.** A drug drawn more than once in a bootstrap resample counts as separate clusters. Each draw is relabelled before the statistic is computed. Without this, duplicated drugs were merged, and every interval was too narrow.
4. **Every reported summary gets a full interval.** Every summary has a 95% BCa interval from 10,000 drug-clustered replicates. That covers each method's AAFE, AFE, share in 0.67–1.5, share in 0.5–2 and share within the labeled range, for all ages, under 2 years, newborns and each ICH stratum. It also covers the pair-weighted AAFE (Amendment 1 §5), PaedScale's summary in every sensitivity analysis, and the exploratory interval coverage, which is drug-weighted like every other summary. Two kinds of number are descriptive and get no interval: the S6 leave-one-drug-out ranges, which are ranges of point estimates, and the widths of the 90% parameter intervals.
5. **Multiplicity.** The Holm adjustment for the three secondary comparisons applies to their drug-level Wilcoxon p-values. Their bootstrap intervals are reported unadjusted at 95%.
6. **Ties are counted.** Each comparison reports the number of tied pairs and tied drugs, meaning a mean difference with absolute value ≤ 10⁻¹². For the Wilcoxon test, tied drugs are dropped and counted. They stay in the bootstrap estimate.
7. **S2** excludes exactly the flags listed for it: `indication_mismatch`, `fe_qualitative`, `up_to` and `adult_up_to`. It no longer also drops `fe_not_in_label`.
8. **S9 as implemented.**
   * S9 keeps only drugs whose `renal_mechanism` is `glomerular_filtration`. Non-renal drugs are not part of S9.
   * The rule reads the clinical pharmacology and pharmacokinetics sections, where labels state the renal mechanism.
   * "Tubular excretion" is treated as tubular secretion.
9. **S6** reports the leave-one-drug-out range for both the newborn comparison (H1) and the all-ages comparison (H3).
10. **Provenance.** `results.json` records the engine commit, whether the working tree was dirty, the bootstrap settings and the library versions. `pairs.csv` starts with one provenance comment line beginning with `#` (read it with `comment="#"`), and the figures carry the commit in their metadata. CI runs `python -m benchmark.run` with 200 replicates as a smoke test. The manuscript numbers come from the committed run with 10,000 replicates.
11. **Known consequences of the pre-specified rules, stated here so they are not post hoc.**
    * The two fluconazole newborn bands span birth to 3 months. Their midpoint (about 46 days) puts them in the infant/toddler stratum, so they count toward H2 and H3 but not H1.
    * Under S5 +2 weeks, the fluconazole GA ≥ 30 band moves from GA 35 to 37 and so uses the term growth curve.
    * Meropenem fe is the midpoint of the label's stated range, 50–75% (0.625), per the protocol's range rule, even though the same sentence says "approximately 70%".
12. **Erratum to Amendment 2 §3.** The piperacillin–tazobactam child band's upper bound of 16 years comes from the protocol's rule for an open upper bound (21 CFR 201.57). The label itself says only "older than 9 months", not 16 years.
