"""Screening order and caps of the external validation (PROTOCOL.md, Amendments 1-2)."""
import random

from benchmark.external.curation import screening


def test_order_is_the_seeded_shuffle_of_numerically_sorted_prefiltered_pmids():
    rows = [{"pmid": "100", "prefilter": True}, {"pmid": "20", "prefilter": True},
            {"pmid": "3", "prefilter": False}, {"pmid": "4000", "prefilter": True}]
    expected = ["20", "100", "4000"]
    random.Random(20261127).shuffle(expected)
    assert screening.order(rows) == expected


def test_a_stratum_closes_after_two_included_studies():
    decisions = [
        {"pmid": "1", "decision": "include", "strata": ["term_newborn", "infant_toddler"]},
        {"pmid": "2", "decision": "exclude", "strata": []},
        {"pmid": "3", "decision": "include", "strata": ["term_newborn"]},
    ]
    assert screening.open_strata(decisions) == {"preterm_newborn", "infant_toddler", "child", "adolescent"}


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
