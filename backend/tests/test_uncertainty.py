"""
Uncertainty layer: Monte Carlo prediction interval over the PUBLISHED 95% CIs of the
maturation parameters (TM50, Hill). Deterministic (seeded), no API key.

Run:  python3 -m tests.test_uncertainty
"""

from engine.pk_engine import compute_pediatric_dose
from engine.uncertainty import dose_prediction_interval

# A renally cleared drug (vancomycin-like) — absolute CL/Vd do not drive the css ratio.
RENAL = dict(
    drug="renal-test", cl_adult_l_h=4.2, vd_adult_l=49.0, fm={"renal_gfr": 0.9},
    target_metric="css", adult_dose_mg_per_day=2000.0,
)


def test_interval_brackets_point_estimate_for_term_neonate():
    point = compute_pediatric_dose(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    pi = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    lo, hi = pi["dose_mg_per_kg_per_day"]["p05"], pi["dose_mg_per_kg_per_day"]["p95"]
    assert lo < point.recommended_dose_mg_per_kg_per_day < hi, (lo, point, hi)
    # A term neonate sits on the steep part of the GFR curve: the interval is non-trivial.
    assert hi / lo > 1.10, (lo, hi)
    print(f"  PI brackets neonate point: {lo:.1f}–{hi:.1f} mg/kg/day  OK")


def test_interval_narrows_as_maturation_completes():
    neo = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    teen = dose_prediction_interval(weight_kg=50.0, age_years=14.0, **RENAL)
    assert teen["fold_width_90"] < neo["fold_width_90"], (teen["fold_width_90"], neo["fold_width_90"])
    assert teen["fold_width_90"] < 1.02, teen["fold_width_90"]
    print(f"  PI narrows with age: neonate ×{neo['fold_width_90']:.2f} → 14 yr ×{teen['fold_width_90']:.3f}  OK")


def test_seeded_and_reproducible():
    a = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, seed=7, **RENAL)
    b = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, seed=7, **RENAL)
    assert a == b
    print("  PI reproducible under a fixed seed  OK")


def test_sensitivity_attributes_variance_to_the_maturing_pathway():
    mixed = dict(RENAL, fm={"renal_gfr": 0.5, "cyp3a4": 0.5})
    pi = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, **mixed)
    shares = pi["variance_share"]
    assert set(shares) == {"renal_gfr", "cyp3a4"}, shares
    assert abs(sum(shares.values()) - 1.0) < 1e-6, shares
    print(f"  variance share: {shares}  OK")


def test_cmax_dose_is_volume_matched_so_dose_interval_is_degenerate():
    cmax = dict(RENAL, target_metric="cmax")
    pi = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, **cmax)
    d = pi["dose_mg_per_kg_per_day"]
    assert abs(d["p95"] / d["p05"] - 1.0) < 1e-9, d
    # ...but maturation uncertainty still moves the half-life, which sets the interval.
    hl = pi["half_life_h"]
    assert hl["p95"] / hl["p05"] > 1.10, hl
    print("  cmax: dose interval degenerate, half-life interval carries the uncertainty  OK")


def test_blocked_case_returns_none():
    pi = dose_prediction_interval(weight_kg=3.5, pma_weeks=42.0, **dict(RENAL, fm={}))
    assert pi is None
    print("  blocked case → no interval  OK")


if __name__ == "__main__":
    print("Uncertainty layer (no API key):")
    test_interval_brackets_point_estimate_for_term_neonate()
    test_interval_narrows_as_maturation_completes()
    test_seeded_and_reproducible()
    test_sensitivity_attributes_variance_to_the_maturing_pathway()
    test_cmax_dose_is_volume_matched_so_dose_interval_is_degenerate()
    test_blocked_case_returns_none()
    print("All uncertainty tests passed.")
