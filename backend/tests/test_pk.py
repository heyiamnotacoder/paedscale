"""
Deterministic PK-engine tests + concordance check against guidelines.json.

Runs with NO API key — this exercises the scientific core (the math that must be exactly
right) and scores it against the hand-reviewed guideline doses. The Claude reasoning layer
is tested separately in test_agent.py (which does need a key).

Run:  python test_pk.py
"""

import json
import os

from engine.pk_engine import compute_pediatric_dose, maturation_factor

HERE = os.path.dirname(__file__)
EVAL = os.path.join(HERE, "..", "eval_data")
BAND_HI, BAND_LO = 1.5, 0.67  # concordance band

# The reviewed adult-PK oracle (moved out of production code) — the harness reads it to feed
# the deterministic engine and score it. The product agent never touches this.
with open(os.path.join(EVAL, "drug_pk.json")) as _f:
    DRUG_SEED = json.load(_f)["drugs"]


def _seed_dose(drug: str, weight_kg: float, age_years: float, adult_dose_mg_per_day):
    s = DRUG_SEED[drug]
    return compute_pediatric_dose(
        drug=drug,
        weight_kg=weight_kg,
        cl_adult_l_h=s["cl_adult_l_h"],
        vd_adult_l=s["vd_adult_l"],
        fm=s["fm"],
        target_metric=s["target_metric"],
        age_years=age_years,
        adult_dose_mg_per_day=adult_dose_mg_per_day,
    )


def test_maturation_monotonic():
    """Maturation must rise with PMA and approach 1 in adulthood."""
    mf_neo = maturation_factor(40, 47.7, 3.40)      # term neonate, renal
    mf_1yr = maturation_factor(40 + 52, 47.7, 3.40)
    mf_adult = maturation_factor(40 * 52, 47.7, 3.40)
    assert mf_neo < mf_1yr < mf_adult, (mf_neo, mf_1yr, mf_adult)
    assert 0.95 <= mf_adult <= 1.001, mf_adult
    assert mf_neo < 0.6, mf_neo  # a term neonate clears renally well below adult/kg
    print(f"  maturation renal: neonate={mf_neo:.2f} 1yr={mf_1yr:.2f} adult={mf_adult:.2f}  OK")


def test_neonate_clears_below_linear():
    """A neonate's clearance fraction of adult must sit well below the naive mg/kg line."""
    # 3.5 kg term neonate on vancomycin (renal)
    r = _seed_dose("vancomycin", weight_kg=3.5, age_years=0.02, adult_dose_mg_per_day=2000)
    # naive linear mg/kg would give child CL fraction = (3.5/70) = 0.05 of adult;
    # allometry+maturation must give LESS (immature GFR) per-kg, i.e. lower mg/kg than adult.
    adult_mg_per_kg = 2000 / 70
    assert r.recommended_dose_mg_per_kg_per_day < adult_mg_per_kg, (
        r.recommended_dose_mg_per_kg_per_day, adult_mg_per_kg
    )
    print(f"  neonate vancomycin: {r.recommended_dose_mg_per_kg_per_day:.1f} mg/kg/day "
          f"(CL {r.cl_fraction_of_adult:.1%} of adult, t1/2 {r.half_life_h:.1f} h)  OK")


def test_refuses_unknown_pathway():
    try:
        compute_pediatric_dose(
            drug="mystery", weight_kg=10, cl_adult_l_h=10, vd_adult_l=50,
            fm={"not_a_real_pathway": 1.0}, age_years=1,
        )
    except ValueError as e:
        assert "maturation curve" in str(e)
        print("  refuses to invent a maturation curve for unknown pathway  OK")
        return
    raise AssertionError("should have refused unknown pathway")


def test_only_published_pathways():
    """MATURATION holds only opened Hill+TM50 primaries — no approximate extras."""
    from engine.constants import MATURATION
    assert set(MATURATION) == {"renal_gfr", "cyp3a4", "ugt2b7"}
    assert MATURATION["renal_gfr"]["tm50_weeks"] == 47.7
    assert MATURATION["renal_gfr"]["hill"] == 3.40
    assert MATURATION["cyp3a4"]["tm50_weeks"] == 73.6
    assert MATURATION["cyp3a4"]["hill"] == 3.0
    assert MATURATION["ugt2b7"]["tm50_weeks"] == 54.2
    assert MATURATION["ugt2b7"]["hill"] == 3.92
    for key, params in MATURATION.items():
        assert "PMID" in params["source"], key
        assert "approx" not in params["source"].lower()
        r = compute_pediatric_dose(
            drug="probe", weight_kg=10, cl_adult_l_h=20, vd_adult_l=50,
            fm={key: 1.0}, age_years=1, adult_dose_mg_per_day=100,
        )
        assert r.cl_child_l_h > 0 and r.pathways[0].pathway == key
    print("  published pathways only: renal_gfr / cyp3a4 / ugt2b7  OK")


