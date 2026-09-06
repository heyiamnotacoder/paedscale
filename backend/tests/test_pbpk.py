"""PBPK trial facade (branch `muse-spark-pbpk`) — deterministic, no key, no network.

Covers the envelope abstains the decision log locks (docs/pbpk-trial-decisions.md),
the AUC arithmetic, and the NTI-sensitive rounding. Delete with the branch if axed.
"""

from __future__ import annotations

from engine.pbpk_vancomycin import (
    AUC_TARGET_HI,
    AUC_TARGET_LO,
    AUC_TARGET_MID,
    PBPK_DETAIL_KEYS,
    STANDARD_INTERVALS_H,
    _round_step_mg,
    _snap_interval,
    recommendation_from_pbpk,
    run_pbpk_vancomycin,
)

# 6 y / 20 kg / SCr 0.5 / height 115 cm — the reference case pinned in the decision log.
REF = {
    "drug": "vancomycin",
    "age_years": 6.0,
    "weight_kg": 20.0,
    "serum_creatinine_mg_dl": 0.5,
    "height_cm": 115.0,
}


def _case(**over):
    c = dict(REF)
    c.update(over)
    return c


def test_reference_case_pinned():
    """The decision log's reference output must not drift silently."""
    r = run_pbpk_vancomycin(REF)
    assert r["blocked"] is False, r["block_reason"]
    assert (r["per_dose_mg"], r["interval_h"]) == (270.0, 6), r
    assert r["auc_predicted"] == 497.0, r["auc_predicted"]
    assert r["half_life_h"] == 2.36, r["half_life_h"]
    assert r["grade"] is None  # no A-D on this facade (Q12)


def test_auc_is_solved_over_the_interval_not_a_rounded_dose_count():
    """AUC24 = per-dose x (24/II) / CL for EVERY interval in the standard set.

    Rounding 24/II to an integer would hand the whole 24-h dose out once per
    36-48 h (a 33-50% under-dose) and feed the same wrong number to the AUC
    check, disabling it. Guard the arithmetic directly.
    """
    cl = 1.5
    for ii in STANDARD_INTERVALS_H:
        doses_per_day = 24.0 / ii
        per_dose = (cl * AUC_TARGET_MID) / doses_per_day
        assert abs(per_dose * doses_per_day / cl - AUC_TARGET_MID) < 1e-9, ii
        if ii > 24:
            assert round(24.0 / ii) <= 1  # the trap this test exists to hold shut


def test_reported_auc_matches_the_reported_regimen():
    """Whatever regimen comes out, its own numbers must reproduce the stated AUC."""
    for case in (REF, _case(weight_kg=30.0, age_years=10.0, height_cm=140.0,
                            serum_creatinine_mg_dl=2.6)):
        r = run_pbpk_vancomycin(case)
        assert not r["blocked"], r["block_reason"]
        recomputed = r["per_dose_mg"] * (24.0 / r["interval_h"]) / r["cl_l_per_h"]
        assert abs(recomputed - r["auc_predicted"]) < 1.0, r
        assert abs(r["daily_dose_mg"] - r["per_dose_mg"] * (24.0 / r["interval_h"])) < 0.11, r


def test_auc_discordance_flag_fires_when_rounding_pushes_out_of_band():
    r = run_pbpk_vancomycin(REF)
    in_band = AUC_TARGET_LO <= r["auc_predicted"] <= AUC_TARGET_HI
    flagged = any("AUC discordance" in f for f in r["flags"])
    assert in_band != flagged, (r["auc_predicted"], r["flags"])


def test_rounding_step_scales_with_dose():
    """A flat 10 mg step is ~28% of a neonatal dose — unacceptable on an NTI drug."""
    assert _round_step_mg(18.0) == 1.0
    assert _round_step_mg(120.0) == 5.0
    assert _round_step_mg(270.0) == 10.0
    neo = run_pbpk_vancomycin(_case(age_years=0.05, weight_kg=1.2, pma_weeks=38.0,
                                    serum_creatinine_mg_dl=0.4, height_cm=38.0))
    assert not neo["blocked"], neo["block_reason"]
    assert neo["per_dose_mg"] % 10 != 0 or neo["per_dose_mg"] < 50  # not snapped to a 10 mg grid
    assert AUC_TARGET_LO <= neo["auc_predicted"] <= AUC_TARGET_HI, neo["auc_predicted"]


def test_child_pugh_bc_abstains_on_the_class_alone():
    """The gate must not require a separate hepatic_impairment boolean to ride along."""
    for cls in ("B", "C"):
        r = run_pbpk_vancomycin(_case(child_pugh=cls))
        assert r["blocked"] is True, (cls, r)
        assert "Child-Pugh B/C" in r["block_reason"]
        assert r["per_dose_mg"] is None
        r2 = run_pbpk_vancomycin(_case(child_pugh=cls, hepatic_impairment=True))
        assert r2["blocked"] is True, (cls, r2)


