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

### Amendment 1 — 2026-11-27, before any search was run, any abstract was screened or any value was extracted

This answers an internal methods review of the protocol above. These rules override the text above where the two conflict.

1. **Screening order.** The ascending-PMID order is replaced, because it would pick the oldest studies first.
   * Each drug's pre-filtered pediatric PMIDs are shuffled with Python's `random.Random(20261127)` after being sorted ascending. Screening follows that order.
   * A study is included if it adds at least one eligible observation to a stratum that has fewer than two included studies for that drug.
   * It contributes its eligible observations in every such stratum, and it counts toward the cap of each stratum it contributes to.
   * Its observations in strata that are already full are not used.
2. **Adult reference.** The single oldest adult abstract is replaced with a pooled value, because one adult study would control the comparison.
   * Adult abstracts that pass the pre-filter are screened in the same seeded order. Up to the first five qualifying ones are kept.
   * A qualifying abstract reports the mean or typical total IV clearance in adults aged 18–65 years who are healthy or have normal renal function, without probenecid.
   * Each value is converted to a 70 kg adult:
     * per-kg values × 70;
     * absolute values with a stated mean weight × (70/WT)^0.75;
     * absolute values without a weight are used as reported and flagged `adult_weight_missing`.
   * The adult reference is the median of the kept values.
   * E4 now uses only the first qualifying adult abstract instead of the median.
3. **Values standardized per 70 kg** are accepted only when the abstract states the age (PMA, or PNA with GA) at which the value applies. The value is the study model's typical value at that age, so it is converted with (WT/70)^0.75 at that age's weight. Otherwise it is not extracted.
4. **Circularity.** Two flags are added.
   * `fixed_maturation` applies when the abstract, or the open-access full text in PubMed Central where one exists, says the model fixed a maturation function or fixed its maturation parameters from the literature.
   * `fixed_allometry` applies when the model fixed the allometric exponent.
   * E3 now excludes `allometric_standardized`, `fixed_maturation` and `fixed_allometry` observations.
   * E7 names the curve-source authors exactly: Anderson BJ, Holford NHG (NH), Rhodin MM, Anand KJ (KJS), Larsson P.
5. **Eligibility clarifications.**
   * When an abstract gives both a group summary (the mean or median of individual or non-compartmental estimates) and a model typical value, the group summary is used.
   * A clearance given only as a range has no central value and is not extracted.
   * CL/F, and values from models that pool oral or intramuscular with IV data without an IV-only value, are not extracted.
   * Studies that coadminister probenecid are excluded.
   * Piperacillin clearance is accepted with or without tazobactam, flagged `with_tazobactam` when given together.
   * Bolus and infusion are both accepted, because clearance is linear at labeled doses.
6. **Age rules.**
   * When an abstract gives PMA, the engine uses PMA directly. GA then matters only for weight imputation, which uses the Fenton chart at that PMA below 50 weeks, as in the label benchmark.
   * "Conceptional" and "postconceptional" age are read as PMA, flagged `pca_as_pma`.
   * When an age range is stated, predictions are made at 7 ages log-spaced across it, and the prediction is their geometric mean, as in the label benchmark. When only a central age is stated, one age is used.
   * The stratum and the under-2 split use the central postnatal age. When only a range is stated, the geometric midpoint is used.
7. **BSA.** A stated BSA, or Mosteller BSA from a stated height and weight, is used for per-1.73 m² conversion. Costeff BSA is used only when neither is given, flagged `bsa_costeff`.
8. **Statistics.**
   * HE1 and HE2 succeed only if the upper bound of the 95% interval for PaedScale minus allometry is below zero. An interval entirely above zero is reported as evidence against PaedScale.
   * HE1 is confirmatory only if at least 8 drugs contribute observations under 2 years. Otherwise HE1 and HE2 are reported as descriptive.
   * An exact sign-flip permutation test on the drug-level paired differences is added as a secondary test. It enumerates every sign assignment when there are 20 or fewer drugs.
   * Per-stratum intervals are reported only for strata with at least 5 drugs.
9. **Duplicate screening and extraction.**
   * A second, independent pass screens and extracts every pre-filtered abstract up to each stratum's cap. It works blind to the first pass's decisions.
   * Both passes are AI-assisted (Claude, Anthropic). The second runs in a fresh context with only this protocol and the abstract texts.
   * Inclusion agreement is reported as Cohen's κ. Extracted numbers are compared value by value.
   * A disagreement is resolved by re-reading the abstract against the protocol, and each resolution and its reason are recorded.
   * The authors must verify the final dataset before submission.
   * A PRISMA-style flow of records (retrieved, pre-filtered, screened, included, by reason excluded) is reported.
