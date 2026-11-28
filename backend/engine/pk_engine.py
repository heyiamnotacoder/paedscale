"""
PaedScale — deterministic pharmacokinetic engine.

This is the "trivial to code, must be exactly right" layer. It applies allometric
scaling (WT^0.75 for clearance) and the Anderson–Holford maturation function
(pathway by pathway) to turn adult PK into a pediatric clearance/volume, then solves
for the dose that reproduces the adult exposure on the drug's effect-driving metric.

Pure functions only — no I/O, no LLM. Callable both as a Claude tool and from unit
tests with no API key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.constants import (
    ADULT_PMA_WEEKS,
    CL_EXPONENT,
    DRUG_SPECIFIC,
    MATURATION,
    REFERENCE_WEIGHT_KG,
    VD_EXPONENT,
)


# ---------------------------------------------------------------------------
# Renal function estimation (labs -> organ-function modifier)
# ---------------------------------------------------------------------------
# Bedside Schwartz constant (Schwartz GJ et al., J Am Soc Nephrol 2009): a
# height/creatinine estimate validated in CHILDREN. Cockcroft-Gault is adult-
# derived (uses 140 - age) and materially overestimates GFR in the young, so it
# is deliberately NOT used here.
SCHWARTZ_K_BEDSIDE = 0.413
NORMAL_GFR_ML_MIN_1_73M2 = 100.0  # approx normal pediatric / young-adult GFR reference


def estimate_gfr_bedside_schwartz(
    height_cm: Optional[float],
    serum_creatinine_mg_dl: Optional[float],
) -> Optional[float]:
    """Bedside Schwartz eGFR (mL/min/1.73 m^2) = 0.413 * height_cm / SCr(mg/dL).

    Returns None when inputs are missing or non-physiological, so callers fall
    back to a data-gap flag rather than a fabricated number.
    """
    try:
        h = float(height_cm)
        scr = float(serum_creatinine_mg_dl)
    except (TypeError, ValueError):
        return None
    if h <= 0 or scr <= 0:
        return None
    return SCHWARTZ_K_BEDSIDE * h / scr


def renal_function_fraction_from_labs(
    height_cm: Optional[float],
    serum_creatinine_mg_dl: Optional[float],
    normal_gfr: float = NORMAL_GFR_ML_MIN_1_73M2,
) -> Optional[float]:
    """Renal organ-function modifier (OF) in (0, 1] from labs, relative to normal GFR.

    OF multiplies the maturation-adjusted renal clearance in compute_pediatric_dose;
    it represents impairment on top of age maturation. Clamped to [0.1, 1.0] (never
    amplifies above normal). Returns None when GFR cannot be estimated.
    """
    egfr = estimate_gfr_bedside_schwartz(height_cm, serum_creatinine_mg_dl)
    if egfr is None:
        return None
    return max(0.1, min(1.0, egfr / normal_gfr))


# ---------------------------------------------------------------------------
# Core maturation math
# ---------------------------------------------------------------------------
def maturation_factor(pma_weeks: float, tm50_weeks: float, hill: float) -> float:
    """Anderson–Holford sigmoidal maturation: fraction of adult activity at a given PMA.

    Normalised so that an adult (PMA = ADULT_PMA_WEEKS) returns ~1.0.
    """
    def _hill(pma: float) -> float:
        return pma ** hill / (tm50_weeks ** hill + pma ** hill)

    mf = _hill(pma_weeks)
    mf_adult = _hill(ADULT_PMA_WEEKS)
    return mf / mf_adult if mf_adult else mf


# International non-proprietary name <-> US name, for matching a drug to a curve's probe.
_DRUG_ALIASES = {"acetaminophen": "paracetamol"}


def is_probe_drug(drug: Optional[str], probe: Optional[str]) -> bool:
    """True when `drug` names the curve's probe (salt and case ignored, INN/USAN aliased)."""
    if not drug or not probe:
        return False
    words = [_DRUG_ALIASES.get(w, w) for w in drug.lower().replace("-", " ").split()]
    return probe.lower() in words


def allometric_scale(weight_kg: float, exponent: float) -> float:
    """(WT / 70) ** exponent."""
    return (weight_kg / REFERENCE_WEIGHT_KG) ** exponent


# ---------------------------------------------------------------------------
# I/O containers
# ---------------------------------------------------------------------------
@dataclass
class PathwayResult:
    pathway: str
    label: str
    fraction: float                # fm for this pathway
    maturation_factor: float       # MF(PMA) for this pathway (0..1)
    organ_function_modifier: float # OF (renal/hepatic impairment), 1.0 = normal
    cl_child_l_h: float            # this pathway's contribution to child clearance
    source: str


