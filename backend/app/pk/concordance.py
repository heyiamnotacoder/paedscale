"""Concordance check: compare the mechanistic dose estimate against the
nearest known guideline dose (concept: "self-checks against guidelines
where they exist... the guideline set becomes the test suite, not the
competitor"). Pure number comparison — no LLM involved.
"""

from dataclasses import dataclass

CONCORDANT_RATIO_BAND = (0.5, 2.0)
PMA_MATCH_WINDOW_WEEKS = 15.0


@dataclass
class ConcordanceResult:
    matched: bool
    guideline_age_group: str | None
    guideline_dose_mg_per_kg: float | None
    predicted_dose_mg_per_kg: float
    ratio: float | None
    verdict: str  # "concordant" | "divergent" | "no_guideline_available"
    source: str | None


def find_concordance(
    pma_weeks: float,
    predicted_dose_mg_per_kg: float,
    guideline_cases: list[dict],
    pma_window_weeks: float = PMA_MATCH_WINDOW_WEEKS,
) -> ConcordanceResult:
    """Find the nearest guideline case (by PMA) within the match window and compare.

    Cases with a missing/null pma_weeks or guideline_dose_mg_per_kg are skipped (real guideline
    entries — e.g. "children > 3 months" — often carry no specific PMA).
    """
    candidates = [
        g
        for g in guideline_cases
        if g.get("pma_weeks") is not None
        and g.get("guideline_dose_mg_per_kg") is not None
        and abs(g["pma_weeks"] - pma_weeks) <= pma_window_weeks
    ]
    if not candidates:
        return ConcordanceResult(
            matched=False,
            guideline_age_group=None,
            guideline_dose_mg_per_kg=None,
            predicted_dose_mg_per_kg=predicted_dose_mg_per_kg,
            ratio=None,
            verdict="no_guideline_available",
            source=None,
        )

    nearest = min(candidates, key=lambda g: abs(g["pma_weeks"] - pma_weeks))
    ratio = predicted_dose_mg_per_kg / nearest["guideline_dose_mg_per_kg"]
    low, high = CONCORDANT_RATIO_BAND
    verdict = "concordant" if low <= ratio <= high else "divergent"

    return ConcordanceResult(
        matched=True,
        guideline_age_group=nearest["age_group"],
        guideline_dose_mg_per_kg=nearest["guideline_dose_mg_per_kg"],
        predicted_dose_mg_per_kg=predicted_dose_mg_per_kg,
        ratio=ratio,
        verdict=verdict,
        source=nearest["source"],
    )
