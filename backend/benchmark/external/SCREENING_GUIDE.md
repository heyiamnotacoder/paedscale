# Screening and extraction guide (operational)

This guide says *how* to record screening decisions. The rules themselves are in `PROTOCOL.md`, Amendments 1 to 7. Where the two differ, PROTOCOL.md wins. Each pass works only from PROTOCOL.md, this guide and the abstract texts. A pass never opens another pass's folder.

## Commands (from `backend/`)

```bash
python3 -m benchmark.external.curation.screening next <pass> <drug> 3   # next abstracts in the seeded order
python3 -m benchmark.external.curation.check <pass> [<drug>]            # validate a pass's records
```

`next` prints pediatric abstracts while any stratum is open. Once every stratum is full, or the list is exhausted, it prints adult abstracts until five qualify or the list is exhausted. Screen strictly in the printed order, and record a decision for every abstract you read before asking for more.

## Record file: `extraction/<pass>/<drug>.json`

```json
{"drug": "vancomycin", "pass": "pass1",
 "pediatric": [
  {"pmid": "123", "decision": "include", "reason": "", "flags": ["critically_ill"],
   "observations": [
    {"label": "preterm, PMA 24-34 wk", "preterm": true,
     "cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "clearance was 0.05 L/h/kg"},
     "pna_days": 11.9, "pna_range_days": [1, 27], "ga_weeks": null, "pma_weeks": 30.4, "pma_range_weeks": [24, 34],
     "age_quote": "PMA 30.4 weeks, range 24-34 weeks; postnatal age 11.9 days, range 1-27 days",
     "weight_kg": 1.3, "weight_quote": "weight 1.30 kg",
     "bsa_m2": null, "bsa_quote": null, "height_cm": null, "height_quote": null, "flags": []}]},
  {"pmid": "456", "decision": "exclude", "reason": "P4: ECMO", "flags": [], "observations": []}],
 "adult": [
  {"pmid": "789", "decision": "include", "reason": "", "flags": [],
   "values": [{"cl": {"value": 5.1, "unit": "L/h", "summary": "mean", "quote": "..."},
               "weight_kg": 72, "weight_quote": "...", "age_years": [18, 45], "age_quote": "...",
               "flags": []}]}]}
```

- **decision** is `include` or `exclude`. An exclusion's `reason` starts with the criterion (P1–P4, or "not total IV CL", "range only", "CL/F", "probenecid", "adult criteria", "no age") and a few words.
- **Ages.** Postnatal age (`pna_days`) is in days; GA (`ga_weeks`) and PMA (`pma_weeks`) are in weeks. Each is a number (the stated central value), a `[low, high]` range when only a range is stated, or null. When both a central value and a range are stated, put the central value in the field and the range in `pna_range_days`, `ga_range_weeks` or `pma_range_weeks`. Convert with year = 365.25 d, month = 30.4375 d, week = 7 d. `age_quote` holds the text as reported.
  - A group needs a postnatal age or a PMA. GA alone does not say when clearance was measured: exclude with "no age" (Amendment 4 §3).
  - "Conceptional" or "postconceptional" age goes in `pma_weeks`, flagged `pca_as_pma`.
  - Every pediatric observation has `"preterm"`: true when the abstract describes the group as preterm or premature, even without a numeric GA; otherwise false. The scorer uses it to impute GA.
  - When both PMA and postnatal age are given, they must imply a GA of 20–45 weeks; otherwise re-read the abstract, because one of them is recorded wrongly.
- **Units.** Use exactly one of: `L/h`, `mL/min`, `mL/h`, `L/min`, `L/day`, `L/h/kg`, `mL/min/kg`, `mL/h/kg`, `L/day/kg`, `L/h/70kg`, `mL/min/1.73m2`, `L/h/1.73m2`, `mL/h/1.73m2`, `mL/min/m2`, `L/h/m2`. A value in any other unit is excluded with "not total IV CL: unit". "l h-1 kg-1" is `L/h/kg`, "mL/kg/min" is `mL/min/kg`, "L/h per 70 kg" is `L/h/70kg`, and "ml/min per m(2)" (per square metre, not per 1.73 m²) is `mL/min/m2`. Record a stated BSA in `bsa_m2` with `bsa_quote`, and a stated height in `height_cm` with `height_quote`.
- **Weight** is a number (the stated mean or median) or a `[low, high]` range when only a range is stated, with `weight_quote`. Leave it null when no weight is stated.
- **Per-70 kg values** (`L/h/70kg`) need the `allometric_standardized` flag and the age the typical value applies at: a PMA, a postnatal age with GA, or a postnatal age whose whole stated range is 2 years or older (Amendment 1 §3, Amendment 6 §2). Otherwise exclude with "not total IV CL: per 70 kg without age".
- **summary** is `mean`, `median`, `geometric_mean` or `typical` (a population model's typical value).
- **Quotes** are copied exactly from the printed abstract text. Each number must appear inside its own quote.
- **Adults** qualify when aged 18–65 years (or healthy volunteers with no stated age), healthy or with normal renal function, given the drug IV without probenecid (Amendment 1 §2). Record the stated age in years in `age_years` (a number or `[low, high]`, every number within 18–65) with `age_quote`; with no stated age leave both null and flag `adult_age_unstated`. An adult value must be absolute or per kg (`L/h`, `mL/min`, `mL/h`, `L/min`, `L/day`, or a per-kg unit); exclude an adult abstract that gives only per-BSA or per-70 kg values with "adult criteria: unit". An absolute clearance (L/h, mL/min, mL/h, L/min, L/day) with no stated weight is flagged `adult_weight_missing`.
- **Flags** you record are, for pediatric studies, `critically_ill`, `allometric_standardized`, `fixed_maturation`, `fixed_allometry`, `with_tazobactam` and `pca_as_pma`; for adult abstracts, `with_tazobactam`, `adult_weight_missing` and `adult_age_unstated` (definitions in PROTOCOL.md). A study-level flag applies to all its observations, an observation-level flag to that one only. The scorer adds `weight_imputed`, `ga_imputed` and `bsa_costeff` itself, so leave the weight, GA or BSA null instead of guessing.
- **Observations.** Record one per age group or covariate point the abstract reports. When an abstract gives both a group summary and a model typical value for the same group, record only the group summary.
- **Stop rule.** Stop when `next` prints "NOTHING OPEN".
