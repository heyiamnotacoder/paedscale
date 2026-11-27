"""The record checker for a screening pass."""
from benchmark.external.curation import check


def test_decisions_must_follow_the_seeded_order_without_gaps():
    order = ["5", "2", "9"]
    assert check.order_problems(["5", "2"], order) == []
    assert check.order_problems(["5", "9"], order)          # skipped 2
    assert check.order_problems(["2", "5"], order)          # out of order


def test_every_included_study_needs_valid_observations():
    abstract = "Title\n\nRESULTS: Clearance was 0.1 L/h/kg at a median age of 5 days in term neonates."
    good = {"pmid": "1", "decision": "include", "reason": "", "flags": [], "observations": [
        {"cl": {"value": 0.1, "unit": "L/h/kg", "summary": "median", "quote": "Clearance was 0.1 L/h/kg"},
         "pna_days": 5, "ga_weeks": None, "pma_weeks": None, "age_quote": "median age of 5 days",
         "weight_kg": None, "weight_quote": None, "flags": []}]}
    assert check.study_problems(good, abstract, kind="pediatric") == []
    empty = {**good, "observations": []}
    assert check.study_problems(empty, abstract, kind="pediatric")
    excl = {"pmid": "2", "decision": "exclude", "reason": "", "flags": [], "observations": []}
    assert check.study_problems(excl, abstract, kind="pediatric")      # an exclusion needs a reason


def test_an_adult_value_with_no_stated_age_passes_when_flagged():
    abstract = "Title\n\nIn healthy volunteers clearance was 5.1 L/h."
    study = {"pmid": "3", "decision": "include", "reason": "", "flags": [], "values": [
        {"cl": {"value": 5.1, "unit": "L/h", "summary": "mean", "quote": "clearance was 5.1 L/h"},
         "weight_kg": None, "weight_quote": None, "age_quote": None,
         "flags": ["adult_weight_missing", "adult_age_unstated"]}]}
    assert check.study_problems(study, abstract, kind="adult") == []
    unflagged = {**study, "values": [{**study["values"][0], "flags": ["adult_weight_missing"]}]}
    assert check.study_problems(unflagged, abstract, kind="adult")


def test_the_queue_moves_to_adult_abstracts_when_the_pediatric_list_runs_out():
    from benchmark.external.curation import screening
    snap = {"pediatric": [{"pmid": "1", "prefilter": True}],
            "adult": [{"pmid": "7", "prefilter": True}, {"pmid": "8", "prefilter": True}]}
    rec = {"pediatric": [{"pmid": "1", "decision": "exclude", "reason": "P4", "observations": []}], "adult": []}
    kind, todo = screening.next_up(snap, rec)
    assert kind == "adult" and sorted(todo) == ["7", "8"]
    rec["adult"] = [{"pmid": p, "decision": "exclude", "reason": "CL/F"} for p in todo]
    assert screening.next_up(snap, rec) == (None, [])
