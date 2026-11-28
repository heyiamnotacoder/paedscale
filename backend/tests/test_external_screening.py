"""Screening order and caps of the external validation (PROTOCOL.md, Amendments 1-4)."""
import random

from benchmark.external.curation import screening


def test_order_is_the_seeded_shuffle_of_numerically_sorted_prefiltered_pmids():
    rows = [{"pmid": "100", "prefilter": True}, {"pmid": "20", "prefilter": True},
            {"pmid": "3", "prefilter": False}, {"pmid": "4000", "prefilter": True}]
    expected = ["20", "100", "4000"]
    random.Random(20261127).shuffle(expected)
    assert screening.order(rows) == expected


def test_the_adult_list_closes_after_five_qualifying_abstracts():
    decisions = [{"pmid": str(i), "decision": "include"} for i in range(5)]
    assert screening.adult_open(decisions[:4]) and not screening.adult_open(decisions)


def test_replay_uses_only_observations_in_strata_that_were_open_when_the_study_was_read():
    from benchmark.external.curation import extraction as ex
    def obs(pna, ga=40):
        return {"pna_days": pna, "ga_weeks": ga}
    record = {"pediatric": [
        {"pmid": "1", "decision": "include", "observations": [obs(10), obs(400)]},
        {"pmid": "2", "decision": "include", "observations": [obs(12)]},
        {"pmid": "3", "decision": "include", "observations": [obs(14), obs(500)]},   # term full by now
    ]}
    used = screening.replay(record)
    assert [(u["pmid"], ex.stratum(u["obs"]["pna_days"], 40)) for u in used] == [
        ("1", "term_newborn"), ("1", "infant_toddler"), ("2", "term_newborn"), ("3", "infant_toddler")]


def test_a_group_described_as_preterm_without_a_ga_is_a_preterm_newborn():
    record = {"pediatric": [{"pmid": "1", "decision": "include", "observations": [
        {"pna_days": None, "ga_weeks": None, "pma_weeks": [24, 34], "preterm": True}]}]}
    assert [u["stratum"] for u in screening.replay(record)] == ["preterm_newborn"]


def test_replay_skips_an_observation_with_no_age_instead_of_crashing():
    record = {"pediatric": [{"pmid": "1", "decision": "include", "observations": [
        {"pna_days": None, "ga_weeks": 30, "pma_weeks": None}]}]}
    assert screening.replay(record) == []


def test_the_queue_moves_to_adult_abstracts_once_every_stratum_is_full():
    ages = [5, 5, 60, 3 * 365, 14 * 365]
    snap = {"pediatric": [{"pmid": str(i), "prefilter": True} for i in range(1, 12)],
            "adult": [{"pmid": "90", "prefilter": True}]}
    first_ten = screening.order(snap["pediatric"])[:10]
    studies = [{"pmid": p, "decision": "include", "observations": [
        {"pna_days": ages[i // 2], "ga_weeks": 30 if i < 2 else 40, "pma_weeks": None}]}
        for i, p in enumerate(first_ten)]
    assert screening.next_up(snap, {"pediatric": studies, "adult": []}) == ("adult", ["90"])


def test_next_shows_only_an_abstract_that_matches_its_committed_hash(tmp_path, monkeypatch):
    import hashlib
    import pytest
    from benchmark.external.curation import screening as sc
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "1.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "d" / "2.txt").write_text("changed", encoding="utf-8")
    snap = {"pediatric": [{"pmid": "1", "sha256": hashlib.sha256(b"ok").hexdigest()},
                          {"pmid": "2", "sha256": hashlib.sha256(b"orig").hexdigest()}], "adult": []}
    assert sc.snapshot_text(str(tmp_path), "d", "1", snap) == "ok"
    with pytest.raises(SystemExit, match="2"):
        sc.snapshot_text(str(tmp_path), "d", "2", snap)
