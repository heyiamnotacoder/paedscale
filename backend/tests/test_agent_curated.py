"""Curated-path tests for the agent layer — no Anthropic API calls.

For the three in-scope drugs, adult_pk.get_adult_pk and pathways.get_pathway_split
must resolve from data/drugs.json directly, without touching the network. This
is what keeps the demo path fast and deterministic; only out-of-scope drugs
fall through to a live Claude call.
"""

import pytest

from app.agent.adult_pk import get_adult_pk
from app.agent.pathways import get_pathway_split

IN_SCOPE_DRUGS = ["midazolam", "vancomycin", "morphine"]


@pytest.mark.parametrize("drug_name", IN_SCOPE_DRUGS)
def test_adult_pk_resolves_from_curated_data(drug_name):
    result = get_adult_pk(drug_name)
    assert result["confidence"] == "high"
    assert result["adult_clearance_l_per_h"] > 0
    assert result["adult_volume_l"] > 0
    assert 0 <= result["adult_protein_binding"] <= 1


@pytest.mark.parametrize("drug_name", IN_SCOPE_DRUGS)
def test_pathway_split_resolves_from_curated_data(drug_name):
    result = get_pathway_split(drug_name)
    assert result["primary_pathway"] in ("CYP3A4", "renal_GFR", "UGT2B7")
    assert 0 <= result["fm_primary"] <= 1
    assert result["confidence"] == "high"


@pytest.mark.parametrize("drug_name", IN_SCOPE_DRUGS)
def test_curated_lookup_is_case_insensitive(drug_name):
    result = get_adult_pk(drug_name.upper())
    assert result["confidence"] == "high"
