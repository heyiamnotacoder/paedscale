"""Build the PaedScale manuscript from the committed benchmark outputs.

Every number in the manuscript comes from backend/benchmark/output/results.json and
backend/benchmark/reference_set.json through a {{placeholder}}; none is typed by hand.

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


def _fe(x: float, ci: list | None) -> str:
    return f"{x:.2f} ({ci[0]:.2f}–{ci[1]:.2f})" if ci else f"{x:.2f}"


def _pct(x: float, ci: list | None) -> str:
    return f"{100 * x:.0f}% ({100 * ci[0]:.0f}–{100 * ci[1]:.0f})" if ci else f"{100 * x:.0f}%"


def _p(p: float | None) -> str:
    return "—" if p is None else (f"{p:.3f}" if p >= 0.001 else "<0.001")


def method_table(results: dict, population: str) -> str:
    rows = ["| Method | AAFE (95% CI) | AFE (95% CI) | Within 0.67–1.5× | Within 0.5–2× |",
            "|---|---|---|---|---|"]
    for m in METHOD_ORDER:
        s = results["by_method"][population][m]
        rows.append(f"| {METHOD_LABEL[m]} | {_fe(s['aafe'], s.get('aafe_ci95'))} | "
                    f"{_fe(s['afe'], s.get('afe_ci95'))} | {_pct(s['within_1_5'], s.get('within_1_5_ci95'))} | "
                    f"{_pct(s['within_2'], s.get('within_2_ci95'))} |")
    return "\n".join(rows)


def hypothesis_table(results: dict) -> str:
    rows = ["| Hypothesis | Population | Drugs | Pairs | Ratio of typical fold error (95% CI) | Tied pairs | Wilcoxon p (drug level) | Supported |",
            "|---|---|---|---|---|---|---|---|"]
    for k in ("H1", "H2", "H3"):
        h = results["hypotheses"][k]
        rows.append(f"| {k} | {h['population']} | {h['n_clusters']} | {h['n_pairs']} | {ratio_with_ci(h, label=False)} | "
                    f"{h['n_tied_pairs']} | {_p(h.get('wilcoxon_p_drug_level'))} | "
                    f"{'Yes' if h['significant'] else 'No'} |")
    return "\n".join(rows)


def secondary_table(results: dict) -> str:
    rows = ["| Comparator | Ratio of typical fold error, PaedScale ÷ comparator (95% CI) | Wilcoxon p | Holm-adjusted p |",
            "|---|---|---|---|"]
    for m in ("weight_linear", "bsa", "allometry"):
        s = results["secondary"][m]
        rows.append(f"| {METHOD_LABEL[m]} | {ratio_with_ci(s, label=False)} | {_p(s.get('wilcoxon_p_drug_level'))} | "
                    f"{_p(s.get('wilcoxon_p_holm'))} |")
    return "\n".join(rows)


def sensitivity_table(results: dict) -> str:
    rows = ["| Analysis | Newborns: drugs, ratio (95% CI) | All ages: drugs, ratio (95% CI) |",
            "|---|---|---|"]
    sens = results["sensitivity"]
    for k, label in SENSITIVITY_LABEL.items():
        if k not in sens:
            continue
        cells = []
        for pop in ("newborn", "all"):
            h = sens[k].get(pop) or {}
            cells.append(f"{h['n_clusters']}, {ratio_with_ci(h, label=False)}" if h.get("n_pairs") else "not estimable")
        rows.append(f"| {label} | {cells[0]} | {cells[1]} |")
    s6 = sens.get("S6_leave_one_drug_out", {})
    if s6:
        rng = {p: f"{_ratio(10 ** s6[p]['min'])} to {_ratio(10 ** s6[p]['max'])}" for p in ("newborn", "all")}
        rows.append(f"| S6 Leave one drug out (range of point estimates) | {rng['newborn']} | {rng['all']} |")
    return "\n".join(rows)


def drug_table(refset: dict) -> str:
    rows = ["| Drug | Class | Target metric | fe (urine, unchanged) | Non-renal enzyme | Bands |",
            "|---|---|---|---|---|---|"]
    for name, d in sorted(refset["drugs"].items()):
        if not d.get("included"):
            continue
        fe = d.get("fe") or {}
        fev = fe.get("value")
        rows.append(f"| {name.replace('_', ' ')} | {d.get('class', '')} | {d['target_metric']} | "
                    f"{'—' if fev is None else f'{fev:.2f}'} | {d.get('nonrenal_enzyme') or '—'} | "
                    f"{len(d.get('bands') or [])} |")
    return "\n".join(rows)


def exclusion_table(results: dict) -> str:
    rows = ["| Drug | Criterion | Reason |", "|---|---|---|"]
    for name, e in sorted(results["excluded"].items()):
        rows.append(f"| {name} | {e['criterion']} | {e['reason']} |")
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


def values(results: dict, refset: dict) -> dict:
    hyp, bm, cov, prov = results["hypotheses"], results["by_method"], results["uncertainty_coverage"], results["provenance"]
    v = {
        "n_candidates": sum(1 for _ in refset["drugs"]),
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
        "table_hypotheses": hypothesis_table(results), "table_secondary": secondary_table(results),
        "table_sensitivity": sensitivity_table(results), "table_strata": stratum_table(results),
    }
    for pop in ("newborn", "under2", "all"):
        v[f"table_methods_{pop}"] = method_table(results, pop)
        for m in METHOD_ORDER:
            s = bm[pop][m]
            v[f"{pop}_{m}_aafe"] = _fe(s["aafe"], s.get("aafe_ci95"))
            v[f"{pop}_{m}_afe"] = _fe(s["afe"], s.get("afe_ci95"))
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
    s6 = results["sensitivity"]["S6_leave_one_drug_out"]
    for pop in ("newborn", "all"):
        v[f"s6_{pop}"] = f"{_ratio(10 ** s6[pop]['min'])} to {_ratio(10 ** s6[pop]['max'])}"
    return v


def _pdf(html_path: str, pdf_path: str) -> None:
    subprocess.run(["node", os.path.join(HERE, "pdf.js"), html_path, pdf_path], check=True)


def main(pdf: bool = False) -> None:
    with open(os.path.join(OUTPUT, "results.json")) as f:
        results = json.load(f)
    with open(os.path.join(BENCH, "reference_set.json")) as f:
        refset = json.load(f)
    with open(os.path.join(HERE, "manuscript.md")) as f:
        text = render(f.read(), values(results, refset))
    os.makedirs(os.path.join(BUILD, "figures"), exist_ok=True)
    for name in os.listdir(OUTPUT):
        if name.endswith(".png"):
            shutil.copy(os.path.join(OUTPUT, name), os.path.join(BUILD, "figures", name))
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