@dataclass
class DoseResult:
    # child physiology
    pma_weeks: float
    weight_kg: float
    cl_child_l_h: float
    vd_child_l: float
    half_life_h: float
    cl_fraction_of_adult: float    # child CL as fraction of adult CL (the headline gap)
    # per-pathway breakdown
    pathways: list[PathwayResult] = field(default_factory=list)
    # dose
    target_metric: str = ""
    recommended_dose_mg_per_day: Optional[float] = None
    recommended_dose_mg_per_kg_per_day: Optional[float] = None
    suggested_interval_h: Optional[float] = None
    dose_basis: str = ""           # human-readable explanation of the solve
    # safety
    warnings: list[str] = field(default_factory=list)
    # hard stop: set when the case is NOT prescribable (non-viable route / above-toxic dose).
    # When True, recommended_dose_* is held at None and block_reason carries the message.
    blocked: bool = False
    block_reason: str = ""


def _resolve_pma_weeks(
    age_years: Optional[float],
    pma_weeks: Optional[float],
    gestational_age_weeks: Optional[float],
    postnatal_age_weeks: Optional[float],
    assume_term: bool = True,
) -> tuple[float, list[str]]:
    """Resolve postmenstrual age in weeks from whatever the caller supplied.

    Priority: explicit pma_weeks > (gestational + postnatal) > age_years.
    If age < 2 yr and no PMA info, assume term (40 wk gestation) and warn.
    """
    warnings: list[str] = []
    if pma_weeks is not None:
        return pma_weeks, warnings
    if gestational_age_weeks is not None and postnatal_age_weeks is not None:
        return gestational_age_weeks + postnatal_age_weeks, warnings
    if age_years is None:
        raise ValueError("Provide one of: pma_weeks, (gestational+postnatal), or age_years.")
    postnatal_weeks = age_years * 52.0
    if age_years < 2.0 and assume_term:
        warnings.append(
            "PMA not supplied for a child < 2 yr — assumed TERM gestation (40 wk). "
            "For a preterm infant this understates immaturity and OVER-estimates the dose."
        )
        return 40.0 + postnatal_weeks, warnings
    # older child: gestational contribution is negligible relative to postnatal age
    return 40.0 + postnatal_weeks, warnings


