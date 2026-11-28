"""Build the PaedScale manuscript from the committed outputs of both evaluations.

Every result in the manuscript comes through a {{placeholder}} from the label benchmark
(backend/benchmark/output/results.json, backend/benchmark/reference_set.json) or the clearance
validation (backend/benchmark/external/output/results.json, dataset/agreement.json, the search
snapshot and extraction/final/). Design constants of the protocols (curve parameters, seeds,
grid sizes) are stated in the text. The build stops on outputs from a dirty tree and on a
rendered text that breaks the journal's limits (bjcp_problems).

Usage (from the repo root):  python3 -m paper.build [--pdf]
Writes paper/build/manuscript.md, manuscript.html and, with --pdf, manuscript.pdf.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "backend", "benchmark")
OUTPUT = os.path.join(BENCH, "output")
EXT = os.path.join(BENCH, "external")
EXT_OUTPUT = os.path.join(EXT, "output")
HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")

METHOD_LABEL = {"weight_linear": "Weight-linear", "bsa": "Body surface area",
                "allometry": "Allometry only", "allometry_class": "Allometry + class rule (A1)",
                "paedscale": "PaedScale"}
METHOD_ORDER = ["weight_linear", "bsa", "allometry", "allometry_class", "paedscale"]
POPULATION_LABEL = {"newborn": "Newborns (<28 d)", "under2": "Under 2 years", "all": "All ages"}
STRATUM_LABEL = {"preterm_newborn": "Preterm newborn", "term_newborn": "Term newborn",
                 "infant_toddler": "Infant/toddler", "child": "Child 2–11 y",
                 "adolescent": "Adolescent 12–16 y"}
SENSITIVITY_LABEL = {
    "S1_exclude_mgkg_shared": "S1 Exclude pairs with the same adult and child mg/kg",
    "S2_exclude_mismatch_qualitative_upto": "S2 Exclude indication-mismatch, qualitative-fe and up-to pairs",
    "S3_all_css": "S3 Every drug matched on average concentration",
    "S4_weight_minus20": "S4 Weight −20%",
    "S4_weight_plus20": "S4 Weight +20%",
    "S5_ga_minus2": "S5 Gestational age −2 weeks (preterm bands)",
    "S5_ga_plus2": "S5 Gestational age +2 weeks (preterm bands)",
    "S7_exclude_curve_source_drugs": "S7 Exclude the curve-source drug (morphine)",
    "S8_exclude_titrated": "S8 Exclude titrated drugs",
    "S9_gfr_only_renal": "S9 Renal drugs cleared by filtration only",
    "S10_midpoint_child": "S10 One child at the band midpoint",
}


def render(template: str, values: dict) -> str:
    """Fill every {{key}}. An unknown key stops the build, so no placeholder can leak."""
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", template)) - set(values))
    if missing:
        raise KeyError(f"no value for placeholder(s): {', '.join(missing)}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values[m.group(1)]), template)


def _ratio(x: float) -> str:
    """Two decimals, unless that would round a value that is not 1 onto 1.00."""
    s = f"{x:.2f}"
    return f"{x:.4f}" if s == "1.00" and abs(x - 1) > 5e-5 else s


def ratio_with_ci(h: dict, label: bool = True) -> str:
    """A paired log10 difference in |log10 FE| and its CI, read as a ratio of typical fold errors.
    Table cells drop the "95% CI" label, which their column header carries."""
    lo, hi = (10 ** v for v in h["ci95"])
    return f"{_ratio(10 ** h['mean_abs_log10_diff'])} ({'95% CI ' if label else ''}{_ratio(lo)}–{_ratio(hi)})"


def _fold(x: float, ci: list | None) -> str:
    return f"{_ratio(x)} ({_ratio(ci[0])}–{_ratio(ci[1])})" if ci else _ratio(x)


def _pct(x: float, ci: list | None) -> str:
    return f"{100 * x:.0f}% ({100 * ci[0]:.0f}–{100 * ci[1]:.0f})" if ci else f"{100 * x:.0f}%"


def _p(p: float | None) -> str:
    return "—" if p is None else (f"{p:.3f}" if p >= 0.001 else "<0.001")


def method_table(results: dict, population: str) -> str:
    rows = ["| Method | AAFE (95% CI) | AFE (95% CI) | Within 0.67–1.5× (95% CI) | Within 0.5–2× (95% CI) | "
            "Within labeled range (95% CI) | Pair-weighted AAFE (95% CI) |",
            "|---|---|---|---|---|---|---|"]
    for m in METHOD_ORDER:
        s = results["by_method"][population][m]
        rows.append(f"| {METHOD_LABEL[m]} | {_fold(s['aafe'], s.get('aafe_ci95'))} | "
                    f"{_fold(s['afe'], s.get('afe_ci95'))} | {_pct(s['within_1_5'], s.get('within_1_5_ci95'))} | "
                    f"{_pct(s['within_2'], s.get('within_2_ci95'))} | "
                    f"{_pct(s['within_label_range'], s.get('within_label_range_ci95'))} | "
                    f"{_fold(s['pair_weighted_aafe'], s.get('pair_weighted_aafe_ci95'))} |")
    return "\n".join(rows)


def _h_row(study, key, pop, h, drugs, n, supported, sign_p=None):
    return (f"| {study} | {key} | {pop} | {drugs} | {n} | {ratio_with_ci(h, label=False)} | "
            f"{_p(h.get('wilcoxon_p_drug_level'))} | {_p(sign_p)} | {'Yes' if supported else 'No'} |")


def hypothesis_table(results: dict, ext: dict) -> str:
    """Both studies' pre-specified hypotheses in one table (label: H1–H3, external: HE1–HE2)."""
    rows = ["| Study | Hypothesis | Population | Drugs | Pairs or observations | Ratio of typical fold error (95% CI) | "
            "Wilcoxon p (drug level) | Sign-flip p | Supported |",
            "|---|---|---|---|---|---|---|---|---|"]
    pops = {"H1": "Newborns (<28 days)", "H2": "Children under 2 years", "H3": "All ages"}
    for k in ("H1", "H2", "H3"):
        h = results["hypotheses"][k]
        rows.append(_h_row("Label", k, pops[k], h, h["n_clusters"], h["n_pairs"], h["significant"]))
    for k, key, pop in (("HE1_under2", "HE1", "Children under 2 years"), ("HE2_all_ages", "HE2", "All ages")):
        h = ext["hypotheses"][k]
        rows.append(_h_row("Clearance", key, pop, h, h["n_drugs"], h["n_obs"], h["success"], h.get("sign_flip_p")))
    return "\n".join(rows)