10. **Pre-filter widened.** It now matches:
    * a body-size unit before the time unit ("mL/kg/h");
    * a bracketed denominator ("L/(h·kg)");
    * up to 40 characters of bracketed text between the number and the unit ("3.2 (95% CI 2.9–3.5) L/h");
    * the unit before the number ("CL (L/h) was 3.2");
    * dot and "x" separators, spelled-out units, and per-day units.

    The cases are in `tests/test_external_prefilter.py`. Infusion rates, creatinine clearance and similar false positives only add screening work, and screening removes them.
11. **Added sensitivity analysis E8.** Exclude studies published before 1995. Older assays and neonatal care differ.

### Amendment 2 — 2026-11-27, before any search was run, any abstract was screened or any value was extracted

This answers a code review of the search script and of Amendment 1. These rules override the text above where the two conflict.

1. **Synonyms.** The search term for acyclovir is `(acyclovir[tiab] OR aciclovir[tiab])`, and for zidovudine `(zidovudine[tiab] OR azidothymidine[tiab])`.
2. **Snapshot integrity.**
   * Each query is one `esearch` call with retmax 9,999. Any esearch error or warning, or a count of 10,000 or more, stops the snapshot.
   * Every PMID must come back from `efetch` as a journal article with abstract text, or the snapshot stops.
   * The query translation and each record's publication year are saved. E8 needs the year.
   * Requests identify the tool as `paedscale` with a generic project address, and retry with backoff on 429 or 5xx responses.
3. **Hashed text.** The title, a blank line, then each English abstract section on its own line as `LABEL: text` (or the text alone when unlabelled), with inline markup flattened and runs of whitespace collapsed. Abstracts in other languages are not included.
4. **Shuffle.** For each drug and each list (pediatric, adult), the pre-filtered PMIDs are sorted numerically ascending, then shuffled with a fresh `random.Random(20261127)`.
5. **Adult abstracts with several groups.** The qualifying groups' values are converted to 70 kg and their median is that abstract's value. Healthy volunteers with no stated age count as adults, flagged `adult_age_unstated`.
6. **Circularity flags come from the abstract only.** Amendment 1 §4's use of full text is withdrawn, so that both screening passes see the same information. A model that fixed a maturation function without saying so in its abstract is missed; this is a stated limitation.
7. **Age grid.** The grid runs from max(lower bound, 1 day) to the upper bound. A stated central weight is used at every grid age. Without one, each grid age takes the growth-table weight for that age.
8. **κ** is computed over the abstracts that both passes read.
9. **Pre-filter.** Whitespace is collapsed before matching, which removes a slow-matching case. It also accepts en-dash exponents ("kg–1"), per-day "d" ("L/kg/d") and dL. The cases are in `tests/test_external_prefilter.py`.
10. **Workload.** When a stratum never fills, the whole pre-filtered list for that drug is read. This is accepted, because stopping early on effort would make inclusion depend on reading order beyond the seeded shuffle.

### Amendment 3 — 2026-11-27, after the search snapshot was committed, before any abstract was screened or any value was extracted

Setting up the screening tools showed two gaps. These rules override the text above where the two conflict.

1. **Per-square-metre clearance.** Older pediatric studies report clearance per m² of BSA (for example "ml/min per m(2)"), not per 1.73 m². Such a value is converted to L/h as value × BSA, with BSA chosen as in Amendment 1 §7. The units are `mL/min/m2` and `L/h/m2`.
2. **Screening order between the lists.** A drug's adult list is screened once every pediatric stratum is full or the pediatric list is exhausted, whichever comes first. Screening of the drug ends when five adult abstracts qualify or the adult list is exhausted. `curation/screening.py` applies this, and `curation/check.py` checks each pass's records against the seeded order and the committed hashes.

### Amendment 4 — 2026-11-27, before any abstract was screened or any value was extracted

This answers a code review of the screening tools and of Amendment 3. These rules override the text above where the two conflict.

1. **What was seen before screening.** Amendment 3 §1 should have said how the per-m² gap was found. A smoke test of the screening queue printed the one pre-filtered pediatric cefoxitin abstract (PMID 7396456) in full, and it reports clearance "per m(2)". No decision was recorded for it, and both passes screen it like any other abstract. To find other unit forms that the extraction units did not cover, the pre-filter's matches were then tallied over all pre-filtered abstracts, with every number masked and nothing else shown. The tally found absolute mL/h (about 40 matches) and L/min (3 matches). These units are added, with the per-day per-kg and per-1.73 m² per-hour forms that the pre-filter already accepts: `mL/h`, `L/min`, `L/day/kg` and `mL/h/1.73m2`. A value in any other unit is not extracted.
2. **Central age and range.** When an abstract states both a central age and a range, both are recorded. The central value sets the stratum and the under-2 split, and the range sets the prediction grid (Amendment 1 §6).
3. **Gestational age alone.** P3 is narrowed. A group described only by gestational age, with no postnatal age or PMA, is excluded as "no age", because GA alone does not say when clearance was measured.
4. **Preterm groups.** Each observation records whether the abstract describes the group as preterm. Stratum assignment uses the same GA rule as the predictions: the stated GA, else 32 weeks for a preterm group, else 40 weeks. With PMA only, postnatal age is PMA − GA, floored at 0.
5. **Flags.** A study-level flag applies to all of its observations and an observation-level flag to that observation; the analysis uses both. Screeners record only `critically_ill`, `allometric_standardized`, `fixed_maturation`, `fixed_allometry`, `with_tazobactam`, `pca_as_pma`, `adult_weight_missing` and `adult_age_unstated`. The scorer adds `weight_imputed`, `ga_imputed` and `bsa_costeff`.
6. **Record checks.** `curation/check.py` also reports pediatric abstracts screened after every stratum was full, adult screening that began before the pediatric list stopped, adult abstracts screened after five qualified, and absolute adult values without a weight that lack the `adult_weight_missing` flag.
7. **Amendment 3 §2 changes workload only.** The pediatric and adult lists are screened independently in their own seeded orders, so the order between them cannot change which studies are included.

