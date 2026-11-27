"""Scoring of the external validation (benchmark/external/PROTOCOL.md, Amendment 12)."""
import math

import pytest

from benchmark.external import score as sc
from benchmark.growth import median_weight_kg


def _obs(**kw):
    o = {"cl": {"value": 0.1, "unit": "L/h/kg", "summary": "mean", "quote": "q"},
         "pna_days": 100, "ga_weeks": None, "pma_weeks": None, "weight_kg": 6.0, "bsa_m2": None,
         "height_cm": None, "preterm": False, "flags": []}
    o.update(kw)
    return o


def _adult(value, unit="L/h", weight=None, flags=()):
    return {"cl": {"value": value, "unit": unit, "summary": "mean", "quote": "q"},
            "weight_kg": weight, "age_years": None, "flags": list(flags)}


def test_adult_reference_is_the_median_of_abstract_medians_at_70kg():
    studies = [
        {"pmid": "1", "decision": "include", "flags": [], "values": [_adult(0.1, "L/h/kg")]},           # 7
        {"pmid": "2", "decision": "exclude", "flags": [], "values": []},
        {"pmid": "3", "decision": "include", "flags": [],
         "values": [_adult(5.0, "L/h", weight=70), _adult(7.0, "L/h", weight=70)]},                    # 6
        {"pmid": "4", "decision": "include", "flags": [], "values": [_adult(4.0, "L/h", weight=80)]},  # 4*(70/80)^.75
        {"pmid": "5", "decision": "include", "flags": [], "values": [_adult(150, "mL/min")]},          # 9
    ]
    ref = sc.adult_reference(studies)
    assert ref["per_abstract_l_h"] == pytest.approx([7.0, 6.0, 4 * (70 / 80) ** 0.75, 9.0])
    assert ref["median_l_h"] == pytest.approx(6.5)
    assert ref["first_l_h"] == pytest.approx(7.0)                    # E4
    assert ref["n_abstracts"] == 4


def test_adult_reference_uses_at_most_the_first_five_qualifying_abstracts():
    studies = [{"pmid": str(i), "decision": "include", "flags": [], "values": [_adult(float(i))]}
               for i in range(1, 8)]
    assert sc.adult_reference(studies)["median_l_h"] == 3.0


def test_observed_clearance_uses_the_stated_weight_and_flags_imputed_weight():
    o = sc.observed(_obs())
    assert o["cl_l_h"] == pytest.approx(0.6) and "weight_imputed" not in o["flags"]
    o = sc.observed(_obs(weight_kg=None))
    w = median_weight_kg(100, 40)
    assert o["cl_l_h"] == pytest.approx(0.1 * w) and "weight_imputed" in o["flags"]


def test_per_bsa_values_use_a_stated_bsa_then_mosteller_then_costeff():
    base = dict(cl={"value": 50, "unit": "mL/min/1.73m2", "summary": "mean", "quote": "q"})
    assert sc.observed(_obs(bsa_m2=0.5, **base))["cl_l_h"] == pytest.approx(50 * 0.06 * 0.5 / 1.73)
    mos = math.sqrt(60 * 6 / 3600)
    o = sc.observed(_obs(height_cm=60, **base))
    assert o["cl_l_h"] == pytest.approx(50 * 0.06 * mos / 1.73) and "bsa_costeff" not in o["flags"]
    o = sc.observed(_obs(**base))
    assert o["cl_l_h"] == pytest.approx(50 * 0.06 * (4 * 6 + 7) / (6 + 90) / 1.73) and "bsa_costeff" in o["flags"]