EXT_METHODS = ["weight_linear", "bsa", "allometry", "paedscale"]
EXT_METHOD_LABEL = {**METHOD_LABEL, "allometry": "Allometry (primary comparator)"}


def external_method_table(ext: dict) -> str:
    rows = ["| Method | Under 2 years: AAFE (95% CI) | Under 2 years: AFE (95% CI) | All ages: AAFE (95% CI) | "
            "All ages: AFE (95% CI) | All ages: within 0.67–1.5× (95% CI) | All ages: within 0.5–2× (95% CI) |",
            "|---|---|---|---|---|---|---|"]
    for m in EXT_METHODS:
        u, a = ext["by_method"]["under2"][m], ext["by_method"]["all"][m]
        rows.append(f"| {EXT_METHOD_LABEL[m]} | {_fold(u['aafe'], u.get('aafe_ci95'))} | {_fold(u['afe'], u.get('afe_ci95'))} | "
                    f"{_fold(a['aafe'], a.get('aafe_ci95'))} | {_fold(a['afe'], a.get('afe_ci95'))} | "
                    f"{_pct(a['within_1_5'], a.get('within_1_5_ci95'))} | {_pct(a['within_2'], a.get('within_2_ci95'))} |")
    return "\n".join(rows)


def label_method_table(results: dict) -> str:
    rows = ["| Method | Newborns: AAFE (95% CI) | Under 2 years: AAFE (95% CI) | All ages: AAFE (95% CI) | "
            "All ages: AFE (95% CI) |", "|---|---|---|---|---|"]
    for m in METHOD_ORDER:
        n, u, a = (results["by_method"][p][m] for p in ("newborn", "under2", "all"))
        rows.append(f"| {METHOD_LABEL[m]} | {_fold(n['aafe'], n.get('aafe_ci95'))} | {_fold(u['aafe'], u.get('aafe_ci95'))} | "
                    f"{_fold(a['aafe'], a.get('aafe_ci95'))} | {_fold(a['afe'], a.get('afe_ci95'))} |")
    return "\n".join(rows)