### Amendment 5 — 2026-11-27, after the search snapshot, the one abstract and the unit tally described in Amendment 4 §1 were seen, before any abstract was screened or any value was extracted

This answers a second code review of the screening tools and of Amendment 4. These rules override the text above where the two conflict.

1. **Amendment 4's heading** should have said, as this one does, that the snapshot, one abstract and the masked unit tally had been seen.
2. **Gestational age when not stated.** GA is PMA − postnatal age when both are stated. Otherwise the default of Amendment 4 §4 (32 weeks preterm, 40 weeks otherwise) applies, capped at the stated PMA, because GA cannot exceed PMA. So a group at PMA 30 weeks is a preterm newborn even when the abstract does not say "preterm".
3. **Per-70 kg values** need the `allometric_standardized` flag. "PNA with GA" in Amendment 1 §3 applies under 2 years; from 2 years a postnatal age alone fixes the age with GA taken as 40 weeks. At 2 years, a GA of 28 instead of 40 weeks changes the maturation fraction by at most 3.4% (CYP3A4) and under 1% for the renal and UGT2B7 curves.
4. **Adult values** must be absolute or per kg, the only forms Amendment 1 §2 converts. An adult abstract with only per-BSA or per-70 kg values does not qualify. A stated adult age is recorded in years and must lie within 18–65 years.
5. **Other recorded numbers.** Weight may be a range when only a range is stated, scored at its arithmetic midpoint as the body says. A stated BSA or height is recorded with its own verbatim quote, checked like the others.
6. **The unit tally is reproducible.** `curation/unit_tally.py` writes the masked tally to `unit_tally.json` (committed). It has 46 absolute mL/h matches and 3 L/min matches. Of the per-day forms, it has one "l per day" match and no per-kg per-day or dL forms.
7. **What check.py can see.** The two lists are recorded separately, with no order between them. `check.py` reports adult decisions when the recorded pediatric list had not reached its stop. It cannot see adult screening that started early and was followed by more pediatric screening. By Amendment 4 §7 this cannot change which studies are included. It runs the stop checks only on records with no other problem.

### Amendment 6 — 2026-11-27, at the same point as Amendment 5 (nothing more seen), before any abstract was screened or any value was extracted

This answers a third code review of the screening tools and corrects Amendment 5. These rules override the text above where the two conflict.

1. **Amendment 5 §6 corrected.** The tally has 56 matches of millilitres per hour in number-first forms ("# ml/h", "# ml/hour", "# () ml/h", "# ml/hr", "# ml h", "# ml/(h"), not 46 absolute ones. A matched form ends at the time unit, so "12 ml/h/kg" also masks to "# ml/h". The tally therefore shows which unit forms occur, not how many values are absolute, per kg or per BSA. The same holds for the 3 "# l/min" matches and for the per-day forms. Of the 64 unit-first matches, a few keep up to 30 characters of unmasked words after the unit, such as "decreased significantly from #". That text was seen with the tally.
2. **Amendment 5 §3 corrected.** A postnatal age alone fixes the age of a per-70 kg value only when the whole stated range is 2 years or older (its lower bound, or the central value when no range is stated). The prediction grid spans the range, and at 1 year a GA of 28 instead of 40 weeks changes the CYP3A4 maturation fraction by about 15%.
3. **Flags by list.** Pediatric records carry only `critically_ill`, `allometric_standardized`, `fixed_maturation`, `fixed_allometry`, `with_tazobactam` and `pca_as_pma`. Adult records carry only `with_tazobactam`, `adult_weight_missing` and `adult_age_unstated`. This refines Amendment 4 §5.
4. **GA from PMA and postnatal age** uses the geometric midpoint of a postnatal range, as the stratum does (Amendment 1 §6). An observation whose PMA and postnatal age imply a GA outside 20–45 weeks is reported as a recording error.
5. **Checks report, never raise.** A malformed record is reported as a problem for that study or that drug, and checking goes on.

### Amendment 7 — 2026-11-27, at the same point as Amendment 5 (nothing more seen), before any abstract was screened or any value was extracted

