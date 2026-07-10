"""Case intake: turn a free-text clinical query into structured covariates.

The orchestrator does the parsing itself (it is the first thing it reasons about),
so this module supplies the shared covariate spec and the intake instructions
rather than a separate model call. Keeping them here keeps the orchestrator
prompt readable and the covariate contract in one place.
"""

COVARIATE_SPEC = """\
Essential covariates to extract (leave unknown ones null and record them in
`assumed_defaults` with the population value you assumed):
  - drug_name, indication, route (default the drug's usual pediatric route)
  - weight_kg
  - height_cm / length (needed for Schwartz eGFR)
  - sex
  - gestational_age_weeks (birth GA) and postnatal_age_weeks (age since birth)
  - pma_weeks = gestational_age_weeks + postnatal_age_weeks  (if only a plain age
    is given for a non-neonate, treat gestational age as 40 wk term unless stated)
  - serum_creatinine_mg_dl and/or egfr_ml_min_1_73 (renal function)
  - child_pugh_score (hepatic function; map a described impairment to 5-15)
  - albumin_g_dl (protein binding)
"""

INTAKE_INSTRUCTIONS = """\
Step 1 — INTAKE. Parse the query into covariates. Convert ages to weeks and
compute PMA. "2 days old" ≈ 0.3 postnatal weeks; a term neonate is 40 wk GA
unless a gestational age is stated. Note every covariate you had to assume a
default for — these downgrade the evidence grade and widen the safety margin.
Never block on a missing covariate: assume an age-typical population default,
flag it, and proceed.
"""


def merge_overrides(covariates: dict, overrides: dict | None) -> dict:
    """Structured overrides from the request win over the parsed covariates."""
    if not overrides:
        return covariates
    merged = dict(covariates)
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged
