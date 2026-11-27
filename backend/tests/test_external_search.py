"""Search rules of the external validation (benchmark/external/PROTOCOL.md)."""
from benchmark.external.curation import search


def test_the_pediatric_and_adult_queries_follow_the_protocol():
    ped, adult = search.queries("vancomycin")
    assert ped == ("vancomycin[tiab] AND clearance[tiab] AND pharmacokinetic*[tiab] AND "
                   "(neonat*[tiab] OR infant*[tiab] OR child*[tiab] OR pediatric*[tiab] OR "
                   "paediatric*[tiab]) AND humans[mh] AND english[la] AND hasabstract")
    assert adult == ("vancomycin[tiab] AND clearance[tiab] AND pharmacokinetic*[tiab] AND "
                     "(healthy[tiab] OR volunteer*[tiab] OR adult*[tiab]) AND humans[mh] AND "
                     "english[la] AND hasabstract")


def test_two_drugs_use_the_protocol_search_term_not_their_reference_set_name():
    assert search.queries("piperacillin_tazobactam")[0].startswith("piperacillin[tiab] AND")
    assert search.queries("penicillin_g")[0].startswith(
        '(benzylpenicillin[tiab] OR "penicillin G"[tiab]) AND')


def test_the_drug_list_is_the_label_set_without_morphine():
    drugs = search.drugs()
    assert len(drugs) == 20 and "morphine" not in drugs and "vancomycin" in drugs
