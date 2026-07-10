"""Unit tests for the multi-method dose engine (app/pk/methods.py)."""

import math

import pytest

from app.pk.methods import (
    solve,
    solve_auc,
    solve_cmax,
    solve_css,
    solve_loading,
    solve_mgkg_linear,
    solve_trough,
)


def test_auc_reproduces_exposure_ratio():
    rec = solve_auc(
        adult_reference_dose_mg=1000.0,
        adult_clearance_l_per_h=4.0,
        adult_interval_h=12.0,
        child_clearance_l_per_h=1.0,
        weight_kg=5.0,
    )
    # Dose = 1000 * (1/4) * (12/12) = 250
    assert rec.dose_mg == pytest.approx(250.0)
    assert rec.dose_mg_per_kg == pytest.approx(50.0)
    assert rec.interval_h == 12.0
    assert rec.method == "auc"


def test_auc_scales_with_child_interval():
    rec = solve_auc(1000.0, 4.0, 12.0, 1.0, 5.0, child_interval_h=6.0)
    assert rec.dose_mg == pytest.approx(125.0)  # half the interval → half the dose
    assert rec.interval_h == 6.0


def test_css_dose_is_clearance_times_target_times_interval():
    rec = solve_css(css_target_mg_per_l=10.0, child_clearance_l_per_h=2.0, interval_h=8.0, weight_kg=4.0)
    assert rec.dose_mg == pytest.approx(160.0)
    assert rec.dose_mg_per_kg == pytest.approx(40.0)


def test_cmax_uses_volume_not_clearance():
    rec = solve_cmax(cmax_target_mg_per_l=8.0, child_volume_l=2.5, weight_kg=5.0)
    assert rec.dose_mg == pytest.approx(20.0)
    assert rec.method == "cmax"


def test_loading_fills_volume_to_target():
    rec = solve_loading(c_target_mg_per_l=20.0, child_volume_l=3.0, weight_kg=6.0)
    assert rec.dose_mg == pytest.approx(60.0)
    assert rec.dose_mg_per_kg == pytest.approx(10.0)


def test_trough_accounts_for_elimination_over_interval():
    cl, vd, tau, ctrough = 1.0, 4.0, 8.0, 5.0
    rec = solve_trough(ctrough, cl, vd, tau, weight_kg=4.0)
    expected = ctrough * vd * math.exp((cl / vd) * tau)
    assert rec.dose_mg == pytest.approx(expected)
    assert rec.dose_mg > ctrough * vd  # must exceed a plain loading dose


def test_mgkg_linear_is_naive_weight_scaling():
    rec = solve_mgkg_linear(adult_reference_dose_mg=700.0, weight_kg=7.0, adult_weight_kg=70.0)
    assert rec.dose_mg == pytest.approx(70.0)
    assert rec.dose_mg_per_kg == pytest.approx(10.0)


def test_dispatch_and_unknown_method():
    rec = solve("cmax", cmax_target_mg_per_l=8.0, child_volume_l=2.5, weight_kg=5.0)
    assert rec.dose_mg == pytest.approx(20.0)
    with pytest.raises(ValueError):
        solve("nonsense", weight_kg=1.0)