def test_pk_cache():
    from engine.pk_cache import PkCache
    c = PkCache(max_entries=2, max_bytes=50_000, ttl_seconds=3600)
    d = {
        "cl_adult_l_h": 5.0, "vd_adult_l": 20.0, "fm": {"renal_gfr": 1.0},
        "citations": [{"claim": "CL", "source": "PMID:1"}],
    }
    assert c.set("gentamicin", "sepsis", d, "live")
    hit = c.get("gentamicin", "sepsis")
    assert hit and hit["dossier"]["cl_adult_l_h"] == 5.0
    # indication is not part of the key — same drug, other indication, still hits
    assert c.get("gentamicin", "meningitis")["dossier"]["cl_adult_l_h"] == 5.0
    assert c.get("gentamicin", None)["dossier"]["cl_adult_l_h"] == 5.0
    assert c.set("vanco", None, d, "live")
    assert c.set("amikacin", None, d, "live")  # evicts oldest
    assert c.get("gentamicin", "sepsis") is None  # LRU evicted
    assert not c.set("x", None, d, "unavailable")
    # reject uncited or partial core PK (no cache poison)
    assert not c.set("bad", None, {
        "cl_adult_l_h": 5.0, "vd_adult_l": 20.0, "citations": [],
    }, "live")
    assert not c.set("partial", None, {
        "cl_adult_l_h": 5.0, "vd_adult_l": None,
        "citations": [{"claim": "CL", "source": "x"}],
    }, "live")
    print("  pk_cache: LRU + reject unavailable/uncited/partial  OK")


def test_edge_cases():
    from engine.edge_cases import assess_edge_cases
    # prodrug
    r = assess_edge_cases({"drug": "codeine", "age_years": 6, "weight_kg": 20}, {})
    assert any("PRODRUG" in f for f in r["flags"]), r
    # obesity
    r2 = assess_edge_cases({"drug": "midazolam", "age_years": 1.0, "weight_kg": 14}, {})
    assert any("OBESITY" in f for f in r2["flags"]), r2
    assert "dosing_weight_kg_hint" in r2["adjustments"]
    # high PB + neonate
    r3 = assess_edge_cases(
        {"drug": "midazolam", "age_years": 0.05, "weight_kg": 3.5},
        {"protein_binding_percent": 97},
    )
    assert any("PROTEIN BINDING" in f for f in r3["flags"]), r3
    # renal
    r4 = assess_edge_cases(
        {"drug": "vanco", "age_years": 6, "weight_kg": 20, "renal_impairment": True}, {}
    )
    assert any("RENAL" in f for f in r4["flags"]), r4
    # no false positive on lean child
    r5 = assess_edge_cases({"drug": "vancomycin", "age_years": 6, "weight_kg": 20},
                           {"protein_binding_percent": 50})
    assert not any("OBESITY" in f for f in r5["flags"])
    print("  edge_cases: prodrug/obesity/PB/renal  OK")


def test_oral_bioavailability():
    """Oral route must inflate the administered dose by 1/F vs the IV-equivalent."""
    s = DRUG_SEED["ampicillin"]  # F ~ 0.40
    common = dict(
        drug="ampicillin", weight_kg=20, cl_adult_l_h=s["cl_adult_l_h"],
        vd_adult_l=s["vd_adult_l"], fm=s["fm"], target_metric=s["target_metric"],
        age_years=6, adult_dose_mg_per_day=s["typical_adult_dose_mg_per_day"],
    )
    iv = compute_pediatric_dose(route="iv", **common)
    po = compute_pediatric_dose(route="oral", oral_bioavailability=0.40, **common)
    ratio = po.recommended_dose_mg_per_kg_per_day / iv.recommended_dose_mg_per_kg_per_day
    assert abs(ratio - 1 / 0.40) < 1e-6, ratio
    assert any("Oral bioavailability F applied" in w for w in po.warnings), po.warnings
    print(f"  oral F: IV={iv.recommended_dose_mg_per_kg_per_day:.1f} → "
          f"PO={po.recommended_dose_mg_per_kg_per_day:.1f} mg/kg/day (×{ratio:.2f} = 1/F)  OK")