def compute_pediatric_dose(
    *,
    drug: str,
    weight_kg: float,
    cl_adult_l_h: float,
    vd_adult_l: float,
    fm: dict[str, float],
    target_metric: str = "css",
    age_years: Optional[float] = None,
    pma_weeks: Optional[float] = None,
    gestational_age_weeks: Optional[float] = None,
    postnatal_age_weeks: Optional[float] = None,
    adult_dose_mg_per_day: Optional[float] = None,
    adult_interval_h: Optional[float] = None,
    renal_function_fraction: float = 1.0,   # OF for renal pathways (1.0 = normal)
    hepatic_function_fraction: float = 1.0, # OF for hepatic pathways (1.0 = normal)
    toxic_dose_mg_per_kg_per_day: Optional[float] = None,
    effective_dose_mg_per_kg_per_day: Optional[float] = None,
    route: str = "iv",                      # child administration route ("iv" | "oral")
    # None = unknown F (oral hard-stops as data gap). Do not default to 1.0 — that invents absorption.
    oral_bioavailability: Optional[float] = None,
    routes_allowed: Optional[list[str]] = None,  # explicit viable routes; None = infer from F
    assume_term: bool = True,
    # Sampled curves from engine/uncertainty.py only. Not in the agent tool schema or
    # _COMPUTE_KEYS, so the model can never pass invented curves.
    maturation: Optional[dict] = None,
) -> DoseResult:
    """Scale adult PK to a pediatric dose via allometry × pathway-wise maturation.

    `fm` maps MATURATION pathway keys -> fraction of clearance (should sum to ~1 for the
    cleared fraction). Any pathway key not present in MATURATION raises — the engine will
    not invent a maturation curve (cite-or-abstain at the code level).

    `target_metric`: css/auc (maintenance, clearance-matched), cmax (peak, volume-matched),
    or time_mic (β-lactam fT>MIC — solved like css but flagged as a proxy only).
    `route`/`oral_bioavailability`: for route="oral" the systemic-matched dose is divided by
    F to give the administered oral dose (F is treated as the adult value — a data-gap flag
    is raised because pediatric absorption can differ).
    """
    pma, warnings = _resolve_pma_weeks(
        age_years, pma_weeks, gestational_age_weeks, postnatal_age_weeks, assume_term
    )

    fm = fm or {}
    fm_total = sum(fm.values()) if fm else 0.0
    # Structurally invalid attribution → hard stop (no invented maturation, no double-count).
    # Empty fm would otherwise dose 100% unattributed mature allometry (over-dose risk in young).
    # Over-sum (>1.05) double-counts pathway clearance. Under-sum still allowed with flag below.
    if not fm or fm_total <= 0:
        blocked = DoseResult(
            pma_weeks=pma, weight_kg=weight_kg, cl_child_l_h=0.0, vd_child_l=0.0,
            half_life_h=float("inf"), cl_fraction_of_adult=0.0, target_metric=target_metric,
            warnings=list(warnings), blocked=True,
            block_reason=(
                "SAFETY STOP — empty or zero fm attribution; refusing to dose without a "
                "maturing pathway map (cite-or-abstain)."
            ),
        )
        blocked.dose_basis = blocked.block_reason
        blocked.warnings.append(blocked.block_reason)
        return blocked
    if fm_total > 1.05:
        blocked = DoseResult(
            pma_weeks=pma, weight_kg=weight_kg, cl_child_l_h=0.0, vd_child_l=0.0,
            half_life_h=float("inf"), cl_fraction_of_adult=0.0, target_metric=target_metric,
            warnings=list(warnings), blocked=True,
            block_reason=(
                f"SAFETY STOP — fm fractions sum to {fm_total:.2f} (>1.05); refusing to "
                "double-count clearance pathways."
            ),
        )
        blocked.dose_basis = blocked.block_reason
        blocked.warnings.append(blocked.block_reason)
        return blocked
    if not (0.5 <= fm_total <= 1.001):
        warnings.append(
            f"fm split sums to {fm_total:.2f} (expected ~1.0) — pathway attribution is "
            "incomplete or inconsistent; treat clearance estimate as uncertain."
        )

    curves = MATURATION if maturation is None else maturation
    cl_scale = allometric_scale(weight_kg, CL_EXPONENT)
    pathways: list[PathwayResult] = []
    cl_child = 0.0

    for pathway, fraction in fm.items():
        if pathway not in curves:
            raise ValueError(
                f"No maturation curve for pathway '{pathway}'. Refusing to invent one — "
                f"known pathways: {sorted(curves)}. Flag as a data gap instead."
            )
        params = curves[pathway]
        probe = params.get("probe_drug")
        if params.get("kind") == DRUG_SPECIFIC and not is_probe_drug(drug, probe):
            raise ValueError(
                f"Maturation curve '{pathway}' was estimated for {probe} only and is not "
                f"valid for '{drug}'. Use a pathway curve or flag a data gap."
            )
        if probe and not is_probe_drug(drug, probe):
            warnings.append(
                f"SURROGATE maturation curve for {pathway}: estimated from {probe}; applying "
                f"it to {drug} assumes the same age course for this pathway."
            )
        if params.get("caveats"):
            warnings.append(f"Maturation curve note ({pathway}): {params['caveats']}")
        mf = maturation_factor(pma, params["tm50_weeks"], params["hill"])
        of = renal_function_fraction if pathway.startswith("renal") else hepatic_function_fraction
        cl_pathway = cl_adult_l_h * fraction * cl_scale * mf * of
        cl_child += cl_pathway
        pathways.append(
            PathwayResult(
                pathway=pathway,
                label=params["label"],
                fraction=fraction,
                maturation_factor=mf,
                organ_function_modifier=of,
                cl_child_l_h=cl_pathway,
                source=params["source"],
            )
        )

    # Any un-attributed clearance (1 - fm_total) is carried at allometric scale only,
    # i.e. assumed mature — but flagged, never silently ignored.
    unattributed = max(0.0, 1.0 - fm_total)
    if unattributed > 0.01:
        cl_child += cl_adult_l_h * unattributed * cl_scale
        warnings.append(
            f"{unattributed*100:.0f}% of clearance is unattributed to a maturing pathway "
            "and was scaled by size only (assumed adult-like) — a source of error in the young."
        )

    vd_child = vd_adult_l * allometric_scale(weight_kg, VD_EXPONENT)
    half_life = math.log(2) * vd_child / cl_child if cl_child > 0 else float("inf")
    cl_fraction_adult = cl_child / cl_adult_l_h if cl_adult_l_h else float("nan")

    result = DoseResult(
        pma_weeks=pma,
        weight_kg=weight_kg,
        cl_child_l_h=cl_child,
        vd_child_l=vd_child,
        half_life_h=half_life,
        cl_fraction_of_adult=cl_fraction_adult,
        pathways=pathways,
        target_metric=target_metric,
        warnings=warnings,
    )

    # ---- route viability HARD STOP ----------------------------------------
    # A non-prescribable route yields NO dose (not a soft flag). Non-viable when an explicit
    # allow-list excludes the route, or oral with known F<=0 (not systemically absorbed).
    # Unknown F (None) is a data gap — block without claiming F=0.
    _route = (route or "iv").lower()
    if routes_allowed and _route not in {r.lower() for r in routes_allowed}:
        result.blocked = True
        result.block_reason = (
            f"SAFETY STOP — ROUTE NOT VIABLE: {_route} is not among allowed routes "
            f"{sorted({r.lower() for r in routes_allowed})} for {drug}."
        )
        result.dose_basis = result.block_reason
        result.warnings.append(result.block_reason)
        return result
    if _route == "oral" and oral_bioavailability is None:
        result.blocked = True
        result.block_reason = (
            f"SAFETY STOP — oral bioavailability unknown for {drug} (data gap); cannot "
            "convert a systemic-matched dose to an administered oral dose without inventing F."
        )
        result.dose_basis = result.block_reason
        result.warnings.append(result.block_reason)
        return result
    if _route == "oral" and oral_bioavailability <= 0:
        result.blocked = True
        result.block_reason = (
            f"SAFETY STOP — ROUTE NOT VIABLE: {drug} is not systemically absorbed via the "
            f"oral route (F={oral_bioavailability}); a systemic-exposure-matched dose cannot "
            "be delivered this way. IV/IM required."
        )
        result.dose_basis = result.block_reason
        result.warnings.append(result.block_reason)
        return result  # withhold the dose solve entirely

    # ---- dose solve -------------------------------------------------------
    # css / auc / time_mic all match the ADULT SYSTEMIC exposure by scaling the daily
    # dose-rate on the clearance ratio. time_mic (β-lactams) is solved the same way but
    # is only a PROXY — see the flag below.
    metric = target_metric.lower()
    if metric in ("css", "auc", "time_mic"):
        # exposure(AUC/Css) = dose_rate / CL  ->  match adult by scaling on clearance ratio
        if adult_dose_mg_per_day is not None:
            dose_rate_child = adult_dose_mg_per_day * (cl_child / cl_adult_l_h)
            result.recommended_dose_mg_per_day = dose_rate_child
            result.recommended_dose_mg_per_kg_per_day = dose_rate_child / weight_kg
            result.dose_basis = (
                f"Maintenance dose-rate matched on {metric.upper()}: "
                f"child clearance is {cl_fraction_adult:.0%} of the adult total, so the "
                f"daily dose is scaled by that same clearance ratio."
            )
        else:
            result.dose_basis = (
                f"{metric.upper()}-driven drug, but no adult daily dose supplied — "
                "cannot solve an absolute dose; clearance/volume returned for downstream use."
            )
        if metric == "time_mic":
            result.warnings.append(
                "TIME>MIC (fT>MIC) drug: the total-daily-dose match is a PROXY only — "
                "efficacy is governed by the FRACTION of the dosing interval above MIC, not "
                "by total exposure. Give frequently (e.g. q4–6h) or by extended/continuous "
                "infusion; treat concordance as DIRECTIONAL (grade ceiling B)."
            )
            # Force a half-life-anchored interval if the caller gave no adult interval to scale.
            if adult_interval_h is None and cl_child > 0 and math.isfinite(half_life):
                result.suggested_interval_h = half_life
                result.dose_basis += (
                    f" Interval anchored to one child half-life (~{half_life:.1f} h) as a "
                    "frequent-dosing placeholder; the fT>MIC target sets the real interval."
                )
    elif metric == "cmax":
        # peak concentration ~ dose / Vd  ->  match adult on volume ratio
        if adult_dose_mg_per_day is not None:
            dose_child = adult_dose_mg_per_day * (vd_child / vd_adult_l)
            result.recommended_dose_mg_per_day = dose_child
            result.recommended_dose_mg_per_kg_per_day = dose_child / weight_kg
            result.dose_basis = (
                "Peak-driven (Cmax) drug: dose matched on volume-of-distribution ratio "
                f"({vd_child/vd_adult_l:.2f}× adult Vd)."
            )
        else:
            result.dose_basis = "Cmax-driven drug, but no adult dose supplied to match against."
    else:
        result.dose_basis = f"Unknown target_metric '{target_metric}'."

    # ---- oral bioavailability -------------------------------------------------
    # The solve above yields the SYSTEMIC-matched dose (what must reach the circulation
    # to reproduce adult exposure). For an oral route only a fraction F is absorbed, so
    # the ADMINISTERED oral dose = systemic dose / F. Applied before the safety check so
    # the toxic/effective bounds are compared against the dose actually given.
    if route.lower() == "oral" and result.recommended_dose_mg_per_day is not None:
        if not (0.0 < oral_bioavailability <= 1.0):
            result.warnings.append(
                f"Oral route requested but F={oral_bioavailability} is out of range (0,1] — "
                "bioavailability correction skipped; dose is the systemic-equivalent amount."
            )
        else:
            result.recommended_dose_mg_per_day /= oral_bioavailability
            result.recommended_dose_mg_per_kg_per_day = (
                result.recommended_dose_mg_per_day / weight_kg
            )
            result.dose_basis += (
                f" Oral route: administered dose = systemic-matched dose / F "
                f"(F={oral_bioavailability:.2f})."
            )
            result.warnings.append(
                "Oral bioavailability F applied as the ADULT value — pediatric absorption "
                "(F) can differ (immature gut, first-pass, formulation); this is a data-gap "
                "assumption that shifts the oral dose if pediatric F is not adult-like."
            )

    # interval suggestion: scale adult interval by half-life prolongation
    if adult_interval_h is not None and cl_child > 0:
        adult_hl = math.log(2) * vd_adult_l / cl_adult_l_h
        ratio = half_life / adult_hl if adult_hl else 1.0
        result.suggested_interval_h = adult_interval_h * ratio
        if ratio > 1.3:
            result.warnings.append(
                f"Child half-life is {ratio:.1f}× the adult value — interval likely needs "
                "EXTENSION to avoid accumulation, not just a smaller dose."
            )

    # ---- safety bounds ----------------------------------------------------
    dpk = result.recommended_dose_mg_per_kg_per_day
    if dpk is not None:
        if toxic_dose_mg_per_kg_per_day is not None and dpk > toxic_dose_mg_per_kg_per_day:
            # HARD STOP: an above-toxic dose is never returned as a recommendation.
            result.blocked = True
            result.block_reason = (
                f"SAFETY STOP — DOSE EXCEEDS TOXIC THRESHOLD: computed {dpk:.2f} mg/kg/day "
                f"> toxic {toxic_dose_mg_per_kg_per_day} mg/kg/day; not prescribable."
            )
            result.warnings.append(result.block_reason)
            result.recommended_dose_mg_per_day = None
            result.recommended_dose_mg_per_kg_per_day = None
        if effective_dose_mg_per_kg_per_day is not None and dpk < effective_dose_mg_per_kg_per_day:
            # Below-effective stays a SOFT flag — a sub-therapeutic estimate is still informative.
            result.warnings.append(
                f"CALCULATED DOSE {dpk:.2f} mg/kg/day is BELOW the minimum effective dose "
                f"({effective_dose_mg_per_kg_per_day} mg/kg/day) — likely sub-therapeutic."
            )

    return result