This answers a fourth code review and corrects Amendment 6. These rules override the text above where the two conflict.

1. **GA from PMA and postnatal age** subtracts the arithmetic midpoints of both, because a GA is a difference of two ages on the same scale. Amendment 6 §4 used the geometric midpoint of the postnatal range here, which made consistent wide-range infant groups (for example PMA 26–100 weeks with postnatal age 1–500 days) look like recording errors. The geometric midpoint is still used for the stratum and the under-2 split (Amendment 1 §6).
2. **Preterm status is always recorded.** Every pediatric observation states whether the abstract describes the group as preterm, so a missing answer cannot silently default to term.
3. **Wording.** Unit-first tally forms (Amendment 6 §1) also keep up to 20 unmasked characters inside the brackets.

### Amendment 8 — 2026-11-27, at the same point as Amendment 5 (nothing more seen), before any abstract was screened or any value was extracted

This answers a fifth code review. These rules override the text above where the two conflict.

1. **GA is not inferred from PMA and postnatal age.** Group summaries of PMA and postnatal age do not subtract to the group's GA: a term group at PMA 40 weeks with postnatal age 1–121 days would come out as 31 weeks and be filed as preterm. Amendment 5 §2 (first sentence) and Amendment 7 §1 are withdrawn. GA is as stated; otherwise 32 weeks for a group described as preterm and 40 weeks for any other group, capped at the stated PMA. The engine uses PMA directly whenever it is stated (Amendment 1 §6), so this GA affects only the stratum and weight imputation.
2. **Consistency of PMA and postnatal age.** When both are stated, an observation is reported as a recording error only if no GA of 20–45 weeks fits both: the largest stated PMA minus the smallest postnatal age is below 20 weeks, or the smallest PMA minus the largest postnatal age is above 45 weeks.
3. **Inputs to each pass.** Both passes work from this protocol, `SCREENING_GUIDE.md` (the record format that `curation/check.py` enforces, which defers to this protocol) and the abstract texts. This is what Amendment 1 §9 means by "only this protocol and the abstract texts".

### Amendment 9 — 2026-11-27, at the same point as Amendment 5 (nothing more seen), before any abstract was screened or any value was extracted

This answers a sixth code review. These rules override the text above where the two conflict.

1. **Default GA cap.** The default GA of Amendment 8 §1 is capped at the largest stated PMA minus the smallest stated postnatal age, not at the PMA alone. A group at PMA 38 weeks and postnatal age 21 days has a GA of at most 35 weeks, so it is a preterm newborn even without the word "preterm". Amendment 6 §4 is withdrawn with Amendment 7 §1, except as restated in Amendment 8 §2 and below.
2. **Stated GA.** An observation whose stated GA exceeds the largest PMA minus the smallest postnatal age by more than half a week is reported as a recording error.
3. **`ga_imputed`** is set when no GA is stated and either the group is described as preterm (the 32-week default) or the cap puts the GA below 37 weeks. A term default of 40 weeks, or a cap that leaves it at 37 weeks or more, is not flagged, as in the body. E1 excludes flagged observations.
4. **Scope of the GA default.** It sets the stratum and weight imputation. Without a stated PMA, the engine is also given GA plus postnatal age, so the default then enters the prediction too.
5. **Stated limitation.** A group described neither as preterm nor by GA, with PMA 37 weeks or more and postnatal age under 28 days, is treated as term even if some of its members were preterm.

### Amendment 10 — 2026-11-27, at the same point as Amendment 5 (nothing more seen), before any abstract was screened or any value was extracted

This answers a seventh code review and corrects Amendment 9. These rules override the text above where the two conflict.

1. **Default GA cap, corrected.** Amendment 9 §1 capped the default at the *largest* PMA minus the *smallest* postnatal age. That let a PMA-only group at a central PMA of 34 weeks (range 28–40) take the term default of 40 weeks. The cap is instead the central PMA minus the central postnatal age (a stated central value, else the arithmetic midpoint of the range), or the central PMA when no postnatal age is stated. A group at PMA 38 weeks and 21 days still caps to 35 weeks and is preterm. Amendment 9 §3 applies unchanged with this cap.
2. **Consistency check scope.** The 20–45-week test of Amendment 8 §2 runs only when both PMA and postnatal age are stated. The stated-GA test of Amendment 9 §2 also runs with PMA alone, taking the postnatal age as 0.
3. **Amendment 9 §5 corrected.** The stated limitation applies to a group described neither as preterm nor by GA whose central PMA minus central postnatal age is 37 weeks or more. Such a group is treated as term even if some of its members were born preterm.

### Amendment 11 — 2026-11-27, at the same point as Amendment 5 (nothing more seen), before any abstract was screened or any value was extracted

This answers an eighth code review and corrects Amendment 10. These rules override the text above where the two conflict.

