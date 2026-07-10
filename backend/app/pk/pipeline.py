"""Wires allometry, maturation, distribution and dose-solve into one deterministic call.

This is the compute layer described in the concept doc (steps 4-5): given an
adult PK profile, a pathway fm split (normally supplied by the Claude
reasoning step; curated directly in `data/drugs.json` for the in-scope
drugs), and a child's covariates, produce the pediatric clearance, volume,
and recommended dose. No LLM calls happen in this module.
"""

import inspect
from dataclasses import dataclass

from app.pk.allometry import scale_clearance
from app.pk.distribution import corrected_volume
from app.pk.dose_solve import DoseRecommendation, solve_dose
from app.pk.maturation import (
    Pathway,
    combined_maturation,
    combined_pathway_maturation,
    effective_clearance_fraction,
    normalized_pathways,
)
from app.pk.methods import DoseResult, solve


@dataclass
class ChildCovariates:
    weight_kg: float
    pma_weeks: float
    protein_binding: float | None = None  # override; else falls back to adult value


@dataclass
class DrugProfile:
    name: str
    adult_clearance_l_per_h: float
    adult_volume_l: float
    adult_protein_binding: float
    primary_pathway: str
    fm_primary: float
    adult_reference_dose_mg: float
    dosing_interval_h: float


@dataclass
class PathwayMaturation:
    tm50_weeks: float
    hill: float


def extrapolate(
    drug: DrugProfile,
    pathway: PathwayMaturation,
    child: ChildCovariates,
    child_interval_h: float | None = None,
    organ_function_modifier: float = 1.0,
) -> DoseRecommendation:
    maturation = combined_pathway_maturation(
        pma_weeks=child.pma_weeks,
        pathway_fm=drug.fm_primary,
        pathway_tm50_weeks=pathway.tm50_weeks,
        pathway_hill=pathway.hill,
    )
    size_scaled_cl = scale_clearance(drug.adult_clearance_l_per_h, child.weight_kg)
    child_cl = size_scaled_cl * maturation * organ_function_modifier

    child_protein_binding = (
        child.protein_binding if child.protein_binding is not None else drug.adult_protein_binding
    )
    child_vd = corrected_volume(
        drug.adult_volume_l,
        child.weight_kg,
        drug.adult_protein_binding,
        child_protein_binding,
    )

    rec = solve_dose(
        adult_reference_dose_mg=drug.adult_reference_dose_mg,
        adult_clearance_l_per_h=drug.adult_clearance_l_per_h,
        adult_interval_h=drug.dosing_interval_h,
        child_clearance_l_per_h=child_cl,
        child_volume_l=child_vd,
        weight_kg=child.weight_kg,
        child_interval_h=child_interval_h,
    )
    rec.maturation_fraction = maturation
    return rec


# --------------------------------------------------------------------------- #
# Generalized engine: multiple pathways, per-organ function, choice of method. #
# --------------------------------------------------------------------------- #


@dataclass
class GeneralizedResult:
    child_clearance_l_per_h: float
    child_volume_l: float
    maturation_fraction: float  # Σ fm·MF, organ-function-independent (for display)
    effective_clearance_fraction: float  # includes per-organ (patho)physiology
    dose: DoseResult


def child_clearance(
    adult_clearance_l_per_h: float,
    weight_kg: float,
    pma_weeks: float,
    pathways: list[Pathway],
    organ_modifiers: dict[str, float] | None = None,
) -> float:
    """Child clearance = allometric size scaling × blended maturation × organ function."""
    eff = effective_clearance_fraction(pma_weeks, pathways, organ_modifiers)
    return scale_clearance(adult_clearance_l_per_h, weight_kg) * eff


def child_distribution_volume(
    adult_volume_l: float,
    weight_kg: float,
    adult_protein_binding: float,
    child_protein_binding: float | None = None,
) -> float:
    """Child Vd = size-scaled adult Vd corrected for altered free fraction."""
    pb = child_protein_binding if child_protein_binding is not None else adult_protein_binding
    return corrected_volume(adult_volume_l, weight_kg, adult_protein_binding, pb)


def extrapolate_generalized(
    adult_clearance_l_per_h: float,
    adult_volume_l: float,
    adult_protein_binding: float,
    pathways: list[Pathway],
    child: ChildCovariates,
    method: str,
    method_params: dict | None = None,
    organ_modifiers: dict[str, float] | None = None,
    normalize_fm: bool = True,
) -> GeneralizedResult:
    """Full deterministic solve for an arbitrary drug.

    The orchestrator supplies the pathway split (fm's + curves + organs), the
    per-organ function modifiers, and the chosen dosing `method` with its
    method-specific targets. This function computes child CL and Vd, then feeds
    whichever of {weight_kg, child_clearance_l_per_h, child_volume_l} the chosen
    solver accepts, alongside the caller's `method_params`.
    """
    paths = normalized_pathways(pathways) if normalize_fm else pathways

    maturation = combined_maturation(child.pma_weeks, paths)
    eff = effective_clearance_fraction(child.pma_weeks, paths, organ_modifiers)
    child_cl = scale_clearance(adult_clearance_l_per_h, child.weight_kg) * eff
    child_vd = child_distribution_volume(
        adult_volume_l, child.weight_kg, adult_protein_binding, child.protein_binding
    )

    # Offer the computed physiology (and the adult PK it derived from) to the
    # solver; keep only the params that solver declares. Caller-supplied
    # method_params win on conflict.
    available = {
        "weight_kg": child.weight_kg,
        "child_clearance_l_per_h": child_cl,
        "child_volume_l": child_vd,
        "adult_clearance_l_per_h": adult_clearance_l_per_h,
        "adult_volume_l": adult_volume_l,
        **(method_params or {}),
    }
    from app.pk.methods import _SOLVERS  # local import to avoid surfacing the registry

    if method not in _SOLVERS:
        raise ValueError(f"Unknown dosing method '{method}'.")
    accepted = set(inspect.signature(_SOLVERS[method]).parameters)
    params = {k: v for k, v in available.items() if k in accepted}
    dose = solve(method, **params)

    return GeneralizedResult(
        child_clearance_l_per_h=child_cl,
        child_volume_l=child_vd,
        maturation_fraction=maturation,
        effective_clearance_fraction=eff,
        dose=dose,
    )
