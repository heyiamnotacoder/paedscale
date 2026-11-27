"""Size-scaling methods compared in the label benchmark (harness only).

Every method gets the same adult daily dose and the same virtual patients
(benchmark/PROTOCOL.md, Amendment 1). Predictions are per-kg daily doses in the drug's
reference unit (mg, or units for penicillin G).
"""

from __future__ import annotations

import math

from benchmark.growth import median_weight_kg
from engine.pk_engine import compute_pediatric_dose

REF_KG = 70.0
GRID_POINTS = 7
# Amendment 1 §4: fixed nominal adult CL/Vd. They cancel out of every dose ratio.
NOMINAL_CL_L_H = 10.0
NOMINAL_VD_L = 50.0


def virtual_patients(band: dict, *, weight_scale: float = 1.0, ga_shift: float = 0.0,
                     grid: bool = True) -> list[dict]:
    """Patients spanning a label age band: log-spaced postnatal ages, median weights."""
    lo, hi = band["pna_days"]
    if not grid:
        ages = [(lo + hi) / 2.0]
    elif hi - lo < 1e-9:
        ages = [lo]
    else:
        a, b = math.log(max(lo, 1.0)), math.log(hi)
        ages = [math.exp(a + (b - a) * i / (GRID_POINTS - 1)) for i in range(GRID_POINTS)]
    ga = (band.get("ga_weeks") or 40.0)
    if ga < 37:            # S5 varies the representative GA of preterm bands only
        ga += ga_shift
    return [
        {"pna_days": t, "ga_weeks": ga, "pma_weeks": ga + t / 7.0,
         "weight_kg": median_weight_kg(t, gestational_age_weeks=ga) * weight_scale}
        for t in ages
    ]


def _bsa_costeff(w: float) -> float:
    return (4.0 * w + 7.0) / (w + 90.0)


def _fm(drug: dict) -> dict:
    fe = drug["fe"]["value"]
    fm = {}
    if fe > 0:
        fm["renal_gfr"] = fe
    if drug.get("nonrenal_enzyme"):
        fm[drug["nonrenal_enzyme"]] = 1.0 - fe
    return fm


def _per_kg(method: str, drug: dict, p: dict, force_css: bool) -> float:
    adult = drug["adult"]["daily"]
    w = p["weight_kg"]
    metric = "css" if force_css else drug["target_metric"]
    if method == "weight_linear":
        return adult / REF_KG
    if method == "bsa":
        return adult * _bsa_costeff(w) / _bsa_costeff(REF_KG) / w
    if method == "allometry":
        return adult * (w / REF_KG) ** 0.75 / w
    if method == "allometry_class":
        exp = 1.0 if metric == "cmax" else 0.75
        return adult * (w / REF_KG) ** exp / w
    if method == "paedscale":
        r = compute_pediatric_dose(
            drug="benchmark", weight_kg=w, cl_adult_l_h=NOMINAL_CL_L_H, vd_adult_l=NOMINAL_VD_L,
            fm=_fm(drug), target_metric=metric, pma_weeks=p["pma_weeks"],
            adult_dose_mg_per_day=adult,
        )
        if r.blocked or r.recommended_dose_mg_per_kg_per_day is None:
            raise ValueError(f"engine blocked a benchmark case: {r.block_reason}")
        return r.recommended_dose_mg_per_kg_per_day
    raise KeyError(method)


METHODS = ("weight_linear", "bsa", "allometry", "allometry_class", "paedscale")


def predict_band(method: str, drug: dict, band: dict, *, weight_scale: float = 1.0,
                 ga_shift: float = 0.0, grid: bool = True, force_css: bool = False) -> float:
    """Band prediction = geometric mean of the per-kg dose over the band's virtual patients."""
    pts = virtual_patients(band, weight_scale=weight_scale, ga_shift=ga_shift, grid=grid)
    logs = [math.log(_per_kg(method, drug, p, force_css)) for p in pts]
    return math.exp(sum(logs) / len(logs))
