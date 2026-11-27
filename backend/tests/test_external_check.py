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


def test_an_absolute_adult_value_without_a_weight_needs_the_flag():
    abstract = "Title\n\nIn healthy adults aged 20-40 years clearance was 5.1 L/h."
    v = {"cl": {"value": 5.1, "unit": "L/h", "summary": "mean", "quote": "clearance was 5.1 L/h"},
         "weight_kg": None, "weight_quote": None, "age_quote": "aged 20-40 years", "flags": []}
    study = {"pmid": "3", "decision": "include", "reason": "", "flags": [], "values": [v]}
    assert check.study_problems(study, abstract, kind="adult")
    study["values"] = [{**v, "flags": ["adult_weight_missing"]}]
    assert check.study_problems(study, abstract, kind="adult") == []


def test_a_malformed_study_is_reported_not_raised():
    assert check.study_problems({"pmid": "4"}, "text", kind="pediatric")


def test_screening_past_a_stop_point_is_a_problem():
    from benchmark.external.curation import screening
    snap = {"pediatric": [{"pmid": "1", "prefilter": True}, {"pmid": "2", "prefilter": True}],
            "adult": [{"pmid": str(i), "prefilter": True} for i in range(10, 17)]}
    ped_order, ad_order = screening.order(snap["pediatric"]), screening.order(snap["adult"])
    one_ped = [{"pmid": ped_order[0], "decision": "exclude", "reason": "P1", "observations": []}]
    adult = [{"pmid": p, "decision": "exclude", "reason": "CL/F", "values": []} for p in ad_order[:1]]
    # adult screening began while a pediatric abstract was still unread and strata were open
    assert check.stop_problems({"pediatric": one_ped, "adult": adult}, snap)
    all_ped = one_ped + [{"pmid": ped_order[1], "decision": "exclude", "reason": "P1", "observations": []}]
    assert check.stop_problems({"pediatric": all_ped, "adult": adult}, snap) == []
    five = [{"pmid": p, "decision": "include", "reason": "", "values": []} for p in ad_order[:5]]
    extra = five + [{"pmid": ad_order[5], "decision": "exclude", "reason": "CL/F", "values": []}]
    assert check.stop_problems({"pediatric": all_ped, "adult": five}, snap) == []
    assert check.stop_problems({"pediatric": all_ped, "adult": extra}, snap)   # past five qualifying


def test_a_missing_record_file_is_a_problem(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "EXTRACTION_DIR", str(tmp_path))
    assert check.check_drug("nosuchpass", "vancomycin")