def external_flow(ext_dir: str) -> dict:
    """Search, pre-filter, screening and inclusion counts from the committed snapshot and final record."""
    from collections import Counter
    flow = Counter()
    reasons = Counter()
    names = sorted(f[:-5] for f in os.listdir(os.path.join(ext_dir, "search")) if f.endswith(".json"))
    for d in names:
        with open(os.path.join(ext_dir, "search", f"{d}.json")) as f:
            snap = json.load(f)
        with open(os.path.join(ext_dir, "extraction", "final", f"{d}.json")) as f:
            fin = json.load(f)
        for k, tag in (("pediatric", "ped"), ("adult", "adult")):
            flow[f"{tag}_hits"] += len(snap[k])
            flow[f"{tag}_prefilter"] += sum(1 for r in snap[k] if r.get("prefilter"))
            flow[f"{tag}_screened"] += len(fin[k])
            flow[f"{tag}_included"] += sum(s["decision"] == "include" for s in fin[k])
        flow["ped_obs"] += sum(len(s["observations"]) for s in fin["pediatric"] if s["decision"] == "include")
        for s in fin["pediatric"]:
            if s["decision"] == "exclude":
                reasons[_reason_group(s["reason"])] += 1
    return {**flow, "drugs": len(names), "ped_reasons": dict(reasons)}


REASON_GROUPS = [   # (prefixes of the recorded reason, group shown in the manuscript)
    (("cl/f", "p1: intramuscular"), "oral or intramuscular dosing, or apparent clearance (CL/F) only"),
    (("p1",), "not a primary study of children given the drug (adults, pregnancy, animals, reviews, simulations)"),
    (("p4",), "restricted population (extracorporeal support, hypothermia, organ impairment, burns, cystic fibrosis)"),
    (("no age",), "no stated age"),
    (("not total iv cl",), "per-70 kg value without an age, or a unit that cannot be converted"),
    (("range only",), "clearance given only as a range"),
    (("p2",), "no usable clearance (none reported, another drug, an equation only, or a typical value without its covariates)"),
]


def _reason_group(reason: str) -> str:
    r = reason.lower()
    for prefixes, group in REASON_GROUPS:
        if r.startswith(prefixes):
            return group
    raise ValueError(f"exclusion reason with no group: {reason!r}")


def secondary_table(results: dict) -> str:
    rows = ["| Comparator | Ratio of typical fold error, PaedScale ÷ comparator (95% CI) | Wilcoxon p | Holm-adjusted p |",
            "|---|---|---|---|"]
    for m in ("weight_linear", "bsa", "allometry"):
        s = results["secondary"][m]
        rows.append(f"| {METHOD_LABEL[m]} | {ratio_with_ci(s, label=False)} | {_p(s.get('wilcoxon_p_drug_level'))} | "
                    f"{_p(s.get('wilcoxon_p_holm'))} |")
    return "\n".join(rows)


EXT_SENSITIVITY_LABEL = {
    "E1_exclude_imputed_weight_or_ga": "E1 Exclude imputed weight or gestational age",
    "E2_exclude_critically_ill": "E2 Exclude critically ill groups",
    "E3_exclude_standardized_or_fixed": "E3 Exclude values from allometric or fixed-maturation models",
    "E4_first_adult_abstract": "E4 First qualifying adult abstract only",
    "E5_study_weighted": "E5 Each study weighted equally",
    "E7_exclude_curve_source_authors": "E7 Exclude studies by authors of the curve sources",
    "E8_exclude_before_1995": "E8 Exclude studies published before 1995",
    "E9_exclude_route_unstated": "E9 Exclude studies with no stated route",
}


def _cell(h: dict | None, n_key: str) -> str:
    if not h or not h.get(n_key) or not h.get("ci95"):
        return "not estimable"
    return f"{h[n_key]}, {ratio_with_ci(h, label=False)}"