def test_time_mic_flag():
    """A time>MIC drug must emit the fT>MIC proxy warning + a half-life-anchored interval."""
    s = DRUG_SEED["ampicillin"]
    r = compute_pediatric_dose(
        drug="ampicillin", weight_kg=20, cl_adult_l_h=s["cl_adult_l_h"],
        vd_adult_l=s["vd_adult_l"], fm=s["fm"], target_metric="time_mic",
        age_years=6, adult_dose_mg_per_day=s["typical_adult_dose_mg_per_day"],
    )
    assert any("TIME>MIC" in w for w in r.warnings), r.warnings
    assert r.suggested_interval_h is not None and r.suggested_interval_h > 0
    print(f"  time>MIC: flag present, interval anchored to t1/2 "
          f"(~{r.suggested_interval_h:.1f} h)  OK")


def test_safety_bounds_fire():
    """An above-toxic dose must HARD STOP: blocked, no dose returned, SAFETY STOP message."""
    s = DRUG_SEED["amikacin"]  # cmax → child mg/kg ≈ adult mg/kg
    # Feed an absurdly high adult dose so the child mg/kg blows past the toxic bound.
    r = compute_pediatric_dose(
        drug="amikacin", weight_kg=20, cl_adult_l_h=s["cl_adult_l_h"],
        vd_adult_l=s["vd_adult_l"], fm=s["fm"], target_metric="cmax",
        age_years=6, adult_dose_mg_per_day=100.0 * 70,  # 100 mg/kg adult → child ~100
        toxic_dose_mg_per_kg_per_day=s["toxic_dose_mg_per_kg_per_day"],
        effective_dose_mg_per_kg_per_day=s["effective_dose_mg_per_kg_per_day"],
    )
    assert r.blocked, r.warnings
    assert r.recommended_dose_mg_per_kg_per_day is None and r.recommended_dose_mg_per_day is None
    assert any("EXCEEDS TOXIC THRESHOLD" in w for w in r.warnings), r.warnings
    print("  safety bounds: above-toxic dose HARD STOPPED (blocked, no dose)  OK")


def test_route_not_viable_hard_stop():
    """Oral route for a not-orally-absorbed drug (F=0) must HARD STOP with no dose."""
    s = DRUG_SEED["gentamicin"]
    r = compute_pediatric_dose(
        drug="gentamicin", weight_kg=12, cl_adult_l_h=s["cl_adult_l_h"],
        vd_adult_l=s["vd_adult_l"], fm=s["fm"], target_metric="cmax",
        age_years=2, adult_dose_mg_per_day=s["typical_adult_dose_mg_per_day"],
        route="oral", oral_bioavailability=0.0,
    )
    assert r.blocked and r.recommended_dose_mg_per_kg_per_day is None
    assert "ROUTE NOT VIABLE" in r.block_reason
    # Unknown F is a data gap — block WITHOUT claiming F=0
    r_unk = compute_pediatric_dose(
        drug="mystery_oral", weight_kg=12, cl_adult_l_h=5.0, vd_adult_l=20.0,
        fm={"renal_gfr": 1.0}, target_metric="css", age_years=2,
        adult_dose_mg_per_day=100, route="oral", oral_bioavailability=None,
    )
    assert r_unk.blocked and r_unk.recommended_dose_mg_per_kg_per_day is None
    assert "unknown" in r_unk.block_reason.lower()
    assert "F=0" not in r_unk.block_reason
    # same drug IV must still solve a dose
    r_iv = compute_pediatric_dose(
        drug="gentamicin", weight_kg=12, cl_adult_l_h=s["cl_adult_l_h"],
        vd_adult_l=s["vd_adult_l"], fm=s["fm"], target_metric="cmax",
        age_years=2, adult_dose_mg_per_day=s["typical_adult_dose_mg_per_day"], route="iv",
    )
    assert not r_iv.blocked and r_iv.recommended_dose_mg_per_kg_per_day is not None
    print("  route viability: oral F=0 HARD STOPPED, unknown F data-gap, IV OK  OK")


