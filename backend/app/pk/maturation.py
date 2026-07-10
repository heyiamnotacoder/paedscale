"""Anderson-Holford sigmoidal maturation (Hill / Emax) model.

Each elimination pathway (e.g. CYP3A4, renal GFR, UGT2B7) matures on its own
trajectory as a function of postmenstrual age (PMA = gestational + postnatal
age, in weeks). MF(PMA) rises from near-zero at extreme prematurity to a
plateau of 1.0 in adulthood. See concept doc: "Maturation function — organ
development".

Real drugs are eliminated by *several* pathways, each maturing at its own rate
and each sensitive to a different organ's function. The generalized engine
therefore represents a drug as a list of `Pathway`s (fraction of clearance +
its maturation curve + which organ it depends on) and blends them, rather than
assuming a single dominant route with the remainder already adult-mature.
"""

from dataclasses import dataclass


@dataclass
class Pathway:
    """One elimination route's contribution to a drug's clearance.

    fm       fraction of total adult clearance via this route (fm's sum to ~1)
    tm50_weeks, hill   the route's Anderson-Holford maturation curve
    name     e.g. "CYP3A4", "renal_GFR"
    organ    which organ's function scales this route: "hepatic" | "renal" | "other"
    """

    fm: float
    tm50_weeks: float
    hill: float
    name: str = ""
    organ: str = "other"


def maturation_fraction(pma_weeks: float, tm50_weeks: float, hill: float) -> float:
    """Fraction (0-1) of adult pathway activity reached at a given postmenstrual age.

    MF(PMA) = PMA^H / (TM50^H + PMA^H)
    """
    if pma_weeks <= 0:
        return 0.0
    return (pma_weeks**hill) / (tm50_weeks**hill + pma_weeks**hill)


def combined_pathway_maturation(
    pma_weeks: float,
    pathway_fm: float,
    pathway_tm50_weeks: float,
    pathway_hill: float,
    other_pathway_maturation: float = 1.0,
) -> float:
    """Weighted maturation across the drug's dominant pathway and the remainder.

    `pathway_fm` is the fraction of total clearance attributed to the mapped
    pathway (the fm split from the Claude reasoning step). The remainder is
    assumed to mature at `other_pathway_maturation` (default: already adult-like),
    matching the concept's organ-function modifier (OF) for pathways not
    explicitly modelled.
    """
    mf_pathway = maturation_fraction(pma_weeks, pathway_tm50_weeks, pathway_hill)
    return pathway_fm * mf_pathway + (1 - pathway_fm) * other_pathway_maturation


def combined_maturation(pma_weeks: float, pathways: list[Pathway]) -> float:
    """Fraction of adult clearance capacity across *all* elimination pathways.

    combined = Σ_i  fm_i · MF_i(PMA)

    Each pathway is explicitly enumerated with its own maturation curve — there
    is no "the rest is already adult" assumption. If the supplied fm's do not
    sum to 1 they are treated as-is (the caller is responsible for a sensible
    split); use `normalized_pathways` first if the fractions come from an LLM
    and may not sum cleanly.
    """
    return sum(p.fm * maturation_fraction(pma_weeks, p.tm50_weeks, p.hill) for p in pathways)


def effective_clearance_fraction(
    pma_weeks: float,
    pathways: list[Pathway],
    organ_modifiers: dict[str, float] | None = None,
) -> float:
    """Maturation blended with per-organ (patho)physiological function.

    effective = Σ_i  fm_i · MF_i(PMA) · OF(organ_i)

    `organ_modifiers` maps an organ ("hepatic" | "renal" | "other") to a
    fraction in (0, 1] capturing impairment *beyond* the age-normal maturation
    the curves already encode (e.g. Child-Pugh hepatic reduction, low eGFR).
    A route whose organ is absent from the map is left unmodified (OF = 1).
    """
    mods = organ_modifiers or {}
    return sum(
        p.fm
        * maturation_fraction(pma_weeks, p.tm50_weeks, p.hill)
        * mods.get(p.organ, 1.0)
        for p in pathways
    )


def normalized_pathways(pathways: list[Pathway]) -> list[Pathway]:
    """Return pathways with fm's rescaled to sum to 1 (no-op if already ~1 or empty)."""
    total = sum(p.fm for p in pathways)
    if total <= 0:
        return pathways
    return [
        Pathway(fm=p.fm / total, tm50_weeks=p.tm50_weeks, hill=p.hill, name=p.name, organ=p.organ)
        for p in pathways
    ]
