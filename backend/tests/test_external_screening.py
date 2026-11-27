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