def test_empty_and_over_sum_fm_hard_stop():
    """Empty fm or over-sum fm must not produce a recommended dose."""
    common = dict(
        drug="probe", weight_kg=10, cl_adult_l_h=20, vd_adult_l=50,
        age_years=1, adult_dose_mg_per_day=100,
    )
    empty = compute_pediatric_dose(fm={}, **common)
    assert empty.blocked and empty.recommended_dose_mg_per_kg_per_day is None
    assert "empty" in empty.block_reason.lower() or "zero fm" in empty.block_reason.lower()

    over = compute_pediatric_dose(fm={"renal_gfr": 0.8, "cyp3a4": 0.5}, **common)  # 1.3
    assert over.blocked and over.recommended_dose_mg_per_kg_per_day is None
    assert "1.30" in over.block_reason or "double-count" in over.block_reason.lower()

    ok = compute_pediatric_dose(fm={"renal_gfr": 1.0}, **common)
    assert not ok.blocked and ok.recommended_dose_mg_per_kg_per_day is not None
    print("  empty/over-sum fm HARD STOPPED; valid fm doses  OK")


def test_ssrf_guard():
    """web_fetch must refuse loopback/private targets but allow public hostnames through the guard."""
    from retrieval.retrieval_tools import web_fetch, _ssrf_guard
    for url in ("http://127.0.0.1/", "http://localhost/foo", "http://169.254.169.254/latest"):
        r = web_fetch(url)
        assert r.get("text") == ""
        assert "SSRF" in (r.get("error") or ""), (url, r)
    # Public DNS names must not be treated as blocked IPs (the PR-1 regression).
    assert _ssrf_guard("https://example.com/") is None, _ssrf_guard("https://example.com/")
    assert _ssrf_guard("https://pubmed.ncbi.nlm.nih.gov/") is None
    print("  web_fetch SSRF guard: loopback blocked, public hosts allowed  OK")


def test_compute_injects_renal_and_blocks_without_pk():
    """Orchestrator compute handler injects case renal OF and refuses without retrieval."""
    from agents.agent import _build_compute, _normalize_case, _dossier_core_pk_ok

    assert not _dossier_core_pk_ok(None)
    assert not _dossier_core_pk_ok({"cl_adult_l_h": 1.0})
    assert _dossier_core_pk_ok({"cl_adult_l_h": 1.0, "vd_adult_l": 10.0})

    case = _normalize_case({
        "drug": "vancomycin", "age_years": 6, "weight_kg": 20,
        "renal_impairment": True, "height_cm": 120, "serum_creatinine_mg_dl": 1.5,
    })
    assert case["renal_function_fraction"] < 1.0

    state = {
        "pk_ok": False, "pk_block_reason": None, "last_dossier": None,
        "blocked_reason": None, "last_compute_renal_frac": None,
    }
    compute = _build_compute(case, state)
    denied = compute({
        "drug": "vancomycin", "weight_kg": 20, "cl_adult_l_h": 4.2, "vd_adult_l": 49,
        "fm": {"renal_gfr": 0.9}, "age_years": 6, "adult_dose_mg_per_day": 2000,
    })
    assert denied.get("blocked") and denied.get("recommended_dose_mg_per_kg_per_day") is None
    # Premature compute must NOT sticky-latch blocked_reason (recoverable tool order).
    assert state["blocked_reason"] is None

    state["pk_ok"] = True
    state["pk_block_reason"] = None
    state["last_dossier"] = {
        "cl_adult_l_h": 4.2, "vd_adult_l": 49.0, "fm": {"renal_gfr": 0.9},
        "typical_adult_dose_mg_per_day": 2000,
    }
    # Model "forgets" renal_function_fraction — handler must inject case value.
    out = compute({
        "drug": "vancomycin", "weight_kg": 20, "cl_adult_l_h": 99, "vd_adult_l": 99,
        "fm": {"renal_gfr": 0.9}, "age_years": 6, "adult_dose_mg_per_day": 2000,
        # deliberate omit renal_function_fraction
    })
    assert not out.get("error"), out
    assert not out.get("blocked"), out
    assert state["blocked_reason"] is None  # successful compute keeps/clears latch
    assert state["last_compute_renal_frac"] == case["renal_function_fraction"]
    # Dossier CL/Vd override model invention; renal OF applied (compare unrounded path OF)
    ref = compute_pediatric_dose(
        drug="vancomycin", weight_kg=20, cl_adult_l_h=4.2, vd_adult_l=49.0,
        fm={"renal_gfr": 0.9}, age_years=6, adult_dose_mg_per_day=2000,
        renal_function_fraction=case["renal_function_fraction"],
    )
    assert abs(out["cl_child_l_h"] - round(ref.cl_child_l_h, 3)) < 1e-9
    assert out["pathways"][0]["organ_function_modifier"] == case["renal_function_fraction"]
    # Without renal reduction CL would be ~2.5× higher
    ref_full = compute_pediatric_dose(
        drug="vancomycin", weight_kg=20, cl_adult_l_h=4.2, vd_adult_l=49.0,
        fm={"renal_gfr": 0.9}, age_years=6, adult_dose_mg_per_day=2000,
        renal_function_fraction=1.0,
    )
    assert ref.cl_child_l_h < ref_full.cl_child_l_h * 0.5
    print("  compute: PK abstain + no sticky latch + renal OF + dossier PK  OK")