def sensitivity_table(results: dict, ext: dict) -> str:
    rows = ["| Analysis | Primary population: drugs, ratio (95% CI) | All ages: drugs, ratio (95% CI) |",
            "|---|---|---|",
            "| **Label benchmark** (primary population: newborns) | | |"]
    sens = results["sensitivity"]
    unknown = sorted(set(sens) - set(SENSITIVITY_LABEL) - {"S6_leave_one_drug_out"})
    if unknown:
        raise KeyError(f"no label for sensitivity analysis: {', '.join(unknown)}")
    for k, label in SENSITIVITY_LABEL.items():
        if k in sens:
            rows.append(f"| {label} | {_cell(sens[k].get('newborn'), 'n_clusters')} | {_cell(sens[k].get('all'), 'n_clusters')} |")
        if k == "S5_ga_plus2":
            rows.append(f"| S6 Leave one drug out (range of point estimates) | {s6_range(results, 'newborn')} | "
                        f"{s6_range(results, 'all')} |")
    rows.append("| **Clearance validation** (primary population: under 2 years) | | |")
    es = ext["sensitivity"]
    unknown = sorted(set(es) - set(EXT_SENSITIVITY_LABEL) - {"E6_leave_one_drug_out"})
    if unknown:
        raise KeyError(f"no label for sensitivity analysis: {', '.join(unknown)}")
    for k, label in EXT_SENSITIVITY_LABEL.items():
        rows.append(f"| {label} | {_cell(es[k].get('HE1_under2'), 'n_drugs')} | {_cell(es[k].get('HE2_all_ages'), 'n_drugs')} |")
        if k == "E5_study_weighted":
            e6 = es["E6_leave_one_drug_out"]
            rng = lambda h: f"{_ratio(10 ** h['min'])} to {_ratio(10 ** h['max'])}"
            rows.append(f"| E6 Leave one drug out (range of point estimates) | {rng(e6['HE1_under2'])} | {rng(e6['HE2_all_ages'])} |")
    return "\n".join(rows)


def s6_range(results: dict, population: str) -> str:
    s6 = results["sensitivity"]["S6_leave_one_drug_out"][population]
    return f"{_ratio(10 ** s6['min'])} to {_ratio(10 ** s6['max'])}"


METRIC_NAME = {"css": "Average concentration", "auc": "Exposure (AUC)", "cmax": "Peak concentration",
               "time_mic": "Daily exposure (proxy for time above MIC)"}
ENZYME_NAME = {"cyp3a4": "CYP3A4", "ugt2b7": "UGT2B7"}
CLASS_NAME = {"beta-lactam": "β-lactam", "NRTI": "nucleoside reverse transcriptase inhibitor"}


def _display(names: dict, code: str | None) -> str:
    """A recorded code in words; a code without a display name is shown as recorded, an absent one as a dash."""
    return "—" if code is None else names.get(code, code)


def drug_table(refset: dict) -> str:
    rows = ["| Drug | Class | Target metric | fe (urine, unchanged) | Non-renal enzyme | Age bands |",
            "|---|---|---|---|---|---|"]
    for name, d in sorted(refset["drugs"].items()):
        if not d.get("included"):
            continue
        fe = d.get("fe") or {}
        fev = fe.get("value")
        note = {"fe_qualitative": " (qualitative)", "fe_not_in_label": " (not in label)"}
        tag = "".join(note[f] for f in fe.get("flags", []) if f in note)
        rows.append(f"| {drug_name(name)} | {_display(CLASS_NAME, d.get('class'))} | "
                    f"{_display(METRIC_NAME, d['target_metric'])} | "
                    f"{'—' if fev is None else f'{fev:.3f}{tag}'} | {_display(ENZYME_NAME, d.get('nonrenal_enzyme'))} | "
                    f"{len(d.get('bands') or [])} |")
    return "\n".join(rows)


def exclusion_table(results: dict) -> str:
    rows = ["| Drug | Criterion | Reason |", "|---|---|---|"]
    for name, e in sorted(results["excluded"].items()):
        rows.append(f"| {drug_name(name)} | {re.sub(r"\bE(\d)\b", r"L\1", e['criterion'])} | {e['reason']} |")
    return "\n".join(rows)


def stratum_table(results: dict) -> str:
    rows = ["| ICH E11 stratum | Drugs | Pairs | PaedScale AAFE | A1 AAFE | Weight-linear AAFE |",
            "|---|---|---|---|---|---|"]
    for st, label in STRATUM_LABEL.items():
        s = results["by_stratum"].get(st)
        if not s:
            continue
        p, a, w = s["paedscale"], s["allometry_class"], s["weight_linear"]
        rows.append(f"| {label} | {p['n_drugs']} | {p['n_pairs']} | {p['aafe']:.2f} | {a['aafe']:.2f} | {w['aafe']:.2f} |")
    return "\n".join(rows)


DRUG_NAME = {"acyclovir": "aciclovir", "penicillin_g": "benzylpenicillin", "piperacillin_tazobactam": "piperacillin (with tazobactam)"}


def drug_name(d: str) -> str:
    return DRUG_NAME.get(d, d.replace("_", " "))


EXT_STRATA = ["preterm_newborn", "term_newborn", "infant_toddler", "child", "adolescent"]
EXT_STRATUM_LABEL = {**STRATUM_LABEL, "adolescent": "Adolescent 12–17 y"}     # clearance protocol strata


