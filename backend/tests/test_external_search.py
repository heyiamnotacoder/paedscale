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


def test_drug_synonyms_are_searched():
    assert search.queries("acyclovir")[0].startswith("(acyclovir[tiab] OR aciclovir[tiab]) AND")
    assert search.queries("zidovudine")[0].startswith("(zidovudine[tiab] OR azidothymidine[tiab]) AND")


EFETCH = b"""<?xml version="1.0"?><PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>111</PMID><Article><ArticleTitle>Vanco in <i>neonates</i>.</ArticleTitle>
<Journal><JournalIssue><PubDate><Year>1998</Year></PubDate></JournalIssue></Journal>
<Abstract><AbstractText Label="METHODS">Twenty neonates.</AbstractText>
<AbstractText Label="RESULTS">CL was 0.1 L/h/kg.</AbstractText></Abstract></Article>
<OtherAbstract Language="fre"><AbstractText>Texte francais.</AbstractText></OtherAbstract>
</MedlineCitation></PubmedArticle>
<PubmedBookArticle><BookDocument><PMID>222</PMID></BookDocument></PubmedBookArticle>
</PubmedArticleSet>"""


def test_efetch_parsing_keeps_title_and_labelled_sections_only():
    recs = search.parse_efetch(EFETCH)
    assert recs["111"]["text"] == "Vanco in neonates.\n\nMETHODS: Twenty neonates.\nRESULTS: CL was 0.1 L/h/kg."
    assert recs["111"]["year"] == "1998"
    assert "222" not in recs                     # book records are not journal abstracts


def test_a_missing_abstract_stops_the_snapshot():
    import pytest
    with pytest.raises(RuntimeError, match="333"):
        search.require_all(["111", "333"], {"111": {"text": "x", "year": "1998"}})


def test_an_esearch_warning_stops_the_snapshot():
    import pytest
    ok = {"count": "2", "idlist": ["2", "1"], "querytranslation": "q"}
    assert search.checked_ids(ok) == ["1", "2"]
    with pytest.raises(RuntimeError, match="warning"):
        search.checked_ids({**ok, "warninglist": {"phrasesnotfound": ["x"]}})
    with pytest.raises(RuntimeError, match="10000"):
        search.checked_ids({**ok, "count": "12000"})
