"""
Kidney function → renal organ-function modifier (OF).

The child's creatinine-based GFR is compared with the GFR the engine ALREADY expects for that
child's weight and PMA (Rhodin 2009: 121.2 mL/min/70 kg, WT^0.75, Anderson–Holford maturation),
so immaturity is not counted twice. Expected values below are worked by hand from the published
equations, not recomputed the way the code does.

Run:  python3 -m pytest -q tests/test_renal.py
"""

import pytest

from engine.pk_engine import assess_renal_function


def test_healthy_term_neonate_is_not_double_penalised_for_immaturity():
    # Term neonate, 14 days old, 3.8 kg, 52 cm, SCr 0.35 mg/dL (normal for age).
    # Smeets 2022 neonatal Schwartz: eGFR = 0.31 * 52 / 0.35 = 46.1 mL/min/1.73 m^2.
    # Mosteller BSA = sqrt(52 * 3.8 / 3600) = 0.2343 m^2 -> 6.24 mL/min absolute.
    # Expected for 3.8 kg at PMA 42 wk: 121.2 * (3.8/70)^0.75 * MF(42) = 5.36 mL/min.
    # Ratio ~1.16 -> OF capped at 1.0. The old fixed-100 comparison gave 0.46.
    r = assess_renal_function(
        weight_kg=3.8, height_cm=52, serum_creatinine_mg_dl=0.35,
        gestational_age_weeks=40, postnatal_age_weeks=2,
    )
    assert r.schwartz_k == pytest.approx(0.31)
    assert r.egfr_ml_min_1_73m2 == pytest.approx(46.1, abs=0.2)
    assert r.gfr_ml_min == pytest.approx(6.24, abs=0.05)
    assert r.expected_gfr_ml_min == pytest.approx(5.36, abs=0.05)
    assert r.gfr_ratio == pytest.approx(1.16, abs=0.02)
    assert r.renal_function_fraction == 1.0


def test_school_age_child_with_raised_creatinine_gets_renal_clearance_cut():
    # 6 y, 20 kg, 120 cm, SCr 1.5: bedside Schwartz 0.413*120/1.5 = 33.0 mL/min/1.73 m^2.
    # BSA sqrt(120*20/3600) = 0.8165 -> 15.6 mL/min. Expected 121.2*(20/70)^0.75*MF(352) = 47.3.
    r = assess_renal_function(
        weight_kg=20, height_cm=120, serum_creatinine_mg_dl=1.5, age_years=6,
    )
    assert r.schwartz_k == pytest.approx(0.413)
    assert r.egfr_ml_min_1_73m2 == pytest.approx(33.0, abs=0.1)
    assert r.expected_gfr_ml_min == pytest.approx(47.3, abs=0.2)
    assert r.renal_function_fraction == pytest.approx(0.33, abs=0.01)


def test_preterm_neonate_abstains_no_cited_coefficient():
    # GA 30 wk, 1 wk old: neither Schwartz 2009 (ages 1-16) nor Smeets 2022 (term-born) covers it.
    r = assess_renal_function(
        weight_kg=1.4, height_cm=39, serum_creatinine_mg_dl=0.9,
        gestational_age_weeks=30, postnatal_age_weeks=1,
    )
    assert r.egfr_ml_min_1_73m2 is None and r.gfr_ratio is None
    assert r.renal_function_fraction == 1.0
    assert any("preterm" in n.lower() for n in r.notes)


def test_infant_outside_schwartz_derivation_range_is_flagged():
    # 4 months: past the neonatal window, below the 1-16 y CKiD range -> bedside k, flagged.
    r = assess_renal_function(
        weight_kg=6.5, height_cm=63, serum_creatinine_mg_dl=0.3, age_years=4 / 12,
    )
    assert r.schwartz_k == pytest.approx(0.413)
    assert any("1-16" in n for n in r.notes)


def test_measured_gfr_above_expected_does_not_raise_the_dose_and_says_so():
    # 10 y, 32 kg, 138 cm, SCr 0.3: 0.413*138/0.3 = 190 mL/min/1.73 m^2 -> 121 mL/min,
    # ~1.8x the 67 mL/min expected. Starting dose is not increased; TDM is advised.
    r = assess_renal_function(
        weight_kg=32, height_cm=138, serum_creatinine_mg_dl=0.3, age_years=10,
    )
    assert r.gfr_ratio == pytest.approx(1.8, abs=0.05)
    assert r.renal_function_fraction == 1.0
    assert any("augmented" in n.lower() and "TDM" in n for n in r.notes)


def test_first_days_after_birth_creatinine_caveat():
    r = assess_renal_function(
        weight_kg=3.4, height_cm=50, serum_creatinine_mg_dl=0.8,
        gestational_age_weeks=39, postnatal_age_weeks=2 / 7,
    )
    assert r.schwartz_k == pytest.approx(0.31)
    assert any("maternal" in n.lower() for n in r.notes)


def test_missing_labs_means_nothing_to_assess():
    assert assess_renal_function(weight_kg=20, height_cm=None,
                                 serum_creatinine_mg_dl=1.0, age_years=6) is None
    assert assess_renal_function(weight_kg=20, height_cm=120,
                                 serum_creatinine_mg_dl=0, age_years=6) is None