def external_stratum_table(ext: dict) -> str:
    rows = ["| ICH E11 stratum | Drugs | Observations | PaedScale AAFE (AFE) | Allometry AAFE (AFE) | "
            "Weight-linear AAFE (AFE) | Ratio, PaedScale ÷ allometry (95% CI) |", "|---|---|---|---|---|---|---|"]
    for st in EXT_STRATA:
        v = ext["by_stratum"].get(st)
        if not v:
            continue
        bm, h = v["by_method"], v["paedscale_vs_allometry"]
        cell = lambda m: f"{bm[m]['aafe']:.2f} ({bm[m]['afe']:.2f})"
        ratio = ratio_with_ci(h, label=False) if h.get("ci95") else "fewer than 5 drugs"
        rows.append(f"| {EXT_STRATUM_LABEL[st]} | {bm['paedscale']['n_drugs']} | {bm['paedscale']['n_pairs']} | "
                    f"{cell('paedscale')} | {cell('allometry')} | {cell('weight_linear')} | {ratio} |")
    return "\n".join(rows)


def external_drug_table(ext: dict, ext_dir: str) -> str:
    rows = ["| Drug | Qualifying adult abstracts | Adult reference clearance, L/h at 70 kg | Pediatric studies included | "
            "Observations | Scored |", "|---|---|---|---|---|---|"]
    for d, a in sorted(ext["adult_reference"].items(), key=lambda kv: drug_name(kv[0])):
        with open(os.path.join(ext_dir, "extraction", "final", f"{d}.json")) as f:
            fin = json.load(f)
        inc = [x for x in fin["pediatric"] if x["decision"] == "include"]
        n_obs = sum(len(x["observations"]) for x in inc)
        cl = "—" if a["median_l_h"] is None else f"{a['median_l_h']:.2f}"
        scored = ("Yes" if d in ext["hypotheses"]["HE2_all_ages"]["per_drug_mean_d"]
                  else "No adult reference" if a["median_l_h"] is None else "No observations")
        rows.append(f"| {drug_name(d)} | {a['n_abstracts']} | {cl} | "
                    f"{len(inc)} | {n_obs} | {scored} |")
    return "\n".join(rows)


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else "none"


