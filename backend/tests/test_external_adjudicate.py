"""Building the final record from two passes and the adjudication log (PROTOCOL.md, Amendment 12 §9)."""
import pytest

from benchmark.external.curation import adjudicate as adj


def _s(pmid, decision, v=0.1):
    obs = [{"cl": {"value": v, "unit": "L/h", "summary": "mean", "quote": "q"}, "pna_days": 10,
            "preterm": False, "flags": []}] if decision == "include" else []
    return {"pmid": pmid, "decision": decision, "reason": "" if obs else "P2: none", "flags": [],
            "observations": obs}


SNAP = {"pediatric": [{"pmid": p, "prefilter": True} for p in ("1", "2", "3", "4")], "adult": []}
ORDER = ["1", "2", "3", "4"]


def test_agreed_decisions_are_kept_and_disagreements_need_a_logged_resolution():
    p1 = {"pediatric": [_s("1", "exclude"), _s("2", "include"), _s("3", "exclude")], "adult": []}
    p2 = {"pediatric": [_s("1", "exclude"), _s("2", "exclude"), _s("3", "exclude"), _s("4", "exclude")], "adult": []}
    final, unresolved = adj.build(p1, p2, {}, ORDER, [], stop=lambda rec, kind: False)
    assert [s["pmid"] for s in final["pediatric"]] == ["1", "2", "3", "4"]      # provisional past a gap
    assert unresolved == [("pediatric", "2", "decisions differ"), ("pediatric", "4", "read by pass2 only")]
    log = {"pediatric": {"2": {"use": "pass2", "reason": "P2: renal clearance only"},
                         "4": {"use": "pass2", "reason": "re-read: no clearance"}}}
    final, unresolved = adj.build(p1, p2, log, ORDER, [], stop=lambda rec, kind: False)
    assert unresolved == []
    assert [(s["pmid"], s["decision"]) for s in final["pediatric"]] == [
        ("1", "exclude"), ("2", "exclude"), ("3", "exclude"), ("4", "exclude")]


def test_value_differences_and_single_pass_abstracts_are_unresolved():
    p1 = {"pediatric": [_s("1", "include", 0.1), _s("2", "exclude")], "adult": []}
    p2 = {"pediatric": [_s("1", "include", 0.2)], "adult": []}
    _, unresolved = adj.build(p1, p2, {}, ORDER, [], stop=lambda rec, kind: False)
    assert unresolved[:2] == [("pediatric", "1", "values differ"), ("pediatric", "2", "read by pass1 only")]
    _, unresolved = adj.build(p1, p2, {"pediatric": {"1": {"use": "pass1", "reason": "r"}}}, ORDER, [],
                              stop=lambda rec, kind: False)
    assert unresolved[0] == ("pediatric", "2", "read by pass1 only")


def test_an_adjudicator_record_overrides_an_agreed_decision():
    p1 = {"pediatric": [_s("1", "include")], "adult": []}
    own = _s("1", "exclude") | {"reason": "P2: single-patient report (Amendment 14 §3)"}
    final, unresolved = adj.build(p1, p1, {"pediatric": {"1": {"record": own, "reason": "A14 §3"}}},
                                  ["1"], [], stop=lambda rec, kind: False)
    assert unresolved == [] and final["pediatric"][0]["decision"] == "exclude"


def test_building_stops_where_the_final_queue_stops():
    p1 = {"pediatric": [_s("1", "exclude"), _s("2", "exclude")], "adult": []}
    final, unresolved = adj.build(p1, p1, {}, ORDER, [], stop=lambda rec, kind: len(rec["pediatric"]) >= 2)
    assert [s["pmid"] for s in final["pediatric"]] == ["1", "2"] and unresolved == []


def test_an_abstract_neither_pass_read_needs_the_adjudicator():
    p1 = {"pediatric": [_s("1", "exclude")], "adult": []}
    _, unresolved = adj.build(p1, p1, {}, ORDER, [], stop=lambda rec, kind: False)
    assert unresolved == [("pediatric", "2", "read by neither pass")]
