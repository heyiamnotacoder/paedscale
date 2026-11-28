"""
Uncertainty layer: Monte Carlo parameter-uncertainty interval over the PUBLISHED 95% CIs of the
maturation parameters (TM50, Hill). Deterministic (seeded), no API key.

Run:  python3 -m tests.test_uncertainty
"""

from engine.pk_engine import compute_pediatric_dose
import random

from engine.constants import MATURATION
from engine.uncertainty import dose_uncertainty_interval, sample_curve

# A renally cleared drug (vancomycin-like) — absolute CL/Vd do not drive the css ratio.
RENAL = dict(
    drug="renal-test", cl_adult_l_h=4.2, vd_adult_l=49.0, fm={"renal_gfr": 0.9},
    target_metric="css", adult_dose_mg_per_day=2000.0,
)


def test_interval_brackets_point_estimate_for_term_neonate():
    point = compute_pediatric_dose(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    pi = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    lo, hi = pi["dose_mg_per_kg_per_day"]["p05"], pi["dose_mg_per_kg_per_day"]["p95"]
    assert lo < point.recommended_dose_mg_per_kg_per_day < hi, (lo, point, hi)
    # A term neonate sits on the steep part of the GFR curve: the interval is non-trivial.
    assert hi / lo > 1.10, (lo, hi)
    print(f"  PI brackets neonate point: {lo:.1f}–{hi:.1f} mg/kg/day  OK")


def test_interval_narrows_as_maturation_completes():
    neo = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    teen = dose_uncertainty_interval(weight_kg=50.0, age_years=14.0, **RENAL)
    assert teen["fold_width_90"] < neo["fold_width_90"], (teen["fold_width_90"], neo["fold_width_90"])
    assert teen["fold_width_90"] < 1.02, teen["fold_width_90"]
    print(f"  PI narrows with age: neonate ×{neo['fold_width_90']:.2f} → 14 yr ×{teen['fold_width_90']:.3f}  OK")


def test_seeded_and_reproducible():
    a = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, seed=7, **RENAL)
    b = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, seed=7, **RENAL)
    assert a == b
    print("  PI reproducible under a fixed seed  OK")


def test_sensitivity_attributes_variance_to_the_maturing_pathway():
    mixed = dict(RENAL, fm={"renal_gfr": 0.5, "cyp3a4": 0.5})
    pi = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **mixed)
    shares = pi["variance_share"]
    assert set(shares) == {"renal_gfr", "cyp3a4"}, shares
    assert abs(sum(shares.values()) - 1.0) < 1e-6, shares
    print(f"  variance share: {shares}  OK")


def test_cmax_dose_is_volume_matched_so_dose_interval_is_degenerate():
    cmax = dict(RENAL, target_metric="cmax")
    pi = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **cmax)
    d = pi["dose_mg_per_kg_per_day"]
    assert abs(d["p95"] / d["p05"] - 1.0) < 1e-9, d
    # ...but maturation uncertainty still moves the half-life, which sets the interval.
    hl = pi["half_life_h"]
    assert hl["p95"] / hl["p05"] > 1.10, hl
    print("  cmax: dose interval degenerate, half-life interval carries the uncertainty  OK")


def test_blocked_case_returns_none():
    pi = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **dict(RENAL, fm={}))
    assert pi is None
    print("  blocked case → no interval  OK")


def test_sampled_curves_reproduce_the_published_95_cis():
    """Each sampled TM50 / Hill must land on the CI printed in its source, both tails."""
    rng = random.Random(1)
    for key, params in MATURATION.items():
        draws = [sample_curve(params, rng) for _ in range(40000)]
        for field, ci in (("tm50_weeks", params["tm50_ci95"]), ("hill", params["hill_ci95"])):
            if ci is None:  # nothing published: the parameter must stay at its point value
                assert all(d[field] == params[field] for d in draws), (key, field)
                continue
            xs = sorted(d[field] for d in draws)
            lo, med, hi = xs[int(0.025 * len(xs))], xs[len(xs) // 2], xs[int(0.975 * len(xs))]
            assert abs(lo / ci[0] - 1) < 0.01, (key, field, lo, ci)
            assert abs(hi / ci[1] - 1) < 0.01, (key, field, hi, ci)
            assert abs(med / params[field] - 1) < 0.01, (key, field, med, params[field])
    print("  sampled TM50/Hill reproduce published 95% CIs (both tails)  OK")


def test_absolute_daily_dose_also_gets_an_interval():
    pi = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    d, dk = pi["dose_mg_per_day"], pi["dose_mg_per_kg_per_day"]
    assert abs(d["p50"] / 3.5 - dk["p50"]) < 1e-9, (d, dk)
    assert pi["n_valid"] == pi["n_draws"]
    print("  absolute mg/day interval reported, all draws valid  OK")


def test_no_spread_means_no_variance_attribution():
    adult = dose_uncertainty_interval(weight_kg=70.0, age_years=40.0, **RENAL)
    assert adult["variance_share"] is None, adult["variance_share"]
    print("  adult (no spread) → no invented variance attribution  OK")


def test_caller_cannot_override_the_published_curves():
    try:
        dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, maturation={}, **RENAL)
    except TypeError:
        print("  maturation override rejected  OK")
        return
    raise AssertionError("maturation override must be rejected")


if __name__ == "__main__":
    print("Uncertainty layer (no API key):")
    test_interval_brackets_point_estimate_for_term_neonate()
    test_interval_narrows_as_maturation_completes()
    test_seeded_and_reproducible()
    test_sensitivity_attributes_variance_to_the_maturing_pathway()
    test_cmax_dose_is_volume_matched_so_dose_interval_is_degenerate()
    test_blocked_case_returns_none()
    test_sampled_curves_reproduce_the_published_95_cis()
    test_absolute_daily_dose_also_gets_an_interval()
    test_no_spread_means_no_variance_attribution()
    test_caller_cannot_override_the_published_curves()
    print("All uncertainty tests passed.")


def test_draws_past_a_safety_bound_are_counted_not_silently_dropped():
    point = compute_pediatric_dose(weight_kg=3.5, pma_weeks=42.0, **RENAL).recommended_dose_mg_per_kg_per_day
    free = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    bounded = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, toxic_dose_mg_per_kg_per_day=point * 1.05,
                                        effective_dose_mg_per_kg_per_day=point * 0.95, **RENAL)
    # the interval describes the engine dose, so a safety bound must not truncate it
    assert bounded["dose_mg_per_kg_per_day"] == free["dose_mg_per_kg_per_day"]
    assert bounded["n_valid"] == bounded["n_draws"]
    assert 0 < bounded["share_above_toxic"] < 0.5 and 0 < bounded["share_below_effective"] < 0.5
    assert free["share_above_toxic"] is None and free["share_below_effective"] is None


def test_interval_names_the_engine_point_estimate_it_surrounds():
    point = compute_pediatric_dose(weight_kg=3.5, pma_weeks=42.0, **RENAL).recommended_dose_mg_per_kg_per_day
    pi = dose_uncertainty_interval(weight_kg=3.5, pma_weeks=42.0, **RENAL)
    assert pi["engine_dose_mg_per_kg_per_day"] == point
    assert "engine dose" in pi["kind"]