def test_compute_forces_dossier_f_and_toxic():
    """Dossier F and toxic bounds always win; oral + unknown F hard-stops via product path."""
    from agents.agent import _build_compute, _normalize_case

    case = _normalize_case({
        "drug": "midazolam", "age_years": 6, "weight_kg": 20, "route": "oral",
    })
    state = {
        "pk_ok": True, "pk_block_reason": None, "blocked_reason": None,
        "last_compute_renal_frac": None,
        "last_dossier": {
            "cl_adult_l_h": 24.0, "vd_adult_l": 70.0, "fm": {"cyp3a4": 0.95},
            "typical_adult_dose_mg_per_day": 100.0,
            "oral_bioavailability": 0.4,
            "toxic_dose_mg_per_kg_per_day": 0.01,  # very low → any real dose blocks
        },
    }
    compute = _build_compute(case, state)

    # Model invents F=1.0 and a huge toxic ceiling — dossier must override both.
    out = compute({
        "drug": "midazolam", "weight_kg": 20, "cl_adult_l_h": 24, "vd_adult_l": 70,
        "fm": {"cyp3a4": 0.95}, "age_years": 6, "adult_dose_mg_per_day": 100,
        "route": "oral", "oral_bioavailability": 1.0,
        "toxic_dose_mg_per_kg_per_day": 9999,
    })
    assert out.get("blocked"), out
    assert "TOXIC" in (out.get("block_reason") or "").upper() or any(
        "TOXIC" in w for w in (out.get("warnings") or [])
    )
    assert state["blocked_reason"]  # real engine hard-stop latches

    # Oral with no F in dossier or args → unknown-F data-gap stop (not F=1.0).
    state2 = {
        "pk_ok": True, "pk_block_reason": None, "blocked_reason": None,
        "last_compute_renal_frac": None,
        "last_dossier": {
            "cl_adult_l_h": 24.0, "vd_adult_l": 70.0, "fm": {"cyp3a4": 0.95},
            "typical_adult_dose_mg_per_day": 100.0,
            # oral_bioavailability deliberately absent
        },
    }
    out2 = _build_compute(case, state2)({
        "drug": "midazolam", "weight_kg": 20, "cl_adult_l_h": 24, "vd_adult_l": 70,
        "fm": {"cyp3a4": 0.95}, "age_years": 6, "adult_dose_mg_per_day": 100,
        "route": "oral",
    })
    assert out2.get("blocked"), out2
    assert "unknown" in (out2.get("block_reason") or "").lower()
    assert "F=0" not in (out2.get("block_reason") or "")
    print("  compute: dossier F/toxic forced; unknown oral F hard-stop  OK")


def test_allergy_normalize_hint():
    from agents.agent import _normalize_case
    c = _normalize_case({
        "drug": "Vancomycin", "age_years": 6, "weight_kg": 20,
        "allergies": ["penicillin", "vancomycin"],
    })
    assert c.get("allergy_name_overlap_hint")
    assert any("vancomycin" in h.lower() for h in c["allergy_name_overlap_hint"])
    print("  allergy name-overlap hint set for same-drug allergy  OK")


def test_mechanism_scorer():
    """The mechanism scorer must reward a perfect answer and catch a targeted miss (no key)."""
    from engine.mechanism_score import load_truth, score_mechanism
    truth = load_truth()["drugs"]
    assert score_mechanism(truth["vancomycin"], truth["vancomycin"])["overall"] == 1.0
    miss = score_mechanism(
        {"elimination": "renal", "pathways": ["renal_gfr"], "enzymes": ["CYP3A4"],
         "transporters": [], "active_metabolites": [], "protein_binding_percent": 50},
        truth["vancomycin"],
    )
    assert miss["enzymes"] is False and miss["elimination"] is True, miss
    print("  mechanism scorer: perfect=1.0, invented-enzyme miss caught  OK")


