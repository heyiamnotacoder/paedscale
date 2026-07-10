"""Unit tests for the safety-bounds check (app/pk/safety.py)."""

from app.pk.safety import check_bounds


def test_within_bounds_passes_unchanged():
    r = check_bounds(dose_mg_per_kg=10.0, min_effective_mg_per_kg=5.0, max_safe_mg_per_kg=15.0)
    assert r.within is True
    assert r.flag is None
    assert r.clamped_mg_per_kg == 10.0


def test_above_max_is_clamped_down_and_flagged():
    r = check_bounds(20.0, min_effective_mg_per_kg=5.0, max_safe_mg_per_kg=15.0)
    assert r.within is False
    assert r.clamped_mg_per_kg == 15.0
    assert "exceeds the maximum safe dose" in r.flag


def test_below_min_is_clamped_up_and_flagged():
    r = check_bounds(2.0, min_effective_mg_per_kg=5.0, max_safe_mg_per_kg=15.0)
    assert r.within is False
    assert r.clamped_mg_per_kg == 5.0
    assert "below the minimum effective dose" in r.flag


def test_missing_bounds_are_not_checked():
    r = check_bounds(1000.0, min_effective_mg_per_kg=None, max_safe_mg_per_kg=None)
    assert r.within is True
    assert r.clamped_mg_per_kg == 1000.0
