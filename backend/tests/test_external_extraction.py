"""Extraction records of the external validation: checks, strata and unit conversion."""
import pytest

from benchmark.external.curation import extraction as ex

ABSTRACT = ("Vancomycin in neonates.\n\nMETHODS: 40 neonates (postnatal age 3-20 days, "
            "gestational age 25-32 weeks, weight 1.2 kg).\nRESULTS: Clearance was 0.05 L/h/kg.")


def _obs(**kw):
    o = {"preterm": True,
         "cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "Clearance was 0.05 L/h/kg"},
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
    (500, "mL/h", {}, 0.5),                                      # Amendment 4
    (0.05, "L/min", {}, 3.0),
    (2.4, "L/day/kg", {"weight_kg": 10}, 1.0),
    (100, "mL/h/1.73m2", {"weight_kg": 20, "bsa_m2": 0.865}, 0.05),
    (100, "mL/min/m2", {"weight_kg": 20, "bsa_m2": 0.8}, 100 * 0.06 * 0.8),   # Amendment 3
    (2.5, "L/h/m2", {"weight_kg": 20, "bsa_m2": 0.8}, 2.0),
])
def test_clearance_converts_to_litres_per_hour(value, unit, kw, expected):
    assert ex.to_l_per_h(value, unit, **kw) == pytest.approx(expected)


def test_flags_must_come_from_the_protocol_list():
    assert ex.problems(_obs(flags=["critically_ill", "pca_as_pma"]), ABSTRACT) == []
    assert any("flag" in p for p in ex.problems(_obs(flags=["sick"]), ABSTRACT))
    assert any("flag" in p for p in ex.problems(_obs(flags=["weight_imputed"]), ABSTRACT))   # the scorer adds it


def test_a_stated_age_range_beside_a_central_age_is_kept_and_checked():
    o = _obs(pna_days=8, pna_range_days=[3, 20])
    assert ex.problems(o, ABSTRACT) == []
    assert ex.problems(_obs(pna_days=8, pna_range_days=[20, 3]), ABSTRACT)
    assert ex.age_range(o, "pna") == [3, 20] and ex.age_range(_obs(pna_days=8), "pna") is None
    assert ex.age_range(_obs(), "pna") == [3, 20]


def test_gestational_age_defaults_to_40_weeks_or_32_when_described_as_preterm():
    assert ex.gestational_weeks({"ga_weeks": [25, 33]}) == 29
    assert ex.gestational_weeks({"ga_weeks": None}) == 40
    assert ex.gestational_weeks({"ga_weeks": None, "preterm": True}) == 32


@pytest.mark.parametrize("field,value", [("pna_days", "12"), ("pna_days", -5), ("pma_weeks", [30]),
                                         ("ga_weeks", "30")])
def test_a_malformed_age_is_a_problem(field, value):
    assert any(field in p for p in ex.problems(_obs(**{field: value}), ABSTRACT))


def test_a_central_age_outside_its_stated_range_is_a_problem():
    assert ex.problems(_obs(pna_days=50, pna_range_days=[3, 20]), ABSTRACT)


def test_gestational_age_cannot_exceed_the_stated_pma():
    assert ex.gestational_weeks({"ga_weeks": None, "pma_weeks": 30}) == 30
    assert ex.gestational_weeks({"ga_weeks": None, "pma_weeks": 60}) == 40


def test_adult_and_pediatric_flags_are_separate():
    assert ex.flag_problems(["adult_weight_missing"], "adult") == []
    assert ex.flag_problems(["pca_as_pma"], "adult")
    assert ex.flag_problems(["adult_age_unstated"], "pediatric")


def test_ga_is_pma_minus_postnatal_age_when_both_are_stated():
    assert ex.gestational_weeks({"ga_weeks": None, "pma_weeks": 32, "pna_days": 14}) == 30


def test_a_per_70kg_value_needs_its_flag_and_an_age_that_fixes_maturation():
    o = _obs(cl={"value": 0.05, "unit": "L/h/70kg", "summary": "typical", "quote": "Clearance was 0.05 L/h/kg"})
    found = ex.problems(o, ABSTRACT)
    assert any("allometric_standardized" in p for p in found)
    assert ex.problems({**o, "flags": ["allometric_standardized"]}, ABSTRACT) == []      # PNA with GA
    assert any("age it applies" in p for p in ex.problems(
        {**o, "flags": ["allometric_standardized"], "ga_weeks": None}, ABSTRACT))


def test_a_weight_range_and_a_quoted_bsa_are_accepted():
    text = ABSTRACT + " Weight 1.0-1.5 kg, BSA 0.12 m2."
    assert ex.problems(_obs(weight_kg=[1.0, 1.5], weight_quote="Weight 1.0-1.5 kg",
                            bsa_m2=0.12, bsa_quote="BSA 0.12 m2"), text) == []
    assert ex.problems(_obs(bsa_m2=0.12, bsa_quote=None), text)


def test_a_per_70kg_value_from_2_years_needs_the_whole_age_range_past_2_years():
    o = {**_obs(cl={"value": 0.05, "unit": "L/h/70kg", "summary": "typical", "quote": "Clearance was 0.05 L/h/kg"}),
         "flags": ["allometric_standardized"], "ga_weeks": None}
    assert ex.age_fixes_maturation({**o, "pna_days": 3 * 365.25})
    assert not ex.age_fixes_maturation({**o, "pna_days": [365.25, 5 * 365.25]})      # grid reaches 1 year
    assert not ex.age_fixes_maturation({**o, "pna_days": 800, "pna_range_days": [365.25, 1200]})


def test_a_truncated_number_does_not_match_its_quote():
    assert not ex._number_in(5, "clearance was 5.1 L/h")
    assert ex._number_in(5.1, "clearance was 5.1 L/h.")


def test_preterm_must_be_a_boolean_and_pma_must_agree_with_postnatal_age():
    assert any("preterm" in p for p in ex.problems(_obs(preterm="false"), ABSTRACT))
    assert any("imply a GA" in p for p in ex.problems(_obs(pma_weeks=30, pna_days=400, ga_weeks=None), ABSTRACT))


def test_ga_from_pma_subtracts_arithmetic_midpoints():
    assert ex.gestational_weeks({"ga_weeks": None, "pma_weeks": 40, "pna_days": [1, 121]}) == pytest.approx(40 - 61 / 7)
    wide = _obs(pma_weeks=[26, 100], pna_days=[1, 500], ga_weeks=None, preterm=True)
    assert not any("imply a GA" in p for p in ex.problems(wide, ABSTRACT))


def test_every_pediatric_observation_says_whether_the_group_is_preterm():
    o = _obs()
    del o["preterm"]
    assert any("preterm" in p for p in ex.problems(o, ABSTRACT))
