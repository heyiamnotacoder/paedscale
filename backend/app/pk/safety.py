"""Safety-bound check on the recommended dose.

Edge-case requirement: a recommendation must fall within the drug's safe limit
and its minimum effective dose. A mechanistic estimate that lands below the
minimum effective dose is futile; one above the maximum safe dose is dangerous.
Either way the number must not be emitted bare — it is clamped to the nearest
bound and flagged loudly so the clinician (and the Critic agent) see it.

Bounds are supplied by the Safety agent (retrieved from label / literature) as
weight-normalised mg/kg values. Either bound may be None (unknown), in which
case that side is simply not checked and the uncertainty is surfaced elsewhere.
"""

from dataclasses import dataclass


@dataclass
class BoundsCheck:
    within: bool
    recommended_mg_per_kg: float
    clamped_mg_per_kg: float
    min_effective_mg_per_kg: float | None
    max_safe_mg_per_kg: float | None
    flag: str | None  # human-readable reason when out of bounds, else None


def check_bounds(
    dose_mg_per_kg: float,
    min_effective_mg_per_kg: float | None,
    max_safe_mg_per_kg: float | None,
) -> BoundsCheck:
    """Clamp the dose into [min_effective, max_safe] and flag if it was outside."""
    clamped = dose_mg_per_kg
    flag: str | None = None

    if max_safe_mg_per_kg is not None and dose_mg_per_kg > max_safe_mg_per_kg:
        clamped = max_safe_mg_per_kg
        flag = (
            f"Estimated {dose_mg_per_kg:.4g} mg/kg exceeds the maximum safe dose "
            f"{max_safe_mg_per_kg:.4g} mg/kg — clamped to the safe limit; do not exceed."
        )
    elif min_effective_mg_per_kg is not None and dose_mg_per_kg < min_effective_mg_per_kg:
        clamped = min_effective_mg_per_kg
        flag = (
            f"Estimated {dose_mg_per_kg:.4g} mg/kg is below the minimum effective dose "
            f"{min_effective_mg_per_kg:.4g} mg/kg — raised to the effective minimum; "
            "the mechanistic estimate may be sub-therapeutic."
        )

    return BoundsCheck(
        within=flag is None,
        recommended_mg_per_kg=dose_mg_per_kg,
        clamped_mg_per_kg=clamped,
        min_effective_mg_per_kg=min_effective_mg_per_kg,
        max_safe_mg_per_kg=max_safe_mg_per_kg,
        flag=flag,
    )