def test_formulation_rounding():
    from engine.formulation import (
        attach_administration,
        build_administration,
        increment_mg,
        parse_doses_per_day,
        round_to_increment,
    )

    assert increment_mg(0.4) == 0.05
    assert increment_mg(3) == 0.1
    assert increment_mg(12) == 0.5
    assert increment_mg(47) == 1.0
    assert increment_mg(220) == 5.0
    assert increment_mg(800) == 10.0
    assert round_to_increment(47.32, 1.0) == 47.0

    assert parse_doses_per_day("q8h") == 3.0
    assert parse_doses_per_day("every 8 hours") == 3.0
    assert parse_doses_per_day("BID") == 2.0
    assert parse_doses_per_day(None, suggested_interval_h=12) == 2.0
    assert parse_doses_per_day("as directed") is None

    admin = build_administration(
        dose_mg_per_day=47.32, weight_kg=20, interval="q8h", formulation_mg_per_ml=5.0,
    )
    assert admin is not None
    assert admin["doses_per_day"] == 3.0
    assert admin["rounded_dose_mg_per_dose"] is not None
    assert admin["volume_ml_per_dose"] == round(admin["rounded_dose_mg_per_dose"] / 5.0, 3)
    assert admin["formulation_mg_per_ml"] == 5.0
    assert admin["flag"] is None

    tiny = build_administration(dose_mg_per_day=0.37, weight_kg=3.5, interval=None)
    assert tiny is not None
    assert tiny["increment_mg"] == 0.05

    rec = {
        "final_dose_mg_per_day": 47.32,
        "final_dose_mg_per_kg_per_day": 2.366,
        "interval": "q8h",
        "flags": [],
        "blocked": False,
    }
    attach_administration(rec, {"weight_kg": 20, "formulation_mg_per_ml": 5})
    assert rec["administration"]["rounded_dose_mg_per_day"] is not None
    assert rec["final_dose_mg_per_day"] == 47.32  # engine number unchanged

    blocked = {"final_dose_mg_per_day": 10, "blocked": True, "flags": []}
    attach_administration(blocked, {"weight_kg": 20})
    assert blocked["administration"] is None

    null_dose = {"final_dose_mg_per_day": None, "blocked": False, "flags": []}
    attach_administration(null_dose, {"weight_kg": 20})
    assert null_dose["administration"] is None
    print("  formulation rounding + attach_administration  OK")


def test_child_pugh():
    """Child-Pugh class from labs: normal → A; high scores → C; resolve prefers calc."""
    from engine.child_pugh import compute_child_pugh, resolve_child_pugh, allergy_tokens_overlap

    mild = compute_child_pugh(
        bilirubin_mg_dl=1.0, albumin_g_dl=4.0, inr=1.1,
        ascites="none", encephalopathy="none",
    )
    assert mild["score"] == 5 and mild["class"] == "A", mild

    severe = compute_child_pugh(
        bilirubin_mg_dl=4.0, albumin_g_dl=2.5, inr=2.5,
        ascites="moderate", encephalopathy="3-4",
    )
    assert severe["score"] == 15 and severe["class"] == "C", severe

    # 2+2+2+1+1 = 8 → class B
    mid = compute_child_pugh(
        bilirubin_mg_dl=2.5, albumin_g_dl=3.0, inr=2.0,
        ascites="none", encephalopathy="none",
    )
    assert mid["class"] == "B" and 7 <= mid["score"] <= 9, mid

    patch = resolve_child_pugh({
        "bilirubin_mg_dl": 1.0, "albumin_g_dl": 4.0, "inr": 1.0,
        "ascites": "none", "encephalopathy": "none",
        "child_pugh": "C",  # complete labs win when ascites/enceph are explicit
    })
    assert patch["child_pugh"] == "A" and patch["child_pugh_source"] == "calculated"

    # Labs without explicit ascites/encephalopathy must not silently default to none.
    no_signs = resolve_child_pugh({
        "bilirubin_mg_dl": 1.0, "albumin_g_dl": 4.0, "inr": 1.0,
        "child_pugh": "C",
    })
    assert no_signs["child_pugh"] == "C" and no_signs["child_pugh_source"] == "entered"

    entered = resolve_child_pugh({"child_pugh": "b"})
    assert entered["child_pugh"] == "B" and entered["child_pugh_source"] == "entered"

    hits = allergy_tokens_overlap(["penicillin", "vancomycin"], "Vancomycin")
    assert any("vancomycin" in h.lower() for h in hits), hits
    assert allergy_tokens_overlap(["penicillin"], "Vancomycin") == []
    print("  child_pugh: A/B/C + resolve + allergy overlap  OK")


