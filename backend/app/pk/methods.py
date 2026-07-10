"""Multi-method dose engine.

AUC exposure-matching is only one way to translate a dose across populations —
and it is the wrong one for many drugs. The metric that drives a drug's effect
determines the method:

  - auc        total exposure drives effect (e.g. many time-dependent antibiotics,
               MMF); reproduce the adult AUC over a dosing interval. Needs an
               adult reference dose + clearance.
  - css        maintenance to a target steady-state average concentration
               (infusions, chronic dosing). Dose_rate = Css · CL.
  - cmax       concentration-dependent effect / peak targets (aminoglycosides).
               Dose = Cmax · Vd (one-compartment IV bolus).
  - trough     target trough at end of interval (e.g. some TDM-guided agents).
  - loading    fill the volume to a target concentration. LD = Vd · C_target.
  - mgkg_linear  naive weight scaling — always computed as the contrast baseline.

The orchestrator picks the method after retrieving the drug's PK/PD driver; this
module only does the arithmetic. Concentrations are mg/L, volumes L, clearance
L/h, doses mg.
"""

import math
from dataclasses import dataclass, field

METHODS = ("auc", "css", "cmax", "trough", "loading", "mgkg_linear")


@dataclass
class DoseResult:
    dose_mg: float
    dose_mg_per_kg: float
    method: str
    matched_metric: str
    interval_h: float | None = None
    detail: dict = field(default_factory=dict)


def _result(dose_mg, weight_kg, method, metric, interval_h=None, **detail) -> DoseResult:
    return DoseResult(
        dose_mg=dose_mg,
        dose_mg_per_kg=dose_mg / weight_kg,
        method=method,
        matched_metric=metric,
        interval_h=interval_h,
        detail=detail,
    )


def solve_auc(
    adult_reference_dose_mg: float,
    adult_clearance_l_per_h: float,
    adult_interval_h: float,
    child_clearance_l_per_h: float,
    weight_kg: float,
    child_interval_h: float | None = None,
) -> DoseResult:
    """Reproduce the adult AUC per interval: Dose_child = Dose_adult·(CL_c/CL_a)·(τ_c/τ_a)."""
    tau_child = child_interval_h if child_interval_h is not None else adult_interval_h
    dose = (
        adult_reference_dose_mg
        * (child_clearance_l_per_h / adult_clearance_l_per_h)
        * (tau_child / adult_interval_h)
    )
    return _result(
        dose,
        weight_kg,
        "auc",
        "AUC over dosing interval (steady state)",
        interval_h=tau_child,
        child_clearance_l_per_h=child_clearance_l_per_h,
    )


def solve_css(
    css_target_mg_per_l: float,
    child_clearance_l_per_h: float,
    interval_h: float,
    weight_kg: float,
) -> DoseResult:
    """Maintenance dose for a target steady-state average conc: Dose = Css·CL·τ."""
    dose = css_target_mg_per_l * child_clearance_l_per_h * interval_h
    return _result(
        dose,
        weight_kg,
        "css",
        "steady-state average concentration",
        interval_h=interval_h,
        css_target_mg_per_l=css_target_mg_per_l,
    )


def solve_cmax(
    cmax_target_mg_per_l: float,
    child_volume_l: float,
    weight_kg: float,
    interval_h: float | None = None,
) -> DoseResult:
    """Peak-target dose (one-compartment IV bolus): Dose = Cmax·Vd."""
    dose = cmax_target_mg_per_l * child_volume_l
    return _result(
        dose,
        weight_kg,
        "cmax",
        "peak concentration (one-compartment IV bolus)",
        interval_h=interval_h,
        cmax_target_mg_per_l=cmax_target_mg_per_l,
        child_volume_l=child_volume_l,
    )


def solve_trough(
    ctrough_target_mg_per_l: float,
    child_clearance_l_per_h: float,
    child_volume_l: float,
    interval_h: float,
    weight_kg: float,
) -> DoseResult:
    """Dose so the concentration at end of interval equals a target trough.

    C(τ) = (Dose/Vd)·e^(−kτ),  k = CL/Vd   ⇒   Dose = Ctrough·Vd·e^(kτ)
    """
    k = child_clearance_l_per_h / child_volume_l
    dose = ctrough_target_mg_per_l * child_volume_l * math.exp(k * interval_h)
    return _result(
        dose,
        weight_kg,
        "trough",
        "trough concentration at end of interval",
        interval_h=interval_h,
        ctrough_target_mg_per_l=ctrough_target_mg_per_l,
        elimination_rate_per_h=k,
    )


def solve_loading(
    c_target_mg_per_l: float,
    child_volume_l: float,
    weight_kg: float,
) -> DoseResult:
    """Loading dose to fill the volume to a target concentration: LD = Vd·C_target."""
    dose = c_target_mg_per_l * child_volume_l
    return _result(
        dose,
        weight_kg,
        "loading",
        "target concentration after loading dose",
        c_target_mg_per_l=c_target_mg_per_l,
        child_volume_l=child_volume_l,
    )


def solve_mgkg_linear(
    adult_reference_dose_mg: float,
    weight_kg: float,
    adult_weight_kg: float = 70.0,
) -> DoseResult:
    """Naive linear weight scaling — the unsafe baseline PaedScale exists to correct."""
    dose = adult_reference_dose_mg * (weight_kg / adult_weight_kg)
    return _result(
        dose,
        weight_kg,
        "mgkg_linear",
        "linear body-weight scaling (naive baseline)",
        adult_reference_dose_mg=adult_reference_dose_mg,
    )


_SOLVERS = {
    "auc": solve_auc,
    "css": solve_css,
    "cmax": solve_cmax,
    "trough": solve_trough,
    "loading": solve_loading,
    "mgkg_linear": solve_mgkg_linear,
}


def solve(method: str, **params) -> DoseResult:
    """Dispatch to the named method. Raises ValueError on an unknown method."""
    try:
        solver = _SOLVERS[method]
    except KeyError:
        raise ValueError(f"Unknown dosing method '{method}'. Known: {', '.join(METHODS)}")
    return solver(**params)
