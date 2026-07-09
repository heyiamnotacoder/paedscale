"""Solve the pediatric dose/interval that reproduces the adult exposure target.

The target is exposure-matching, not weight-matching: choose the dose so
that the child's AUC over one dosing interval equals the adult reference
AUC over its own interval. This is the standard "same drug, same target
exposure, different clearance" translation used in model-informed pediatric
dosing.

    AUC_tau = Dose / CL   (linear PK, one-compartment approximation)

    Dose_child = Dose_adult_reference * (CL_child / CL_adult_reference) * (tau_child / tau_adult_reference)
"""

from dataclasses import dataclass


@dataclass
class DoseRecommendation:
    dose_mg: float
    dose_mg_per_kg: float
    interval_h: float
    child_clearance_l_per_h: float
    child_volume_l: float


def solve_dose(
    adult_reference_dose_mg: float,
    adult_clearance_l_per_h: float,
    adult_interval_h: float,
    child_clearance_l_per_h: float,
    child_volume_l: float,
    weight_kg: float,
    child_interval_h: float | None = None,
) -> DoseRecommendation:
    """Return the pediatric dose (and mg/kg) that matches adult exposure per interval."""
    tau_child = child_interval_h if child_interval_h is not None else adult_interval_h
    exposure_ratio = child_clearance_l_per_h / adult_clearance_l_per_h
    interval_ratio = tau_child / adult_interval_h
    dose_mg = adult_reference_dose_mg * exposure_ratio * interval_ratio
    return DoseRecommendation(
        dose_mg=dose_mg,
        dose_mg_per_kg=dose_mg / weight_kg,
        interval_h=tau_child,
        child_clearance_l_per_h=child_clearance_l_per_h,
        child_volume_l=child_volume_l,
    )
