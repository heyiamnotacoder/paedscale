"""Graded renal and hepatic function modifiers.

The MVP used a single fixed 0.5 multiplier for "impairment". Real dosing turns
on *how much* function is lost. These functions convert bedside covariates
(serum creatinine + height for renal; Child-Pugh for hepatic) into a per-organ
clearance modifier in (0, 1] that scales the relevant elimination pathways,
*on top of* the age-normal maturation the Anderson-Holford curves already encode.

The modifiers capture pathology relative to a normally-functioning child of the
same maturity — impairment only ever reduces clearance here, so each is capped
at 1.0.
"""

# Bedside Schwartz constant (2009 revision, enzymatic creatinine).
BEDSIDE_SCHWARTZ_K = 0.413
# eGFR (mL/min/1.73m^2) taken as "normal" reference for a matured kidney.
REFERENCE_EGFR = 100.0
# Floor so a modifier never collapses clearance to zero (anuria is a clinical
# stop, not a dosing calculation).
MIN_MODIFIER = 0.05


def schwartz_egfr(height_cm: float, serum_creatinine_mg_dl: float, k: float = BEDSIDE_SCHWARTZ_K) -> float:
    """Bedside Schwartz eGFR (mL/min/1.73m^2) = k · height(cm) / SCr(mg/dL)."""
    if serum_creatinine_mg_dl <= 0 or height_cm <= 0:
        raise ValueError("height_cm and serum_creatinine_mg_dl must be positive")
    return k * height_cm / serum_creatinine_mg_dl


def renal_function_modifier(egfr_ml_min_1_73: float, reference_egfr: float = REFERENCE_EGFR) -> float:
    """Renal clearance modifier from an (e)GFR / CrCl, clamped to (MIN_MODIFIER, 1]."""
    ratio = egfr_ml_min_1_73 / reference_egfr
    return max(MIN_MODIFIER, min(ratio, 1.0))


def child_pugh_class(score: int) -> str:
    """Child-Pugh class from the 5-15 composite score: A (5-6), B (7-9), C (10-15)."""
    if score <= 6:
        return "A"
    if score <= 9:
        return "B"
    return "C"


# Class-level hepatic clearance retention. Drug-specific in reality; these are
# defensible population defaults for a starting estimate (Child-Pugh A ≈ near
# normal, B ≈ moderate reduction, C ≈ marked reduction). The agent may override.
_CHILD_PUGH_MODIFIER = {"A": 0.9, "B": 0.6, "C": 0.4}


def hepatic_function_modifier(child_pugh_score: int) -> float:
    """Hepatic clearance modifier from a Child-Pugh score (default per class)."""
    return _CHILD_PUGH_MODIFIER[child_pugh_class(child_pugh_score)]


def organ_modifiers(
    egfr_ml_min_1_73: float | None = None,
    child_pugh_score: int | None = None,
) -> dict[str, float]:
    """Build the {organ: modifier} map consumed by `effective_clearance_fraction`.

    Only organs with a supplied covariate are included; absent organs default to
    1.0 (no impairment) at the point of use.
    """
    mods: dict[str, float] = {}
    if egfr_ml_min_1_73 is not None:
        mods["renal"] = renal_function_modifier(egfr_ml_min_1_73)
    if child_pugh_score is not None:
        mods["hepatic"] = hepatic_function_modifier(child_pugh_score)
    return mods