1. **Default GA cap, corrected again.** Amendment 10 §1 subtracted the central postnatal age, which brought back the failure that Amendment 8 §1 withdrew: a term group at PMA 40 weeks with postnatal age 1–121 days capped to 31 weeks and was filed as preterm. The cap is now the central PMA minus the *smallest* stated postnatal age (the lower bound of a stated range, else the stated value), or the central PMA when no postnatal age is stated. A member at the central PMA was born no later than that. So the PMA-40 group caps at 39.9 weeks and stays term; a group at PMA 38 weeks with a postnatal age of 21 days caps at 35 weeks and is preterm; a PMA-only group at a central PMA of 34 weeks (range 28–40) caps at 34 weeks. Amendment 9 §3 applies unchanged with this cap. The stated limitation of Amendment 10 §3 now reads: a group described neither as preterm nor by GA whose central PMA minus smallest postnatal age is 37 weeks or more is treated as term.
2. **Range without a central field.** A range-only age goes in the main field (`pna_days`, `ga_weeks` or `pma_weeks`). A record that fills `pna_range_days`, `ga_range_weeks` or `pma_range_weeks` but leaves its main field null is reported as a recording error.
3. **The tools are frozen for screening.** After this amendment the screening and extraction code changes only for an error found while screening. Each such change is a dated amendment that says which records it affects.
4. **Restoring the abstracts** (added in the review follow-up, same point). The abstract texts are gitignored, so a fresh checkout re-fetches them with `python3 -m benchmark.external.curation.search restore`, which stops on any PMID whose text no longer matches its committed SHA-256. On 2026-11-27 all 1,440 distinct texts matched. The screening queue shows an abstract only after the same hash check. Re-running the searches needs the explicit `snapshot` subcommand. The freeze in §3 covers these tools too.

### Amendment 12 — 2026-11-27, while both screening passes were running and before either pass's records had been read, any agreement was computed or any prediction was made

The scoring code (`score.py`), the agreement code (`curation/agreement.py`) and the author lookup for E7 were written at this point. This amendment fixes the details the text above leaves open. These rules override the text above where the two conflict.

1. **Count in Amendment 11 §4.** "1,440 distinct texts" should read 1,440 drug–PMID pairs (1,252 distinct PMIDs). All matched.
2. **Prediction grid.** When a PMA is stated, the grid is in PMA: 7 log-spaced points across a stated PMA range, else the central PMA. Each point's postnatal age for weight imputation is (PMA − GA) × 7 days, floored at 0. Otherwise the grid is in postnatal age as in Amendment 2 §7. A stated weight (its arithmetic midpoint for a range) is used at every point; otherwise each point takes the growth-table weight at its own age.
3. **Observed clearance.** Per-kg, per-70 kg and Costeff-BSA conversions use the stated weight, else the growth-table weight at the central postnatal age and GA (`weight_imputed`). Mosteller BSA needs a stated height and a stated weight.
4. **PaedScale prediction.** `compute_pediatric_dose` with the adult reference clearance, fe and the enzyme from `../reference_set.json`, the point's weight and PMA, and the clearance-matched metric. As in the label benchmark, clearance not attributed to a pathway is scaled by allometry alone. The exploratory interval coverage uses one point per observation (central age and weight) and 1,000 draws with the engine's default seed.
5. **Under 2 years** means a central postnatal age below 24 months (730.5 days).
6. **Adult reference.** A weight range is used at its midpoint. A drug with no qualifying adult abstract is excluded (protocol body).
7. **Statistics.** Each observation is paired with itself across methods. The sign-flip test is two-sided: the share of the 2^k sign assignments of the drug-level differences whose absolute sum is at least the observed one. HE2 is always reported, and it is marked as tested only when HE1 succeeds. Per-stratum comparisons and intervals are reported only for strata with at least 5 drugs; smaller strata get the per-drug differences without an interval.
8. **E7 author match.** An author matches when the PubMed "LastName Initials" equals Anderson BJ, Holford NH or NHG, Rhodin MM, Anand KJ or KJS, or Larsson P.
9. **Adjudication.** The final record follows the seeded order. A decision both passes agree on is kept. A disagreement, and any abstract only one pass read, is decided by the adjudicator re-reading the abstract against the protocol. An abstract neither pass read but that the final queue opens is screened by the adjudicator. Each adjudicated decision and value is recorded in `extraction/adjudication.json` with its reason. The final record must pass `curation/check.py`.

### Amendment 13 — 2026-11-27, during the first screening pass, before any agreement was computed or any prediction was made

An error in the record checker was found while screening (Amendment 11 §3).

1. **Number matching.** The check that each recorded number appears in its quote compared text forms and missed trailing zeros: a clearance printed "0.0340" and recorded as 0.034 was reported as absent. Numbers in a quote are now compared numerically. This also removes a leniency of the old check, which accepted a value that rounded to a printed number (5.12 against "5.1"). The pass-1 records finished at this point (amikacin, cefoxitin, daptomycin, famotidine, gentamicin, meropenem, penicillin G) were re-checked and pass. No decision or value changed.
2. **Weight in grams.** A screener found a neonatal weight stated only in grams ("1086 +/- 311 g"). The guide asks for kilograms, and the checker required the kilogram number in the quote, so the weight was left null and would have been imputed. A weight in kilograms whose value × 1000 appears in a quote stated in grams is now accepted ("g", "gm" or "gram"). A weight left null for this reason in a record already finished is filled in at adjudication.

