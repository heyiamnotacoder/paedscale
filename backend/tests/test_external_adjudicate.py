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


def test_a_log_entry_needs_a_reason_and_a_record_must_be_for_its_own_pmid():
    p1 = {"pediatric": [_s("1", "include", 0.1)], "adult": []}
    p2 = {"pediatric": [_s("1", "include", 0.2)], "adult": []}
    run = lambda log: adj.build(p1, p2, {"pediatric": {"1": log}}, ["1"], [], stop=lambda r, k: False)[1]
    assert run({"use": "pass2"}) == [("pediatric", "1", "log entry has no reason")]
    assert run({"record": _s("999", "exclude"), "reason": "r"}) == [
        ("pediatric", "1", "log record is for PMID '999'")]
    assert run({"use": "pass2", "reason": "re-read"}) == []


def test_the_final_record_is_written_only_when_nothing_is_unresolved(tmp_path):
    p1 = {"pediatric": [_s("1", "include", 0.1)], "adult": []}
    p2 = {"pediatric": [_s("1", "include", 0.2)], "adult": []}
    out = tmp_path / "final"
    snap = {"pediatric": [{"pmid": "1", "prefilter": True}], "adult": []}
    assert adj.write_final({"d": (p1, p2, {})}, {"d": snap}, str(out)) == ["d pediatric 1: values differ"]
    assert not out.exists()
    log = {"pediatric": {"1": {"use": "pass1", "reason": "re-read"}}}
    assert adj.write_final({"d": (p1, p2, log)}, {"d": snap}, str(out)) == []
    assert (out / "d.json").exists()


def test_a_log_entry_the_final_queue_never_reaches_is_reported():
    p1 = {"pediatric": [_s("1", "exclude")], "adult": []}
    log = {"pediatric": {"1": {"use": "pass1", "reason": "r"}, "7": {"use": "pass1", "reason": "typo"}}}
    _, unresolved = adj.build(p1, p1, log, ["1"], [], stop=lambda r, k: False)
    assert unresolved == [("pediatric", "7", "log entry is never reached by the final queue")]


def test_a_use_entry_for_a_pass_that_did_not_read_it_keeps_listing_later_items():
    p1 = {"pediatric": [_s("1", "exclude"), _s("2", "include", 0.1)], "adult": []}
    p2 = {"pediatric": [_s("2", "include", 0.2)], "adult": []}
    log = {"pediatric": {"1": {"use": "pass2", "reason": "r"}}}
    _, unresolved = adj.build(p1, p2, log, ["1", "2"], [], stop=lambda r, k: False)
    assert [u[1] for u in unresolved] == ["1", "2"]
    assert adj.build(p1, p2, {"pediatric": {"1": {"record": [1], "reason": "r"}}}, ["1"], [],
                     stop=lambda r, k: False)[1][0][2].startswith("log record is for PMID")


def test_a_failed_run_leaves_no_final_record_behind(tmp_path):
    p1 = {"pediatric": [_s("1", "include", 0.1)], "adult": []}
    p2 = {"pediatric": [_s("1", "include", 0.2)], "adult": []}
    snap = {"pediatric": [{"pmid": "1", "prefilter": True}], "adult": []}
    out = tmp_path / "final"
    out.mkdir()
    (out / "old.json").write_text("{}")
    assert adj.write_final({"d": (p1, p2, {})}, {"d": snap}, str(out))
    assert list(out.iterdir()) == []


def test_an_empty_log_entry_is_not_silently_ignored():
    p1 = {"pediatric": [_s("1", "include", 0.1)], "adult": []}
    _, unresolved = adj.build(p1, p1, {"pediatric": {"1": {}}}, ["1"], [], stop=lambda r, k: False)
    assert unresolved == [("pediatric", "1", "log entry has no reason")]