def external_values(ext: dict, agreement: dict, flow: dict) -> dict:
    v = {}
    for k, tag in (("HE1_under2", "he1"), ("HE2_all_ages", "he2")):
        h = ext["hypotheses"][k]
        v[f"ext_{tag}_ratio"] = ratio_with_ci(h)
        v[f"ext_{tag}_cell"] = ratio_with_ci(h, label=False)
        v[f"ext_{tag}_drugs"], v[f"ext_{tag}_obs"] = h["n_drugs"], h["n_obs"]
        v[f"ext_{tag}_p"] = _p(h.get("wilcoxon_p_drug_level"))
        v[f"ext_{tag}_signp"] = _p(h.get("sign_flip_p"))
    for pop in ("under2", "all"):
        for m in EXT_METHODS:
            s = ext["by_method"][pop][m]
            v[f"ext_{pop}_{m}_aafe"] = _fold(s["aafe"], s.get("aafe_ci95"))
            v[f"ext_{pop}_{m}_afe"] = _fold(s["afe"], s.get("afe_ci95"))
            v[f"ext_{pop}_{m}_w2"] = _pct(s["within_2"], s.get("within_2_ci95"))
            v[f"ext_{pop}_{m}_w15"] = _pct(s["within_1_5"], s.get("within_1_5_ci95"))
    for m in ("weight_linear", "bsa"):
        v[f"ext_sec_{m}"] = ratio_with_ci(ext["secondary"][m])
        v[f"ext_sec_{m}_holm"] = _p(ext["secondary"][m].get("wilcoxon_p_holm"))
    for st in EXT_STRATA:
        st_v = ext["by_stratum"].get(st) or {}
        h = st_v.get("paedscale_vs_allometry") or {}
        v[f"ext_st_{st}_ratio"] = ratio_with_ci(h) if h.get("ci95") else "not estimated"
        for m in EXT_METHODS:
            bm = (st_v.get("by_method") or {}).get(m)
            v[f"ext_st_{st}_{m}_afe"] = f"{bm['afe']:.2f}" if bm else "—"
            v[f"ext_st_{st}_{m}_aafe"] = f"{bm['aafe']:.2f}" if bm else "—"
    adult = ext["adult_reference"]
    no_adult = sorted(d for d, a in adult.items() if a["median_l_h"] is None)
    v["ext_no_adult"] = _and(sorted(drug_name(d) for d in no_adult))
    no_obs = sorted(d for d in adult if d not in ext["hypotheses"]["HE2_all_ages"]["per_drug_mean_d"] and d not in no_adult)
    v["ext_no_obs"] = _and(sorted(drug_name(d) for d in no_obs))
    v["ext_n_no_obs"] = len(no_obs)
    v["ext_scored_drugs"] = _and(sorted(drug_name(d) for d in ext["hypotheses"]["HE2_all_ages"]["per_drug_mean_d"]))
    he1, he2 = ext["hypotheses"]["HE1_under2"], ext["hypotheses"]["HE2_all_ages"]
    v["ext_he1_status"], v["ext_he1_verdict"] = _status(he1), _verdict(he1)
    v["ext_he2_sentence"] = _he2_sentence(he2, ratio_with_ci(he2))
    e1 = ext["sensitivity"]["E1_exclude_imputed_weight_or_ga"]["HE1_under2"]
    v["ext_e1_drugs"], v["ext_e1_status"] = e1["n_drugs"], _status(e1)
    v["ext_n_no_adult"] = len(no_adult)
    v["ext_n_drugs"], v["ext_n_obs"] = ext["n_drugs"], ext["n_obs"]
    per = ext["hypotheses"]["HE2_all_ages"]["per_drug_mean_d"]
    v["ext_n_favour"] = sum(d < 0 for d in per.values())
    v["ext_not_favour"] = _and(sorted(drug_name(k) for k, d in per.items() if d >= 0))
    v["ext_he1_reduction"] = f"{100 * (1 - 10 ** ext['hypotheses']['HE1_under2']['mean_abs_log10_diff']):.0f}%"
    e6 = ext["sensitivity"]["E6_leave_one_drug_out"]["HE1_under2"]
    v["ext_e6_he1"] = f"{_ratio(10 ** e6['min'])} to {_ratio(10 ** e6['max'])}"
    he1_sens = [h["HE1_under2"] for k, h in ext["sensitivity"].items() if k != "E6_leave_one_drug_out"]
    v["ext_n_sens"] = len(he1_sens)
    v["ext_n_sens_excluding_1"] = sum(1 for h in he1_sens if h.get("ci95") and h["ci95"][1] < 0)
    v["ext_coverage"] = f"{100 * ext['uncertainty_coverage']['coverage_90_drug_weighted']:.0f}%"
    v["ext_kappa"] = f"{agreement['kappa_overall']:.2f}"
    v["ext_both_read"] = agreement["both_read"]
    v["ext_dec_dis"] = agreement["n_decision_disagreements"]
    v["ext_val_agree"] = agreement["n_value_agreements"]
    v["ext_both_incl"] = agreement["n_value_agreements"] + agreement["n_value_disagreements"]
    v["ext_num_compared"], v["ext_num_differ"] = agreement["n_values_compared"], agreement["n_values_differ"]
    for k in ("drugs", "ped_hits", "ped_prefilter", "ped_screened", "ped_included", "ped_obs",
              "adult_hits", "adult_prefilter", "adult_screened", "adult_included"):
        v[f"ext_{k}"] = f"{flow[k]:,}"
    reasons = sorted(flow["ped_reasons"].items(), key=lambda kv: -kv[1])
    v["ext_ped_reasons"] = "; ".join(f"{r}, {n}" for r, n in reasons)
    return v