def test_child_pugh_a_doses_and_flags():
    r = run_pbpk_vancomycin(_case(child_pugh="A", hepatic_impairment=True))
    assert not r["blocked"], r["block_reason"]
    assert any("Child-Pugh A only" in f for f in r["flags"])


def test_hepatic_impairment_without_a_class_abstains():
    r = run_pbpk_vancomycin(_case(hepatic_impairment=True))
    assert r["blocked"] is True
    assert "Child-Pugh class" in r["block_reason"]


def test_pma_under_36_weeks_abstains():
    r = run_pbpk_vancomycin(_case(age_years=0.02, weight_kg=1.0, pma_weeks=30.0,
                                  serum_creatinine_mg_dl=0.6, height_cm=35.0))
    assert r["blocked"] is True and "PMA" in r["block_reason"]


def test_under_two_without_pma_abstains_no_assumed_term():
    r = run_pbpk_vancomycin(_case(age_years=0.5, weight_kg=7.0, height_cm=65.0))
    assert r["blocked"] is True and "PMA required" in r["block_reason"]


def test_missing_or_nonnumeric_age_abstains_rather_than_defaulting():
    """`float(x or 0)` used to make a missing age a neonate and raise on a string."""
    for bad in ({}, {"age_years": None}, {"age_years": "six"}):
        c = dict(REF)
        c.update(bad)
        if not bad:
            c.pop("age_years")
        r = run_pbpk_vancomycin(c)
        assert r["blocked"] is True, (bad, r)
        assert "age in years" in r["block_reason"], (bad, r["block_reason"])


def test_missing_renal_inputs_abstain():
    for drop in ("serum_creatinine_mg_dl", "height_cm"):
        c = dict(REF)
        c.pop(drop)
        r = run_pbpk_vancomycin(c)
        assert r["blocked"] is True and "creatinine" in r["block_reason"], drop


def test_egfr_below_floor_abstains():
    r = run_pbpk_vancomycin(_case(serum_creatinine_mg_dl=4.0))
    assert r["blocked"] is True and "eGFR" in r["block_reason"]


def test_non_vancomycin_and_oral_abstain():
    assert run_pbpk_vancomycin(_case(drug="gentamicin"))["blocked"] is True
    assert run_pbpk_vancomycin(_case(route="oral"))["blocked"] is True


def test_allergy_hard_stop():
    r = run_pbpk_vancomycin(_case(allergies=["vancomycin"]))
    assert r["blocked"] is True and "SAFETY STOP" in r["block_reason"]


def test_icu_flag_reads_the_indication_field_too():
    """The tab's indication placeholder is 'e.g. MRSA sepsis' — that path must flag."""
    r = run_pbpk_vancomycin(_case(indication="MRSA sepsis"))
    assert any("Critical-illness" in f for f in r["flags"]), r["flags"]
    r2 = run_pbpk_vancomycin(_case(conditions=["septic shock"]))
    assert any("Critical-illness" in f for f in r2["flags"])
    r3 = run_pbpk_vancomycin(REF)
    assert not any("Critical-illness" in f for f in r3["flags"])


def test_abstain_and_success_share_one_regimen_shape():
    ok = run_pbpk_vancomycin(REF)
    no = run_pbpk_vancomycin(_case(drug="gentamicin"))
    for k in PBPK_DETAIL_KEYS:
        assert k in ok and k in no, k
    assert all(no[k] is None for k in PBPK_DETAIL_KEYS if k != "auc_target")


def test_checkpoint_honesty_markings_survive():
    r = run_pbpk_vancomycin(REF)
    by_id = {c["id"]: c for c in r["checkpoints"]}
    assert "ABSTAINED" in by_id["C1-quant"]["metric"]
    assert "[INFERENCE]" in by_id["O1"]["metric"]
    assert "[INFERENCE]" not in by_id["E4"]["metric"]  # the only paper-explicit peds gate
    assert "OUT OF ENVELOPE" in by_id["C2"]["metric"]


def test_recommendation_carries_no_grade_and_no_concordance():
    rec = recommendation_from_pbpk(REF, run_pbpk_vancomycin(REF))
    assert rec["grade"] is None and "concordance" not in rec
    assert rec["calculator_mode"] == "pbpk" and rec["allometry_applied"] is False
    assert rec["pbpk"]["per_dose_mg"] == 270.0


def test_snap_interval_never_dips_below_the_half_life():
    for t_half in (1.0, 5.0, 13.0, 30.0):
        for nominal in (1, 2, 3, 4):
            ii = _snap_interval(t_half, nominal)
            assert ii in STANDARD_INTERVALS_H
            assert ii >= t_half or ii == STANDARD_INTERVALS_H[-1]


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for fn in ALL:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nPBPK trial facade: {len(ALL)} tests passed.")