def result_to_dict(r: DoseResult) -> dict:
    """Flatten a DoseResult for JSON / tool-return."""
    return {
        "pma_weeks": round(r.pma_weeks, 1),
        "weight_kg": r.weight_kg,
        "cl_child_l_h": round(r.cl_child_l_h, 3),
        "vd_child_l": round(r.vd_child_l, 2),
        "half_life_h": round(r.half_life_h, 2),
        "cl_fraction_of_adult": round(r.cl_fraction_of_adult, 3),
        "target_metric": r.target_metric,
        "recommended_dose_mg_per_day": (
            round(r.recommended_dose_mg_per_day, 2)
            if r.recommended_dose_mg_per_day is not None else None
        ),
        "recommended_dose_mg_per_kg_per_day": (
            round(r.recommended_dose_mg_per_kg_per_day, 3)
            if r.recommended_dose_mg_per_kg_per_day is not None else None
        ),
        "suggested_interval_h": (
            round(r.suggested_interval_h, 1) if r.suggested_interval_h is not None else None
        ),
        "dose_basis": r.dose_basis,
        "pathways": [
            {
                "pathway": p.pathway,
                "label": p.label,
                "fraction": p.fraction,
                "maturation_factor": round(p.maturation_factor, 3),
                "organ_function_modifier": p.organ_function_modifier,
                "cl_child_l_h": round(p.cl_child_l_h, 3),
                "source": p.source,
            }
            for p in r.pathways
        ],
        "warnings": r.warnings,
        "blocked": r.blocked,
        "block_reason": r.block_reason,
    }