### Amendment 14 — 2026-11-28, after the first screening pass finished and its screeners' reports were read, while the second pass was running and before any of its records were read, any agreement was computed or any prediction was made

The pass-1 reports showed the same few questions decided differently from drug to drug. These rules settle them for adjudication. They apply to both passes' records at adjudication; κ is computed on the passes as recorded. These rules override the text above where the two conflict. Because they were set after pass-1 decisions were known, every effect they have on the dataset is listed in `extraction/adjudication.json`.

1. **Route not stated.** An abstract that reports a clearance that is not CL/F, and mentions no oral, intramuscular or other non-intravenous dosing, counts as intravenous, flagged `route_unstated` (pediatric or adult). A clearance study without a stated route is almost always intravenous, and P1's purpose is to exclude CL/F. New sensitivity analysis **E9** excludes `route_unstated` pediatric observations and recomputes the adult reference without `route_unstated` adult abstracts.
2. **Cardiopulmonary bypass** is extracorporeal support. A population restricted to bypass surgery is excluded under P4.
3. **Single-patient reports** are not a group summary or a population typical value. They are excluded under P2.
4. **Typical value at the cohort's central covariates.** A population typical value whose abstract states the cohort's central age (and weight, if any) but no separate covariate point is accepted at that central age and weight, flagged `typical_at_cohort_median`. The group summary still takes precedence (Amendment 1 §5).
5. **Birth weight.** A stated birth weight is the group's weight only for a group whose central postnatal age is under 28 days, flagged `birth_weight`. Otherwise the weight is left null and imputed.
6. **Open-ended bounds.** A postnatal age stated only as an upper bound ("less than 4 weeks") is the range [0, bound]. A GA or PMA stated only as one bound ("≥ 32 weeks") is not recorded. An age in words is read by fixed rules: "first day of life" [0, 1] day, "first week of life" [1, 7] days.
7. **Reviews, and values cited from other studies,** are not data from the abstract's own study and are excluded.
8. **Adult patients** who are not healthy volunteers need a stated age within 18–65 years and stated normal renal function (Amendment 1 §2). Other co-medication than probenecid does not exclude an adult or pediatric study.

### Amendment 15 — 2026-11-28, after both passes finished and during adjudication, before any prediction was made

This answers a code review of the scorer, the agreement code and Amendments 12–14, and records rules the adjudicator needed. These rules override the text above where the two conflict.

1. **Per kg over absolute.** When an abstract gives the same group's clearance both per kg and as an absolute value, the per-kg value is used. With an imputed weight, the fold error of a per-kg observation depends on weight only to the power −0.25 (observed and predicted both scale with weight), against 0.75 for an absolute one.
2. **Repeated conditions in the same subjects.** When an abstract reports the same subjects under a usual and an experimental condition (a crossover, or before and after an interacting drug), the usual-condition value is used.
3. **Ages from a stated schedule.** An age that follows arithmetically from a stated start and dosing schedule ("from the first day of life, every 72 hours", after the third dose) is accepted.
4. **Grams.** Amendment 13 §2's rule now needs the gram unit on that number ("912 gm", "1086 ± 311 g"), and not a per-volume unit such as g/dL. Pass records were re-checked and pass.
5. **Scoring.** HE2 is confirmatory only when HE1 is (Amendment 1 §8 counts drugs under 2 years). E7 and E8 stop with an error when an author list or a publication year is missing, rather than silently keeping or dropping the study. E9 also drops an adult abstract whose value, not only the study, carries `route_unstated`. The per-stratum comparisons now include weight-linear and BSA, as the protocol body asks. The E7 match is exact.
6. **Agreement.** Besides the per-abstract comparison, extracted numbers are counted one by one (each clearance and each recorded age, weight, BSA or height), as Amendment 1 §9 asks, for abstracts both passes included with the same number of observations.
7. **What was seen, corrected.** Amendment 13 §1's re-check of finished pass-1 records was by script (pass or fail only). The pass-2 screeners started after Amendments 13 and 14 were committed, and one of them applied Amendment 14 while screening; this is a deviation from strict blinding to adjudication rules, and it can only raise agreement on the Amendment 14 questions.

### Amendment 16 — 2026-11-28, after adjudication finished and the final record was built, before any prediction was made

By this point both passes' records, the agreement output and, during adjudication, the abstracts had been read. No prediction or score had been computed. This answers a code review of the adjudication and agreement code and records what changed after the passes were seen. These rules override the text above where the two conflict.

