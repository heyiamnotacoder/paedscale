"""Wires allometry, maturation, distribution and dose-solve into one deterministic call.

This is the compute layer described in the concept doc (steps 4-5): given an
adult PK profile, a pathway fm split (normally supplied by the Claude
reasoning step; curated directly in `data/drugs.json` for the in-scope
drugs), and a child's covariates, produce the pediatric clearance, volume,
and recommended dose. No LLM calls happen in this module.
"""

from dataclasses import dataclass

from app.pk.allometry import scale_clearance
from app.pk.distribution import corrected_volume
from app.pk.dose_solve import DoseRecommendation, solve_dose
from app.pk.maturation import combined_pathway_maturation


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
) -> DoseRecommendation:
    maturation = combined_pathway_maturation(
        pma_weeks=child.pma_weeks,
        pathway_fm=drug.fm_primary,
        pathway_tm50_weeks=pathway.tm50_weeks,
        pathway_hill=pathway.hill,
    )
    size_scaled_cl = scale_clearance(drug.adult_clearance_l_per_h, child.weight_kg)
    child_cl = size_scaled_cl * maturation

    child_protein_binding = (
        child.protein_binding if child.protein_binding is not None else drug.adult_protein_binding
    )
    child_vd = corrected_volume(
        drug.adult_volume_l,
        child.weight_kg,
        drug.adult_protein_binding,
        child_protein_binding,
    )

    return solve_dose(
        adult_reference_dose_mg=drug.adult_reference_dose_mg,
        adult_clearance_l_per_h=drug.adult_clearance_l_per_h,
        adult_interval_h=drug.dosing_interval_h,
        child_clearance_l_per_h=child_cl,
        child_volume_l=child_vd,
        weight_kg=child.weight_kg,
        child_interval_h=child_interval_h,
    )
