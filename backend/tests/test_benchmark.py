"""
FDA-label benchmark harness (harness only — product code never imports `benchmark`).
Deterministic, no API key, no network: label text is snapshotted in benchmark/labels/.

Run:  python3 -m pytest -q tests/test_benchmark.py
"""

import math

from benchmark.growth import median_weight_kg


def test_growth_reference_uses_who_under_five_and_cdc_after():
    # WHO 2006 day-0 medians: boys 3.3464, girls 3.2322 kg -> sex average 3.2893
    assert abs(median_weight_kg(age_days=0) - 3.2893) < 1e-3
    # CDC 2000 at 120.5 months: boys 32.088, girls 33.064 -> 32.576
    assert abs(median_weight_kg(age_days=120.5 * 30.4375) - 32.576) < 1e-2
    # monotone across the WHO -> CDC seam
    assert median_weight_kg(age_days=1850) < median_weight_kg(age_days=1950)


def test_preterm_weight_comes_from_the_preterm_reference():
    w28 = median_weight_kg(age_days=0, gestational_age_weeks=28)
    assert 0.9 < w28 < 1.4, w28            # Fenton 50th centile region at 28 wk
    assert w28 < median_weight_kg(age_days=0, gestational_age_weeks=34)


# ---------------------------------------------------------------------------
# Reference-set integrity: every number is backed by verbatim label text.
# ---------------------------------------------------------------------------
import json
import os
import re

BENCH = os.path.join(os.path.dirname(__file__), "..", "benchmark")


def _refset():
    with open(os.path.join(BENCH, "reference_set.json")) as f:
        return json.load(f)["drugs"]


def _label_text(name):
    with open(os.path.join(BENCH, "labels", name)) as f:
        return " ".join(json.load(f)["sections"].values())


def test_every_reference_number_has_a_verbatim_label_quote():
    for drug, d in _refset().items():
        if not d["included"]:
            assert d["excluded_by"] in {"E1", "E2", "E3", "E4"} and d["reason"], drug
            continue
        text = _label_text(d["label"])
        quotes = [d["fe"]["quote"], d["adult"]["quote"]] + [b["quote"] for b in d["bands"]]
        for q in quotes:
            assert q and q in text, (drug, q[:80])


def test_reference_doses_sit_inside_their_labeled_ranges():
    for drug, d in _refset().items():
        if not d["included"]:
            continue
        lo, hi = d["adult"]["range_daily"]
        assert lo <= d["adult"]["daily"] <= hi, drug
        assert d["bands"], drug
        for b in d["bands"]:
            lo, hi = b["range_per_kg_daily"]
            assert lo <= b["ref_per_kg_daily"] <= hi, (drug, b["id"])
            assert 0 <= b["pna_days"][0] <= b["pna_days"][1] <= 18 * 365.25, (drug, b["id"])


def test_model_inputs_follow_the_protocol_class_rule():
    rule = {"aminoglycoside": "cmax", "beta-lactam": "time_mic"}
    for drug, d in _refset().items():
        if d["included"]:
            assert d["target_metric"] == rule.get(d["class"], "css"), drug
            assert 0.0 <= d["fe"]["value"] <= 1.0, drug
            assert d["nonrenal_enzyme"] in (None, "cyp3a4", "ugt2b7"), drug


def test_product_code_never_imports_the_benchmark_or_eval_data():
    root = os.path.join(os.path.dirname(__file__), "..")
    for pkg in ("engine", "agents", "api", "retrieval"):
        for dirpath, _, files in os.walk(os.path.join(root, pkg)):
            for fn in files:
                if fn.endswith(".py"):
                    src = open(os.path.join(dirpath, fn)).read()
                    assert not re.search(r"^\s*(from|import)\s+benchmark\b", src, re.M), fn


# ---------------------------------------------------------------------------
# Scaling methods (identical inputs for all) and endpoint arithmetic.
# ---------------------------------------------------------------------------
from benchmark.methods import METHODS, predict_band, virtual_patients
from benchmark.metrics import cluster_bootstrap_ci, summarize

