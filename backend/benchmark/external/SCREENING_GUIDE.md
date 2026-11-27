# Screening and extraction guide (operational)

This guide says *how* to record screening decisions. The rules themselves are in `PROTOCOL.md`, Amendments 1 to 3. Where the two differ, PROTOCOL.md wins. Each pass works only from PROTOCOL.md, this guide and the abstract texts. A pass never opens another pass's folder.

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
    {"label": "preterm, PMA 24-34 wk",
     "cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "clearance was 0.05 L/h/kg"},
     "pna_days": [1, 27], "ga_weeks": null, "pma_weeks": [24, 34],
     "age_quote": "PMA 30.4 weeks, range 24-34 weeks; postnatal age 11.9 days, range 1-27 days",
     "weight_kg": 1.3, "weight_quote": "weight 1.30 kg",
     "bsa_m2": null, "height_cm": null, "flags": []}]},
  {"pmid": "456", "decision": "exclude", "reason": "P4: ECMO", "flags": [], "observations": []}],
 "adult": [
  {"pmid": "789", "decision": "include", "reason": "", "flags": [],
   "values": [{"cl": {"value": 5.1, "unit": "L/h", "summary": "mean", "quote": "..."},
               "weight_kg": 72, "weight_quote": "...", "age_quote": "...", "flags": []}]}]}
```

- **decision** is `include` or `exclude`. An exclusion's `reason` starts with the criterion (P1–P4, or "not total IV CL", "range only", "CL/F", "probenecid", "adult criteria", "no age") and a few words.
- **Ages.** Postnatal age is in days and GA and PMA are in weeks. Each is a number (central value) or a `[low, high]` range, or null. When both a central value and a range are reported, give the central value. Convert with year = 365.25 d, month = 30.4375 d, week = 7 d. `age_quote` holds the text as reported.
- **Units.** Use exactly one of: `L/h`, `mL/min`, `L/h/kg`, `mL/min/kg`, `mL/h/kg`, `L/h/70kg`, `mL/min/1.73m2`, `L/h/1.73m2`, `mL/min/m2`, `L/h/m2`, `L/day`. "l h-1 kg-1" is `L/h/kg`, "mL/kg/min" is `mL/min/kg`, "L/h per 70 kg" is `L/h/70kg`, and "ml/min per m(2)" (per square metre, not per 1.73 m²) is `mL/min/m2`. Record a stated BSA in `bsa_m2` and a stated height in `height_cm`.
- **summary** is `mean`, `median`, `geometric_mean` or `typical` (a population model's typical value).
- **Quotes** are copied exactly from the printed abstract text. Each number must appear inside its own quote.
- **Adult values** need no age range. Give `age_quote` when the abstract states an age; otherwise leave it null and flag `adult_age_unstated` (healthy volunteers only, Amendment 2 §5).
- **Flags** are from PROTOCOL.md: `critically_ill`, `weight_imputed` (leave weight null instead; the scorer adds this flag), `ga_imputed`, `allometric_standardized`, `fixed_maturation`, `fixed_allometry`, `with_tazobactam`, `pca_as_pma`, `adult_weight_missing`, `adult_age_unstated`.
- **Observations.** Record one per age group or covariate point the abstract reports. When an abstract gives both a group summary and a model typical value for the same group, record only the group summary.
- **Stop rule.** Stop when `next` prints "NOTHING OPEN".
