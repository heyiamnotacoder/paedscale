"""Extraction records of the external validation: checks, strata and unit conversion."""
import pytest

from benchmark.external.curation import extraction as ex

ABSTRACT = ("Vancomycin in neonates.\n\nMETHODS: 40 neonates (postnatal age 3-20 days, "
            "gestational age 25-32 weeks, weight 1.2 kg).\nRESULTS: Clearance was 0.05 L/h/kg.")


def _obs(**kw):
    o = {"cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "Clearance was 0.05 L/h/kg"},
         "pna_days": [3, 20], "ga_weeks": [25, 32], "pma_weeks": None,
         "age_quote": "postnatal age 3-20 days, gestational age 25-32 weeks",
         "weight_kg": 1.2, "weight_quote": "weight 1.2 kg", "flags": []}
    o.update(kw)
    return o


def test_a_valid_observation_has_no_problems():
    assert ex.problems(_obs(), ABSTRACT) == []


def test_a_quote_not_in_the_abstract_is_a_problem():
    assert any("quote" in p for p in ex.problems(_obs(weight_quote="weight 1.4 kg"), ABSTRACT))


def test_a_value_missing_from_its_own_quote_is_a_problem():
    bad = _obs(cl={"value": 0.5, "unit": "L/h/kg", "summary": "mean", "quote": "Clearance was 0.05 L/h/kg"})
    assert any("0.5" in p for p in ex.problems(bad, ABSTRACT))


def test_an_unknown_unit_is_a_problem():
    bad = _obs(cl={"value": 0.05, "unit": "L/kg", "summary": "mean", "quote": "Clearance was 0.05 L/h/kg"})
    assert any("unit" in p for p in ex.problems(bad, ABSTRACT))


def test_strata_follow_ich_e11_from_the_central_postnatal_age():
    assert ex.stratum(pna_days=10, ga_weeks=30) == "preterm_newborn"
    assert ex.stratum(pna_days=10, ga_weeks=40) == "term_newborn"
    assert ex.stratum(pna_days=60, ga_weeks=30) == "infant_toddler"
    assert ex.stratum(pna_days=3 * 365.25, ga_weeks=40) == "child"
    assert ex.stratum(pna_days=14 * 365.25, ga_weeks=40) == "adolescent"


def test_central_values_use_the_geometric_midpoint_for_postnatal_age():
    assert ex.central([4, 16], geometric=True) == pytest.approx(8.0)
    assert ex.central([25, 33], geometric=False) == 29
    assert ex.central(12, geometric=True) == 12
    assert ex.central([0, 16], geometric=True) == pytest.approx(4.0)   # lower bound floored at 1 day


@pytest.mark.parametrize("value,unit,kw,expected", [
    (2.0, "L/h", {}, 2.0),
    (100, "mL/min", {}, 6.0),
    (0.1, "L/h/kg", {"weight_kg": 3}, 0.3),
    (2, "mL/min/kg", {"weight_kg": 10}, 1.2),
    (50, "mL/h/kg", {"weight_kg": 2}, 0.1),
    (8.0, "L/h/70kg", {"weight_kg": 70 / 16}, 1.0),            # 8 × (1/16)^0.75 = 1.0
    (86.5, "mL/min/1.73m2", {"weight_kg": 20, "bsa_m2": 0.865}, 86.5 * 0.06 * 0.5),
    (24, "L/day", {}, 1.0),
    (100, "mL/min/m2", {"weight_kg": 20, "bsa_m2": 0.8}, 100 * 0.06 * 0.8),   # Amendment 3
    (2.5, "L/h/m2", {"weight_kg": 20, "bsa_m2": 0.8}, 2.0),
])
def test_clearance_converts_to_litres_per_hour(value, unit, kw, expected):
    assert ex.to_l_per_h(value, unit, **kw) == pytest.approx(expected)
