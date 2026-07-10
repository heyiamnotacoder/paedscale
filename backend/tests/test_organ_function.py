"""Unit tests for graded renal/hepatic function (app/pk/organ_function.py)."""

import pytest

from app.pk.organ_function import (
    BEDSIDE_SCHWARTZ_K,
    MIN_MODIFIER,
    child_pugh_class,
    hepatic_function_modifier,
    organ_modifiers,
    renal_function_modifier,
    schwartz_egfr,
)


def test_schwartz_egfr_formula():
    egfr = schwartz_egfr(height_cm=50.0, serum_creatinine_mg_dl=0.5)
    assert egfr == pytest.approx(BEDSIDE_SCHWARTZ_K * 50.0 / 0.5)


def test_schwartz_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        schwartz_egfr(50.0, 0.0)


def test_renal_modifier_clamped_between_floor_and_one():
    assert renal_function_modifier(200.0) == 1.0  # normal/high → no reduction
    assert renal_function_modifier(50.0) == pytest.approx(0.5)
    assert renal_function_modifier(0.0) == MIN_MODIFIER  # never zero


def test_child_pugh_class_boundaries():
    assert child_pugh_class(5) == "A"
    assert child_pugh_class(6) == "A"
    assert child_pugh_class(7) == "B"
    assert child_pugh_class(9) == "B"
    assert child_pugh_class(10) == "C"
    assert child_pugh_class(15) == "C"


def test_hepatic_modifier_decreases_with_severity():
    a = hepatic_function_modifier(5)
    b = hepatic_function_modifier(7)
    c = hepatic_function_modifier(12)
    assert a > b > c
    assert 0 < c < 1


def test_organ_modifiers_only_includes_supplied_organs():
    assert organ_modifiers() == {}
    mods = organ_modifiers(egfr_ml_min_1_73=50.0, child_pugh_score=7)
    assert set(mods) == {"renal", "hepatic"}
    assert mods["renal"] == pytest.approx(0.5)
    assert "renal" not in organ_modifiers(child_pugh_score=7)