CSS_DRUG = {"target_metric": "css", "fe": {"value": 0.9}, "nonrenal_enzyme": None,
            "adult": {"daily": 700.0}}
CMAX_DRUG = dict(CSS_DRUG, target_metric="cmax")
BAND_6Y = {"pna_days": [6 * 365.25, 6 * 365.25], "ga_weeks": None}
BAND_NEO = {"pna_days": [0, 7], "ga_weeks": None}


def test_virtual_patients_use_a_log_spaced_grid_inside_the_band():
    pts = virtual_patients(BAND_NEO)
    ages = [p["pna_days"] for p in pts]
    assert len(pts) == 7 and ages[0] == 1.0 and abs(ages[-1] - 7.0) < 1e-9
    assert all(b > a for a, b in zip(ages, ages[1:]))
    assert len(virtual_patients(BAND_6Y)) == 1


def test_weight_linear_is_the_adult_mg_per_kg_at_any_age():
    assert abs(predict_band("weight_linear", CSS_DRUG, BAND_NEO) - 10.0) < 1e-9
    assert abs(predict_band("weight_linear", CSS_DRUG, BAND_6Y) - 10.0) < 1e-9


def test_allometry_gives_more_per_kg_to_smaller_children():
    w = virtual_patients(BAND_6Y)[0]["weight_kg"]
    expected = 10.0 * (w / 70.0) ** -0.25
    assert abs(predict_band("allometry", CSS_DRUG, BAND_6Y) - expected) < 1e-9


def test_paedscale_ties_weight_linear_for_cmax_drugs():
    for band in (BAND_NEO, BAND_6Y):
        assert abs(predict_band("paedscale", CMAX_DRUG, band) - predict_band("weight_linear", CMAX_DRUG, band)) < 1e-9
        assert abs(predict_band("allometry_class", CMAX_DRUG, band) - predict_band("weight_linear", CMAX_DRUG, band)) < 1e-9


def test_paedscale_differs_from_allometry_class_only_by_maturation():
    # A newborn on the steep GFR curve gets far less than size-only allometry...
    assert predict_band("paedscale", CSS_DRUG, BAND_NEO) < 0.6 * predict_band("allometry_class", CSS_DRUG, BAND_NEO)
    # ...an adolescent on the plateau gets essentially the same.
    teen = {"pna_days": [15 * 365.25, 15 * 365.25], "ga_weeks": None}
    assert abs(predict_band("paedscale", CSS_DRUG, teen) / predict_band("allometry_class", CSS_DRUG, teen) - 1) < 0.01
    assert set(METHODS) == {"weight_linear", "bsa", "allometry", "allometry_class", "paedscale"}


def test_endpoint_arithmetic_on_a_worked_example():
    rows = [{"drug": "a", "fe": 2.0}, {"drug": "a", "fe": 0.5}]
    s = summarize(rows)
    assert abs(s["aafe"] - 2.0) < 1e-9 and abs(s["afe"] - 1.0) < 1e-9
    assert s["within_2"] == 1.0 and s["within_1_5"] == 0.0


def test_aggregation_is_drug_weighted():
    rows = [{"drug": "a", "fe": 1.0}, {"drug": "a", "fe": 1.0}, {"drug": "b", "fe": 10.0}]
    assert abs(summarize(rows)["aafe"] - 10 ** 0.5) < 1e-9          # (0 + 1) / 2 drugs
    assert abs(summarize(rows, weight="pair")["aafe"] - 10 ** (1 / 3)) < 1e-9


def test_cluster_bootstrap_is_seeded_and_brackets_the_estimate():
    rows = [{"drug": d, "fe": f} for d, f in zip("abcdefgh", [1.1, 0.8, 1.6, 0.9, 1.3, 2.2, 0.7, 1.0])]
    stat = lambda rs: summarize(rs)["aafe"]
    a = cluster_bootstrap_ci(rows, stat, n_boot=2000, seed=3)
    b = cluster_bootstrap_ci(rows, stat, n_boot=2000, seed=3)
    assert a == b and a["lo"] <= stat(rows) <= a["hi"] and a["n_clusters"] == 8