def values(results: dict, refset: dict) -> dict:
    hyp, bm, cov, prov = results["hypotheses"], results["by_method"], results["uncertainty_coverage"], results["provenance"]
    v = {
        "n_candidates": len(refset["drugs"]),
        "n_drugs": results["n_included_drugs"], "n_bands": results["n_bands"],
        "n_excluded": len(results["excluded"]),
        "excluded_list": ", ".join(sorted(results["excluded"])),
        "engine_commit": prov["engine_commit"][:7], "n_boot": f"{prov['n_boot']:,}", "seed": prov["seed"],
        "python_version": prov["versions"]["python"], "numpy_version": prov["versions"]["numpy"],
        "scipy_version": prov["versions"]["scipy"],
        "coverage": _pct(cov["coverage_90"], cov.get("coverage_90_ci95")),
        "cov_median_width": f"{cov['median_fold_width']:.3f}", "cov_max_width": f"{cov['max_fold_width']:.2f}",
        "cov_blocked": cov["n_bands_blocked"],
        "table_drugs": drug_table(refset), "table_excluded": exclusion_table(results),
        "table_secondary": secondary_table(results), "table_strata": stratum_table(results),
        "table_label_methods": label_method_table(results),
    }
    for pop in ("newborn", "under2", "all"):
        v[f"table_methods_{pop}"] = method_table(results, pop)
        for m in METHOD_ORDER:
            s = bm[pop][m]
            v[f"{pop}_{m}_aafe"] = _fold(s["aafe"], s.get("aafe_ci95"))
            v[f"{pop}_{m}_afe"] = _fold(s["afe"], s.get("afe_ci95"))
            v[f"{pop}_{m}_w15"] = _pct(s["within_1_5"], s.get("within_1_5_ci95"))
            v[f"{pop}_{m}_w2"] = _pct(s["within_2"], s.get("within_2_ci95"))
    for k in ("H1", "H2", "H3"):
        h = hyp[k]
        v[f"{k}_ratio"] = ratio_with_ci(h)
        v[f"{k}_drugs"], v[f"{k}_pairs"] = h["n_clusters"], h["n_pairs"]
        v[f"{k}_p"] = _p(h.get("wilcoxon_p_drug_level"))
        v[f"{k}_ties"] = h["n_tied_pairs"]
    for m in ("weight_linear", "bsa", "allometry"):
        v[f"sec_{m}"] = ratio_with_ci(results["secondary"][m])
        v[f"sec_{m}_holm"] = _p(results["secondary"][m].get("wilcoxon_p_holm"))
    for pop in ("newborn", "all"):
        v[f"s6_{pop}"] = s6_range(results, pop)
    newborn = [h.get("newborn") or {} for k, h in results["sensitivity"].items() if k != "S6_leave_one_drug_out"]
    v["label_n_sens"] = len(newborn)
    v["label_n_sens_crossing_1"] = sum(1 for h in newborn if not h.get("ci95") or h["ci95"][1] >= 0)
    return v


def word_count(markdown: str) -> int:
    """Words from the Introduction to the end of the Discussion, without tables, figures or captions."""
    body = markdown[markdown.index("# Introduction"):markdown.index("# Declarations")]
    body = re.sub(r"^\|.*\|$", "", body, flags=re.M)
    body = re.sub(r"!\[.*?\]\(.*?\)", "", body)
    body = re.sub(r"^Table: .*$", "", body, flags=re.M)
    return len(body.split())


def _status(h: dict) -> str:
    return "confirmatory" if h.get("confirmatory") else "descriptive"


def _verdict(h: dict) -> str:
    return "succeeded" if h.get("success") else "did not succeed"


def _he2_sentence(he2: dict, ratio: str) -> str:
    if not he2.get("tested"):
        return "HE2 was therefore not tested."
    return (f"HE2 was therefore tested, and it also succeeded: {ratio} at all ages." if he2.get("success")
            else f"HE2 was therefore tested, and it did not succeed: {ratio} at all ages.")