def test_the_grid_spans_the_postnatal_range_log_spaced_with_growth_weights():
    pts = sc.grid(_obs(pna_days=[10, 1000], weight_kg=None))
    assert len(pts) == 7
    assert pts[0]["pna_days"] == pytest.approx(10) and pts[-1]["pna_days"] == pytest.approx(1000)
    assert pts[3]["pna_days"] == pytest.approx(100)
    assert pts[3]["weight_kg"] == pytest.approx(median_weight_kg(100, 40))
    assert pts[3]["pma_weeks"] == pytest.approx(40 + 100 / 7)
    assert sc.grid(_obs(pna_days=[0, 30], weight_kg=3.0))[0]["pna_days"] == pytest.approx(1)  # floored
    assert all(p["weight_kg"] == 3.0 for p in sc.grid(_obs(pna_days=[0, 30], weight_kg=3.0)))


def test_a_stated_pma_is_used_directly_and_its_range_is_the_grid():
    pts = sc.grid(_obs(pna_days=None, pma_weeks=34, pma_range_weeks=[28, 40], weight_kg=None, preterm=True))
    assert pts[0]["pma_weeks"] == pytest.approx(28) and pts[-1]["pma_weeks"] == pytest.approx(40)
    one = sc.grid(_obs(pna_days=14, pma_weeks=33, weight_kg=1.5))
    assert len(one) == 1 and one[0]["pma_weeks"] == 33 and one[0]["weight_kg"] == 1.5


def test_methods_scale_the_adult_clearance_as_the_protocol_table_says():
    p = {"weight_kg": 7.0, "pma_weeks": 60.0, "pna_days": 140.0}
    drug = {"fe": {"value": 1.0}, "nonrenal_enzyme": None}
    assert sc.predict_point("weight_linear", 7.0, drug, p) == pytest.approx(0.7)
    assert sc.predict_point("allometry", 7.0, drug, p) == pytest.approx(7 * 0.1 ** 0.75)
    bsa = lambda w: (4 * w + 7) / (w + 90)
    assert sc.predict_point("bsa", 7.0, drug, p) == pytest.approx(7 * bsa(7) / bsa(70))
    ps = sc.predict_point("paedscale", 7.0, drug, p)
    assert 0 < ps < sc.predict_point("allometry", 7.0, drug, p)       # renal maturation < 1 at 60 wk


def test_prediction_is_the_geometric_mean_over_the_grid():
    drug = {"fe": {"value": 1.0}, "nonrenal_enzyme": None}
    o = _obs(pna_days=[100, 400], weight_kg=None)
    vals = [sc.predict_point("allometry", 7.0, drug, p) for p in sc.grid(o)]
    assert sc.predict("allometry", 7.0, drug, o) == pytest.approx(math.exp(sum(map(math.log, vals)) / 7))


def test_exact_sign_flip_p_value():
    # all positive: only the identity and the all-flipped assignment are as extreme
    assert sc.sign_flip_p([0.1, 0.2, 0.3]) == pytest.approx(2 / 8)
    assert sc.sign_flip_p([0.1, -0.1]) == pytest.approx(1.0)
    assert sc.sign_flip_p([]) is None


def test_hypothesis_needs_eight_drugs_to_be_confirmatory_and_an_upper_bound_below_zero():
    rows = []
    for i in range(8):
        for m, fe in (("paedscale", 1.1), ("allometry", 2.0)):
            rows.append({"drug": f"d{i}", "pmid": "1", "obs": 0, "method": m, "fe": fe * (1 + i / 100),
                         "stratum": "term_newborn", "under2": True})
    h = sc.hypothesis(rows, n_boot=200)
    assert h["n_drugs"] == 8 and h["confirmatory"] and h["ci95"][1] < 0 and h["success"]
    h = sc.hypothesis([r for r in rows if r["drug"] != "d0"], n_boot=200)
    assert not h["confirmatory"] and not h["success"]


def test_study_weighting_gives_each_study_equal_weight_within_a_drug():
    rows = [{"drug": "a", "pmid": "1", "d": 1.0}, {"drug": "a", "pmid": "1", "d": 1.0},
            {"drug": "a", "pmid": "2", "d": 0.0}]
    assert sc.drug_mean_d(rows) == pytest.approx(2 / 3)
    assert sc.drug_mean_d(rows, by_study=True) == pytest.approx(0.5)
