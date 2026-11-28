"""Extended maturation curves: published TM50/Hill pairs beyond the original three.

Expected numbers are typed from the source tables (independent of the code), so a typo in
constants.py fails here. Every value was read from the full text named in its row.
"""

import pytest

from engine.constants import MATURATION
from engine.pk_engine import compute_pediatric_dose

# key: (tm50_weeks, hill, tm50_ci95, hill_ci95, PMID)
PUBLISHED = {
    # Anderson & Holford, Drug Metab Pharmacokinet 2009 Table 1 (1000-run bootstrap 95% CI)
    "ugt1a_sult": (52.2, 3.43, (49.8, 54.1), (3.19, 3.96), "19252334"),
    # Allegaert et al. 2015 (TM50 in abstract); Hill as tabulated in Healy et al. 2025 Table 2
    "cyp2d6": (39.8, 9.0, None, None, "25258277"),
    # McCune et al. 2014 Table 2: 45.7 (RSE 4.3%), 2.3 (RSE 9.7%) -> Wald 95% CI
    "gsta1": (45.7, 2.3, (45.7 * (1 - 1.96 * 0.043), 45.7 * (1 + 1.96 * 0.043)),
              (2.3 * (1 - 1.96 * 0.097), 2.3 * (1 + 1.96 * 0.097)), "24218510"),
    # Maharaj et al. 2021 Table 3 (bootstrap 2.5th / 97.5th percentiles)
    "cyp1a2": (70.0, 3.97, (52.5, 317.3), (2.08, 7.08), "32497307"),
    # Commander et al. 2021 Table 2 (bootstrap 95% CI)
    "renal_secretion": (39.3, 5.73, (32.8, 43.7), (3.1, 13.8), "33029806"),
    # Morse et al. 2020 Table 1 (Hill fixed to 1)
    "dexmedetomidine": (52.4, 1.0, (43.5, 68.8), None, "33126702"),
    # Gonzalez et al. 2014 Table 2 (bootstrap 2.5th / 97.5th percentiles)
    "clindamycin": (43.6, 3.1, (36.1, 83.0), (1.2, 5.1), "24949994"),
    # Anderson & Hannam 2019 abstract (95% CI)
    "ibuprofen": (36.8, 11.5, (34.7, 40.9), (8.1, 15.0), "31472084"),
}


@pytest.mark.parametrize("key", sorted(PUBLISHED))
def test_new_curve_carries_the_published_numbers(key):
    tm50, hill, tm50_ci, hill_ci, pmid = PUBLISHED[key]
    c = MATURATION[key]
    assert c["tm50_weeks"] == pytest.approx(tm50)
    assert c["hill"] == pytest.approx(hill)
    if tm50_ci is None:
        assert c.get("tm50_ci95") is None
    else:
        assert c["tm50_ci95"] == pytest.approx(tm50_ci, rel=1e-3)
    if hill_ci is None:
        assert c.get("hill_ci95") is None
    else:
        assert c["hill_ci95"] == pytest.approx(hill_ci, rel=1e-3)
    assert f"PMID {pmid}" in c["source"]


@pytest.mark.parametrize("key", sorted(PUBLISHED))
def test_new_curve_is_usable_by_the_engine(key):
    probe = MATURATION[key]["probe_drug"]
    r = compute_pediatric_dose(
        drug=probe, weight_kg=10, cl_adult_l_h=20, vd_adult_l=50,
        fm={key: 1.0}, age_years=1, adult_dose_mg_per_day=100,
    )
    assert r.pathways[0].pathway == key
    assert 0 < r.pathways[0].maturation_factor < 1


def _dose(drug, fm):
    return compute_pediatric_dose(
        drug=drug, weight_kg=5, cl_adult_l_h=20, vd_adult_l=50,
        fm=fm, pma_weeks=50, adult_dose_mg_per_day=100,
    )


def test_drug_specific_curve_is_refused_for_another_drug():
    with pytest.raises(ValueError, match="clindamycin"):
        _dose("erythromycin", {"clindamycin": 1.0})


def test_drug_specific_curve_accepts_its_own_drug_whatever_the_salt():
    r = _dose("Clindamycin phosphate", {"clindamycin": 1.0})
    assert r.pathways[0].pathway == "clindamycin"


def test_surrogate_curve_is_flagged_for_a_non_probe_drug():
    w = " ".join(_dose("codeine", {"cyp2d6": 1.0}).warnings)
    assert "surrogate" in w.lower() and "tramadol" in w