def _n_of(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _main_text(markdown: str) -> str:
    return markdown[markdown.index("# Introduction"):markdown.index("# Declarations")]


def table_and_figure_counts(markdown: str) -> dict:
    """Main-text tables and figures, and the supporting ones."""
    main, supp = _main_text(markdown), markdown[markdown.index("# Supporting information"):]
    return {"tables": main.count("Table: **Table"), "figures": len(re.findall(r"!\[\*\*Figure", main)),
            "supp_tables": len(re.findall(r"^## Table S", supp, flags=re.M)),
            "supp_figures": len(re.findall(r"^## Figure S", supp, flags=re.M))}


def _section(markdown: str, heading: str) -> str:
    i = markdown.index(heading) + len(heading)
    j = markdown.find("\n#", i)
    return markdown[i:j if j >= 0 else None]


def bjcp_problems(markdown: str) -> list[str]:
    """The British Journal of Clinical Pharmacology limits (paper/BJCP_REQUIREMENTS.md)."""
    out = []
    m = re.search(r'^title: "(.*)"$', markdown, flags=re.M)
    if not m:
        return ["title is missing from the front matter"]
    title = m.group(1)
    if len(title) > 150:
        out.append(f"title has {len(title)} characters (limit 150)")
    if re.search(r"\b[A-Z]{2,}\b", title):
        out.append("title contains an abbreviation")
    abstract = _section(markdown, "# Abstract")
    if len(abstract.split()) > 250:
        out.append(f"abstract has {len(abstract.split())} words (limit 250)")
    for h in ("**Aim.**", "**Methods.**", "**Results.**", "**Conclusion.**"):
        if h not in abstract:
            out.append(f"abstract lacks {h}")
    for box in ("## What is already known about this subject", "## What this study adds"):
        bullets = [b for b in _section(markdown, box).splitlines() if b.startswith("- ")]
        words = sum(len(b.split()) - 1 for b in bullets)
        if len(bullets) > 3 or words > 50:
            out.append(f"{box[3:]}: {len(bullets)} bullets, {words} words (limits 3 and 50)")
    c = table_and_figure_counts(markdown)
    if c["tables"] + c["figures"] > 8:
        out.append(f"{c['tables']} tables and {c['figures']} figures in the main text (limit 8)")
    return out


def render_manuscript(template: str, v: dict) -> str:
    """Fill the template, with the word, table and figure counts of the filled text itself."""
    draft = render(template, {**v, "word_count": "0", "n_tables": "0", "n_figures": "0",
                              "n_supp_tables": "0", "n_supp_figures": "0"})
    c = table_and_figure_counts(draft)
    return render(template, {**v, "word_count": f"{word_count(draft):,}", "n_tables": c["tables"],
                             "n_figures": c["figures"], "n_supp_tables": _n_of(c["supp_tables"], "table"),
                             "n_supp_figures": _n_of(c["supp_figures"], "figure")})


def check_provenance(prov: dict) -> None:
    if prov.get("working_tree_dirty"):
        raise ValueError(f"outputs at {prov.get('engine_commit')} come from a dirty working tree; rerun from a clean commit")


def load_external() -> tuple[dict, dict, dict]:
    with open(os.path.join(EXT_OUTPUT, "results.json")) as f:
        ext = json.load(f)
    with open(os.path.join(EXT, "dataset", "agreement.json")) as f:
        agreement = json.load(f)
    return ext, agreement, external_flow(EXT)


def all_values(results: dict, refset: dict, ext: dict, agreement: dict, flow: dict) -> dict:
    for prov in (results["provenance"], ext["provenance"]):
        check_provenance(prov)
    if ext["provenance"]["versions"] != results["provenance"]["versions"]:
        raise ValueError("the two evaluations' outputs were made with different software versions")
    v = {**values(results, refset), **external_values(ext, agreement, flow)}
    v["table_hypotheses"] = hypothesis_table(results, ext)
    v["table_sensitivity"] = sensitivity_table(results, ext)
    v["table_ext_methods"] = external_method_table(ext)
    v["table_ext_strata"] = external_stratum_table(ext)
    v["table_ext_drugs"] = external_drug_table(ext, EXT)
    v["ext_engine_commit"] = ext["provenance"]["engine_commit"][:7]
    for pop in ("newborn", "under2", "all"):
        v[f"table_label_methods_{pop}"] = method_table(results, pop)
    return v


def _pdf(html_path: str, pdf_path: str) -> None:
    subprocess.run(["node", os.path.join(HERE, "pdf.js"), html_path, pdf_path], check=True)


def main(pdf: bool = False) -> None:
    with open(os.path.join(OUTPUT, "results.json")) as f:
        results = json.load(f)
    with open(os.path.join(BENCH, "reference_set.json")) as f:
        refset = json.load(f)
    with open(os.path.join(HERE, "manuscript.md")) as f:
        template = f.read()
    text = render_manuscript(template, all_values(results, refset, *load_external()))
    problems = bjcp_problems(text)
    if problems:
        raise ValueError("the manuscript breaks the journal's limits: " + "; ".join(problems))
    os.makedirs(os.path.join(BUILD, "figures"), exist_ok=True)
    for src in (OUTPUT, EXT_OUTPUT):
        for name in os.listdir(src):
            if name.endswith(".png"):
                shutil.copy(os.path.join(src, name), os.path.join(BUILD, "figures", name))
    md = os.path.join(BUILD, "manuscript.md")
    with open(md, "w") as f:
        f.write(text)
    html = os.path.join(BUILD, "manuscript.html")
    subprocess.run(["pandoc", md, "-s", "-o", html, "--css", "style.css", "--embed-resources",
                    "--resource-path", BUILD + ":" + HERE, "--metadata", "lang=en", "--mathml"],
                   check=True, cwd=BUILD)
    if pdf:
        _pdf(html, os.path.join(BUILD, "manuscript.pdf"))
    print("wrote", md, html, "and PDF" if pdf else "")


if __name__ == "__main__":
    main(pdf="--pdf" in sys.argv)