def concordance_check():
    """Score seed-based estimates against the guideline JSON."""
    with open(os.path.join(EVAL, "guidelines.json")) as f:
        gl = json.load(f)

    # representative test children per drug (weight_kg, age_years, adult_dose_mg_per_day)
    cases = {
        "midazolam": [(20, 6, 1.44 * 70)],   # child; adult ~0.06 mg/kg/h*70kg*24h
        "vancomycin": [(20, 6, 2000)],
        "morphine": [(20, 6, 0.48 * 70)],
        # Stage-2 drugs (adult daily dose = adult mg/kg midpoint * 70 kg):
        "gentamicin": [(20, 6, 5.0 * 70)],    # cmax-driven aminoglycoside, ~5 mg/kg adult
        "amikacin":   [(20, 6, 15.0 * 70)],   # cmax-driven aminoglycoside, ~15 mg/kg adult
        "fentanyl":   [(20, 6, 0.036 * 70)],  # css infusion, ~1.5 mcg/kg/h adult
        "ampicillin": [(20, 6, 8000)],        # css (time>MIC proxy), 2 g q6h adult
        "clindamycin":[(20, 6, 1800)],        # css, 600 mg q8h adult
    }
    print("\nConcordance vs guidelines (band 0.67x-1.5x):")
    passed = 0
    total = 0
    for drug, drug_cases in cases.items():
        pops = gl["drugs"][drug]["populations"]
        for (wt, age, adult_dose) in drug_cases:
            # find matching guideline population
            gpop = next(
                (p for p in pops if p["age_years_min"] <= age <= p["age_years_max"]), None
            )
            if not gpop:
                continue
            r = _seed_dose(drug, wt, age, adult_dose)
            est = r.recommended_dose_mg_per_kg_per_day
            ref = gpop["dose_mg_per_kg_per_day"]
            ratio = est / ref if ref else float("nan")
            ok = BAND_LO <= ratio <= BAND_HI
            passed += ok
            total += 1
            print(f"  {drug:12s} est={est:6.2f}  guideline={ref:6.2f} mg/kg/day  "
                  f"ratio={ratio:.2f}  {'PASS' if ok else 'CHECK'}")
    print(f"\n  {passed}/{total} within band "
          f"(seed PK — expect some misses; this validates the pipeline, not final numbers)")