1. **Adjudication log.** Every log entry needs a reason, and a logged record must carry the PMID it is filed under; otherwise the item stays unresolved. `extraction/final/` is written only when nothing is unresolved, and the adjudication run then checks it with `curation/check.py`.
2. **Agreement changes made after the records were seen.** Commit 430e7a8, made after a first agreement output had been read, compares numbers as numbers (30 equals 30.0) and applies a study-level flag to each of its items, so that the same extraction recorded in two equivalent forms is not counted as a disagreement. It raised the per-abstract value agreement from 76 to 80 of the 97 abstracts both passes included. The value-by-value counting of Amendment 15 §6 was also added after the pass-2 records had been read. Neither change touches the inclusion decisions or κ. At this amendment the items are also paired in sorted order rather than in recorded order, and a clearance's unit is compared with its value.
3. **Grams.** The Amendment 13 §2 rule also accepts a spread in brackets ("1086 (311) g") and a thousands comma ("1,086 g"). The rule only accepts more quotes, so no pass record that passed the checker can now fail.
4. **Results of agreement and adjudication.** κ is 0.960 over the 773 abstracts both passes read (7 decision disagreements). Of the 97 abstracts both included, 80 have identical extracted values; 23 of the 259 numbers compared one by one differ. The final record has 55 adjudication entries, each with its reason in `extraction/adjudication.json`. They cover all disagreements and single-pass abstracts, and these effects of Amendments 14 and 15 on decisions both passes had agreed on:
   * `route_unstated` added to 22 included pediatric studies and 4 adult abstracts whose abstracts name no route;
   * four pediatric studies and one adult abstract included under Amendment 14 §1 that both passes had excluded for an unstated route (fluconazole 18809946 and 35074829, levetiracetam 34753796, zidovudine 9559787; tobramycin adult 3606064), and one kept excluded for another reason (tobramycin 3964533, unreadable age);
   * two single-patient reports excluded under Amendment 14 §3 (meropenem 25884534, 30300440);
   * one per-kg value used under Amendment 15 §1 (vancomycin 2630235).
5. **"At birth."** A typical value stated "at birth" is recorded at a postnatal age of 0 days, so its PMA is its GA. The 1-day floor of Amendment 2 §7 applies only to the lower bound of a range.
6. **Frozen dataset.** The final record, the adjudication log, the agreement output (`dataset/agreement.json`) and the author lists for E7 (`dataset/authors.json`) are committed before any prediction is made.

### Amendment 17 — 2026-11-28, after scoring (the outputs of commit 5f45c11 had been read)

This answers a second code review of the adjudication and agreement code. Nothing here changes the final record, the agreement output or any scored number: the final record was rebuilt and is identical, `dataset/agreement.json` was recomputed and is identical, and `results.json` was regenerated and is identical apart from its provenance.

1. **Amendment 16 §3 corrected.** It said the grams rule only accepted more quotes. Its rewrite had in fact dropped the form "1086 (SD) 311 g". That form is accepted again. No record contains it.
2. **Adjudication.** A log entry that the final queue never reaches (a misspelt PMID, or one past the stop) is now reported as unresolved, as is a log entry for a drug no pass covers. A `use` entry that names a pass which did not read the abstract no longer stops the listing of later items. A failed run now removes `extraction/final/`, so no record from an earlier run can be scored.
3. **Agreement.** Items are paired for the value-by-value count in an order that sorts on the covariates first, and numbers as numbers, so one differing clearance cannot misalign the other pairs. A difference in the clearance's summary statistic (mean against median) makes the abstract a value disagreement but is not counted as a differing number, because it is not a number (Amendment 1 §9).
4. **Amendment 16 §5** changed one record: fluconazole 18809946.
5. **Figures and the observation table.** Two figures of the external validation (fold error by age; per-drug paired difference) and a column with each observation's central postnatal age in `output/observations.csv` were added after scoring. They present the scored numbers and change none.

### Amendment 18 — 2026-11-28, after scoring (the outputs of commit 3b5ca61 had been read)

A third code review found two statements in Amendment 17 that were too strong. The code now does what they say. The final record and `dataset/agreement.json` were recomputed and are identical; no scored number changes.

1. **Amendment 17 §3.** Items with the same covariates were ordered by clearance value before their flags, summary statistic and unit, so one differing clearance could still misalign two such items. They are now ordered by covariates, then flags, summary statistic and unit, and the clearance value last. A differing covariate (an age or weight) can still change the pairing; the per-abstract comparison, which does not pair items, is unaffected.
2. **Amendment 17 §2.** A run that stopped on an exception (a malformed pass record, a missing snapshot) left the earlier `extraction/final/` in place. The folder is now emptied when a run starts and again if it fails in any way. An empty log entry is now reported as having no reason rather than ignored.
3. **Smaller fixes.** The "(SD)" grams form is matched without regard to case. The per-drug figure is skipped, rather than failing after the outputs are written, when no comparison could be made. The age figure's axis label says that groups at birth are plotted at 1 day and that methods are offset slightly.