def test_probe_drug_gets_no_surrogate_flag():
    w = " ".join(_dose("tramadol", {"cyp2d6": 1.0}).warnings)
    assert "surrogate" not in w.lower()


def test_paracetamol_and_acetaminophen_are_the_same_probe():
    w = " ".join(_dose("acetaminophen", {"ugt1a_sult": 1.0}).warnings)
    assert "surrogate" not in w.lower()


def test_curve_caveat_is_repeated_as_a_warning():
    w = " ".join(_dose("olanzapine", {"cyp1a2": 1.0}).warnings)
    assert "CL/F" in w


def test_gfr_curve_is_never_called_a_surrogate():
    w = " ".join(_dose("vancomycin", {"renal_gfr": 1.0}).warnings)
    assert "surrogate" not in w.lower()


def test_interval_names_curves_with_no_published_uncertainty():
    from engine.uncertainty import dose_uncertainty_interval
    pi = dose_uncertainty_interval(
        drug="tramadol", weight_kg=5, cl_adult_l_h=20, vd_adult_l=50,
        fm={"cyp2d6": 0.6, "renal_gfr": 0.4}, pma_weeks=50, adult_dose_mg_per_day=100,
        n_draws=300,
    )
    assert pi["pathways_without_uncertainty"] == ["cyp2d6"]
    assert "cyp2d6" in pi["method"]
    # with no CI, cyp2d6 cannot carry any of the variance
    assert pi["variance_share"]["cyp2d6"] == pytest.approx(0.0, abs=1e-12)


def test_interval_lists_nothing_when_every_curve_has_a_ci():
    from engine.uncertainty import dose_uncertainty_interval
    pi = dose_uncertainty_interval(
        drug="busulfan", weight_kg=5, cl_adult_l_h=20, vd_adult_l=50,
        fm={"gsta1": 1.0}, pma_weeks=50, adult_dose_mg_per_day=100, n_draws=300,
    )
    assert pi["pathways_without_uncertainty"] == []
    assert pi["dose_mg_per_kg_per_day"]["p95"] > pi["dose_mg_per_kg_per_day"]["p05"]


# ---- drug / enzyme -> curve map --------------------------------------------------
from engine import pathway_map  # noqa: E402


@pytest.mark.parametrize("drug,key", [
    ("Clindamycin", "clindamycin"),          # drug-specific curve wins
    ("acetaminophen", "ugt1a_sult"),         # USAN name of the paracetamol probe
    ("midazolam", "cyp3a4"),                 # probe of a pathway curve
    ("busulfan", "gsta1"),
    ("amoxicillin", None),                   # no curve of its own
])
def test_curve_for_drug(drug, key):
    assert pathway_map.curve_for_drug(drug) == key


@pytest.mark.parametrize("enzyme,keys", [
    ("CYP2D6", ["cyp2d6"]),
    ("CYP3A4/5", ["cyp3a4"]),                # sub-family notation; never the clindamycin-only curve
    ("cyp3a5", ["cyp3a4"]),
    ("UGT1A9", ["ugt1a_sult"]),
    ("OAT3", ["renal_secretion"]),
    ("CYP2C9", []),                          # only the ibuprofen-specific curve -> abstain
    ("UGT1A1", []),                          # minor paracetamol pathway: not a surrogate
    ("CYP2A6", []),                          # only a dexmedetomidine-specific curve exists
])
def test_curves_for_enzyme(enzyme, keys):
    assert pathway_map.curves_for_enzyme(enzyme) == keys


def test_catalogue_lists_every_curve_with_its_scope():
    text = pathway_map.curve_catalogue()
    for key in MATURATION:
        assert key in text
    assert "clindamycin only" in text
    assert "no published uncertainty" in text  # cyp2d6


def test_mechanism_score_counts_a_drug_specific_curve_as_its_pathway_family():
    from engine.mechanism_score import load_truth, score_mechanism
    truth = load_truth()["drugs"]["clindamycin"]
    model = dict(truth, pathways=["clindamycin"])
    assert score_mechanism(model, truth)["pathways"] is True


def test_agent_compute_tool_lists_every_curve():
    from agents.agent import TOOLS
    compute = next(t for t in TOOLS if t["name"] == "compute_pediatric_dose")
    for key in MATURATION:
        assert key in compute["description"]


def test_retrieval_prompt_lists_every_curve():
    import retrieval
    for key in MATURATION:
        assert key in retrieval.SYSTEM
