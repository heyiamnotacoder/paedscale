"""Agreement between the two screening passes (PROTOCOL.md, Amendment 1 §9, Amendment 2 §8)."""
import pytest

from benchmark.external.curation import agreement as ag


def test_cohens_kappa():
    assert ag.kappa([("include", "include"), ("exclude", "exclude")]) == pytest.approx(1.0)
    pairs = [("include", "include")] * 20 + [("include", "exclude")] * 5 + \
            [("exclude", "include")] * 10 + [("exclude", "exclude")] * 15
    # po = 0.7; pe = 0.5*0.6 + 0.5*0.4 = 0.5
    assert ag.kappa(pairs) == pytest.approx(0.4)
    assert ag.kappa([("include", "include")]) is None          # no variation: undefined
    assert ag.kappa([]) is None


def _study(pmid, decision, obs=()):
    return {"pmid": pmid, "decision": decision, "reason": "" if decision == "include" else "P2: x",
            "flags": [], "observations": list(obs)}


def _o(v, unit="L/h/kg", pna=10, w=3.0):
    return {"cl": {"value": v, "unit": unit, "summary": "mean", "quote": "q"}, "pna_days": pna,
            "ga_weeks": None, "pma_weeks": None, "weight_kg": w, "preterm": False, "flags": []}


def test_compare_counts_only_abstracts_both_passes_read_and_lists_value_differences():
    r1 = {"pediatric": [_study("1", "include", [_o(0.1)]), _study("2", "exclude"), _study("3", "include", [_o(0.2)])],
          "adult": []}
    r2 = {"pediatric": [_study("1", "include", [_o(0.1)]), _study("2", "include", [_o(0.3)]),
                        _study("3", "include", [_o(0.25)]), _study("4", "exclude")], "adult": []}
    c = ag.compare(r1, r2)
    assert c["both_read"] == 3 and c["only_pass2"] == ["pediatric 4"]
    assert c["decision_disagreements"] == ["pediatric 2"]
    assert [d["pmid"] for d in c["value_disagreements"]] == ["3"]
    assert c["value_agreements"] == 1


def test_a_different_number_of_observations_is_a_value_disagreement():
    r1 = {"pediatric": [_study("1", "include", [_o(0.1), _o(0.2, pna=100)])], "adult": []}
    r2 = {"pediatric": [_study("1", "include", [_o(0.1)])], "adult": []}
    assert [d["pmid"] for d in ag.compare(r1, r2)["value_disagreements"]] == ["1"]
