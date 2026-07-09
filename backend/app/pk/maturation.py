"""Anderson-Holford sigmoidal maturation (Hill / Emax) model.

Each elimination pathway (e.g. CYP3A4, renal GFR, UGT2B7) matures on its own
trajectory as a function of postmenstrual age (PMA = gestational + postnatal
age, in weeks). MF(PMA) rises from near-zero at extreme prematurity to a
plateau of 1.0 in adulthood. See concept doc: "Maturation function — organ
development".
"""


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