if __name__ == "__main__":
    print("Deterministic PK-engine tests (no API key):")
    test_maturation_monotonic()
    test_neonate_clears_below_linear()
    test_refuses_unknown_pathway()
    test_only_published_pathways()
    test_edge_cases()
    test_pk_cache()
    test_oral_bioavailability()
    test_time_mic_flag()
    test_safety_bounds_fire()
    test_route_not_viable_hard_stop()
    test_empty_and_over_sum_fm_hard_stop()
    test_ssrf_guard()
    test_compute_injects_renal_and_blocks_without_pk()
    test_compute_forces_dossier_f_and_toxic()
    test_allergy_normalize_hint()
    test_mechanism_scorer()
    test_formulation_rounding()
    test_child_pugh()
    from tests.test_hi_table import (
        test_extract_fills_per_class_contract_with_excerpt_and_citation,
        test_caution_only_or_missing_excerpt_is_not_a_citation,
        test_mild_moderate_severe_maps_to_abc_and_is_flagged,
        test_no_adjustment_necessary_is_fold_one,
        test_missing_a_is_fold_one_missing_b_uses_c_else_abstain,
        test_missing_c_uses_moderate_else_abstain,
        test_user_adult_dose_overrides_label_fold_only_without_dose_abstains,
        test_indication_stratified_rows_must_match_or_abstain,
        test_resolver_is_single_implementation,
        test_live_extract_from_openfda_style_label,
        test_non_hepatic_severity_is_not_a_citation,
        test_both_facades_share_resolve_hi_dose,
        test_retrieval_attaches_live_hi_table,
        test_compute_uses_shared_hi_resolver,
    )
    print("HI table extract + resolve (issue #3):")
    test_extract_fills_per_class_contract_with_excerpt_and_citation()
    test_caution_only_or_missing_excerpt_is_not_a_citation()
    test_mild_moderate_severe_maps_to_abc_and_is_flagged()
    test_no_adjustment_necessary_is_fold_one()
    test_missing_a_is_fold_one_missing_b_uses_c_else_abstain()
    test_missing_c_uses_moderate_else_abstain()
    test_user_adult_dose_overrides_label_fold_only_without_dose_abstains()
    test_indication_stratified_rows_must_match_or_abstain()
    test_resolver_is_single_implementation()
    test_live_extract_from_openfda_style_label()
    test_non_hepatic_severity_is_not_a_citation()
    test_both_facades_share_resolve_hi_dose()
    test_retrieval_attaches_live_hi_table()
    test_compute_uses_shared_hi_resolver()
    from tests.test_hi_gate import (
        test_pediatric_healthy_liver_still_submits,
        test_pediatric_hepatic_requires_class_or_complete_labs,
        test_adult_hi_requires_class_even_if_hepatic_box_off,
        test_empty_ascites_is_not_implicit_none,
        test_age_does_not_switch_facades,
        test_normalize_adult_hi_sets_hepatic_and_flags_child_pugh_on_child,
        test_resolve_does_not_default_missing_signs,
        test_server_rejects_incomplete_hi,
    )
    print("HI gate + calculator toggle (issue #4):")
    test_pediatric_healthy_liver_still_submits()
    test_pediatric_hepatic_requires_class_or_complete_labs()
    test_adult_hi_requires_class_even_if_hepatic_box_off()
    test_empty_ascites_is_not_implicit_none()
    test_age_does_not_switch_facades()
    test_normalize_adult_hi_sets_hepatic_and_flags_child_pugh_on_child()
    test_resolve_does_not_default_missing_signs()
    test_server_rejects_incomplete_hi()
    from tests.test_pediatric_hi import (
        test_hepatic_fm_share_and_gate,
        test_bake_then_allometry_keeps_hepatic_of_one,
        test_low_hepatic_fm_does_not_enter,
        test_no_cited_row_abstains,
        test_adult_label_grade_cap_b,
        test_renal_plus_hi_stacked_cap_c,
        test_oral_high_e_requires_oral_product_row,
        test_pediatric_guideline_beats_adult_label,
        test_cap_grade_never_raises,
    )
    print("Pediatric HI facade (issue #5):")
    test_hepatic_fm_share_and_gate()
    test_bake_then_allometry_keeps_hepatic_of_one()
    test_low_hepatic_fm_does_not_enter()
    test_no_cited_row_abstains()
    test_adult_label_grade_cap_b()
    test_renal_plus_hi_stacked_cap_c()
    test_oral_high_e_requires_oral_product_row()
    test_pediatric_guideline_beats_adult_label()
    test_cap_grade_never_raises()
    from tests.test_adult_hi import (
        test_adult_hi_emits_three_outcomes,
        test_no_allometry_and_no_ad_grade,
        test_same_hi_module_no_second_parser,
        test_oral_high_e_same_rule,
        test_adult_label_beats_pediatric_guideline,
        test_fold_only_no_adult_dose_abstains,
        test_contraindicated_blocked_no_dose,
        test_age_under_18_still_adult_facade,
        test_run_case_short_circuits_orchestrator,
    )
    print("Adult HI facade (issue #6):")
    test_adult_hi_emits_three_outcomes()
    test_no_allometry_and_no_ad_grade()
    test_same_hi_module_no_second_parser()
    test_oral_high_e_same_rule()
    test_adult_label_beats_pediatric_guideline()
    test_fold_only_no_adult_dose_abstains()
    test_contraindicated_blocked_no_dose()
    test_age_under_18_still_adult_facade()
    test_run_case_short_circuits_orchestrator()
    # PBPK trial facade (branch muse-spark-pbpk) — axe with the branch.
    from tests.test_pbpk import ALL as PBPK_TESTS
    print("PBPK trial facade (branch muse-spark-pbpk):")
    for _fn in PBPK_TESTS:
        _fn()
    print(f"  {len(PBPK_TESTS)} tests passed.")
    concordance_check()
    print("\nAll structural tests passed.")
