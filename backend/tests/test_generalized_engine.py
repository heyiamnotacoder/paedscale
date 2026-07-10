"""Tests for multi-pathway maturation and the generalized extrapolation engine."""

import pytest

from app.pk.maturation import (
    Pathway,
    combined_maturation,
    effective_clearance_fraction,
    maturation_fraction,
    normalized_pathways,
)
from app.pk.pipeline import ChildCovariates, extrapolate_generalized


def _paths():
    # A drug split across a hepatic (CYP3A4-like) and a renal route.
    return [
        Pathway(fm=0.6, tm50_weeks=55.4, hill=1.0, name="CYP3A4", organ="hepatic"),
        Pathway(fm=0.4, tm50_weeks=47.7, hill=3.4, name="renal_GFR", organ="renal"),
    ]


def test_combined_maturation_is_weighted_sum():
    paths = _paths()
    pma = 40.0
    expected = sum(p.fm * maturation_fraction(pma, p.tm50_weeks, p.hill) for p in paths)
    assert combined_maturation(pma, paths) == pytest.approx(expected)


def test_combined_maturation_rises_with_age():
    paths = _paths()
    assert combined_maturation(30.0, paths) < combined_maturation(200.0, paths)
    # Monotonic toward 1.0; a hill=1 pathway is only asymptotically complete, so
    # even a school-age child sits below 1, but the adult limit is 1.0.
    assert combined_maturation(200.0, paths) < combined_maturation(5000.0, paths)
    assert combined_maturation(5000.0, paths) == pytest.approx(1.0, abs=0.02)


def test_organ_modifiers_only_reduce_their_own_pathway():
    paths = _paths()
    pma = 300.0
    base = effective_clearance_fraction(pma, paths, None)
    renal_hit = effective_clearance_fraction(pma, paths, {"renal": 0.5})
    hepatic_hit = effective_clearance_fraction(pma, paths, {"hepatic": 0.5})
    assert renal_hit < base
    assert hepatic_hit < base
    # renal is 40% of clearance, hepatic 60% → hepatic impairment costs more.
    assert hepatic_hit < renal_hit


def test_normalized_pathways_sum_to_one():
    paths = [Pathway(fm=2.0, tm50_weeks=50, hill=1), Pathway(fm=2.0, tm50_weeks=48, hill=3)]
    norm = normalized_pathways(paths)
    assert sum(p.fm for p in norm) == pytest.approx(1.0)


def test_generalized_auc_neonate_dose_per_kg_below_older_child():
    paths = _paths()
    params = dict(
        adult_reference_dose_mg=500.0,
        adult_clearance_l_per_h=5.0,
        adult_interval_h=12.0,
    )
    neonate = extrapolate_generalized(
        adult_clearance_l_per_h=5.0,
        adult_volume_l=50.0,
        adult_protein_binding=0.5,
        pathways=paths,
        child=ChildCovariates(weight_kg=3.5, pma_weeks=40),
        method="auc",
        method_params=params,
    )
    older = extrapolate_generalized(
        adult_clearance_l_per_h=5.0,
        adult_volume_l=50.0,
        adult_protein_binding=0.5,
        pathways=paths,
        child=ChildCovariates(weight_kg=12.0, pma_weeks=160),
        method="auc",
        method_params=params,
    )
    assert neonate.dose.dose_mg_per_kg < older.dose.dose_mg_per_kg
    assert 0 < neonate.maturation_fraction < 1


def test_generalized_cmax_uses_volume_path():
    # cmax solver needs child_volume_l; engine must inject it and ignore CL.
    res = extrapolate_generalized(
        adult_clearance_l_per_h=5.0,
        adult_volume_l=70.0,
        adult_protein_binding=0.5,
        pathways=_paths(),
        child=ChildCovariates(weight_kg=7.0, pma_weeks=60),
        method="cmax",
        method_params={"cmax_target_mg_per_l": 30.0},
    )
    assert res.dose.method == "cmax"
    assert res.dose.dose_mg == pytest.approx(30.0 * res.child_volume_l)


def test_generalized_renal_impairment_reduces_renal_drug_dose():
    renal_drug = [Pathway(fm=1.0, tm50_weeks=47.7, hill=3.4, name="renal_GFR", organ="renal")]
    params = dict(adult_reference_dose_mg=500.0, adult_clearance_l_per_h=5.0, adult_interval_h=12.0)
    child = ChildCovariates(weight_kg=12.0, pma_weeks=160)
    healthy = extrapolate_generalized(5.0, 50.0, 0.5, renal_drug, child, "auc", params)
    impaired = extrapolate_generalized(
        5.0, 50.0, 0.5, renal_drug, child, "auc", params, organ_modifiers={"renal": 0.4}
    )
    assert impaired.dose.dose_mg < healthy.dose.dose_mg