### Amendment 19 — 2026-11-28, after scoring of the primary dataset (the outputs of commit 3b5ca61 had been read); before any extension label was fetched, any extension search was run or any extension abstract was read

This pre-registers an **extension set** of drugs. It changes nothing in the primary analysis: the frozen dataset (Amendment 16), HE1, HE2, the secondary and sensitivity analyses and `output/results.json` stay as committed, and they remain the validation's primary result.

1. **Why.** Five of the 20 drugs had no qualifying adult abstract, so 15 drugs were scored and 11 contributed observations under 2 years, three above the 8-drug threshold of Amendment 1 §8. The scored drugs are mostly renally cleared: clindamycin is the only CYP3A4 drug, and zidovudine, the only UGT2B7 drug, dropped out. The extension tests the same question on drugs that were not part of the primary dataset.
2. **Candidates (12).** They were chosen by the authors before any extension search, not by a systematic search; as in the label benchmark, selection bias is a stated limitation.
   * The three label-benchmark candidates excluded there only because their labels lack machine-readable dosing text (label benchmark E1/E2), which does not bear on clearance: **cefazolin, digoxin, fentanyl**.
   * Nine IV drugs widely studied in children, chosen to add non-renal and mixed elimination: **alfentanil** and **sufentanil** (hepatic, CYP3A4); **ganciclovir, cefotaxime, levofloxacin** and **milrinone** (mainly renal); **ceftriaxone, linezolid** and **metronidazole** (renal plus other routes).
   * Morphine and midazolam stay excluded as maturation-curve source drugs.
3. **Engine inputs, fixed before any extension search.**
   * **Label.** One FDA label per drug, selected by the label benchmark's rule (`../curation/fetch_labels.py`: openFDA, an intravenous route, exactly the drug's active ingredient, a pediatric mention in Dosage and Administration preferred, then the latest effective time, the highest SPL version and the highest set id). Cefazolin, digoxin and fentanyl keep their committed snapshots in `../labels/`; the other nine are written to `extension/labels/`.
   * **fe and enzyme** follow the label benchmark's model-input rules (`../PROTOCOL.md`, "Model inputs" and its Amendment 1 §8–9): fe is the label's fraction excreted unchanged in urine from the longest collection, a range at its midpoint, a qualitative statement 0.90 flagged `fe_qualitative`; `fm[enzyme] = 1 − fe` only when the label, or literature cited in the extension set file before any search, names CYP3A4 or UGT2B7 as the principal non-renal route; otherwise the non-renal fraction is unattributed and scaled by size only; an enzyme named without an fe gives fe = 0, flagged `fe_not_in_label`. Every value carries a verbatim label quote, checked by test.
   * **Eligibility.** The label benchmark's E3 (elimination maps onto the engine's curves: a quantitative fe, or CYP3A4 or UGT2B7 named as principal route) and E4 (linear clearance). E4 fails when the label's clinical pharmacology or pharmacokinetics text says that the drug's pharmacokinetics or clearance are nonlinear or dose-dependent. A failing candidate is excluded, with its criterion and quote, before any extension search. E1 and E2 do not apply: this validation does not use doses.
   * The engine is the one committed at this amendment. A maturation curve added to the engine later does not change the extension's predictions.
4. **Search, screening, extraction and adjudication** follow this protocol as it stands (the body and Amendments 1–18) with no change of rule, seed or query form. The search term is the drug name; cefazolin is `(cefazolin[tiab] OR cephazolin[tiab])`. Both passes see Amendments 13–16 from the start, so the blinding departure of Amendment 15 §7 does not recur. Two blinded AI-assisted passes run in fresh contexts, each with only this protocol, `SCREENING_GUIDE.md` and the abstracts; κ, the value-by-value comparison and logged adjudication are as in Amendments 1 §9, 12 §9, 15 §6 and 16. The extension's search snapshot, records, adjudication log, agreement output and author lists live in a separate tree, `extension/`, so the primary record cannot change. The extension dataset is frozen and committed before any extension prediction is computed.
5. **Analysis, fixed now.** It uses `score.py` unchanged in its statistics, with the extension's dataset and engine inputs.
   * **XE1** (key extension endpoint): HE1 on the extension drugs alone. PaedScale against allometry, drug-weighted mean |log10 FE| under 2 years, 95% BCa cluster-bootstrap interval (10,000 replicates, seed 20261127), success when the upper bound is below zero. It is confirmatory only if at least 8 extension drugs contribute observations under 2 years; otherwise it is descriptive.
   * **XE2:** the same for all ages, tested only if XE1 succeeds.
   * **PE1, PE2** (pooled): the same on the primary and extension drugs together. They are descriptive, because the primary part had already been scored when this amendment was written.
   * The secondary endpoints, per-stratum results and sensitivity analyses E1–E9 are computed for the extension and the pooled set as for the primary set, and written to `output/extension/` and `output/pooled/`.
   * The manuscript reports the primary analysis as primary and the extension as a pre-registered secondary validation.
