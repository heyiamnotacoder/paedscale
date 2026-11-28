"""Run from the repo root: python3 -m pytest -q paper/test_build.py"""
import math

import pytest

from paper import build


def test_every_placeholder_is_filled_and_an_unknown_one_stops_the_build():
    assert build.render("AAFE {{a}} and {{b}}", {"a": "1.2", "b": "x"}) == "AAFE 1.2 and x"
    with pytest.raises(KeyError, match="missing"):
        build.render("{{missing}}", {})


def test_a_log10_difference_and_its_interval_read_as_a_ratio():
    # mean log10 difference log10(0.8); CI from log10(0.5) to 0 -> ratio 0.80 (0.50-1.00)
    h = {"mean_abs_log10_diff": math.log10(0.8), "ci95": [math.log10(0.5), 0.0]}
    assert build.ratio_with_ci(h) == "0.80 (95% CI 0.50–1.00)"


def test_an_interval_that_barely_crosses_one_is_not_rounded_onto_it():
    h = {"mean_abs_log10_diff": math.log10(0.91), "ci95": [math.log10(0.80), 0.00016]}
    assert build.ratio_with_ci(h) == "0.91 (95% CI 0.80–1.0004)"


def test_a_table_cell_gives_the_interval_without_repeating_its_name():
    h = {"mean_abs_log10_diff": math.log10(0.8), "ci95": [math.log10(0.5), 0.0]}
    assert build.ratio_with_ci(h, label=False) == "0.80 (0.50–1.00)"


def test_the_manuscript_fills_from_the_committed_benchmark_outputs():
    """Every placeholder in the manuscript has a value in the committed results."""
    import json
    import os
    with open(os.path.join(build.OUTPUT, "results.json")) as f:
        results = json.load(f)
    with open(os.path.join(build.BENCH, "reference_set.json")) as f:
        refset = json.load(f)
    with open(os.path.join(build.HERE, "manuscript.md")) as f:
        text = build.render_manuscript(f.read(), build.all_values(results, refset, *build.load_external()))
    assert "{{" not in text and "0.77 (95% CI 0.58–0.96)" in text and "0.61 (95% CI 0.50–0.79)" in text


def _committed():
    import json
    import os
    with open(os.path.join(build.OUTPUT, "results.json")) as f:
        results = json.load(f)
    with open(os.path.join(build.BENCH, "reference_set.json")) as f:
        refset = json.load(f)
    return results, refset


def test_fractions_excreted_keep_three_decimals_and_say_when_imputed():
    results, refset = _committed()
    table = build.drug_table(refset)
    assert "| meropenem |" in table and "0.625" in table
    assert "0.900 (qualitative)" in table          # ampicillin: protocol default for a qualitative label


def test_the_method_tables_report_every_prespecified_secondary_endpoint():
    results, refset = _committed()
    head = build.method_table(results, "newborn").splitlines()[0]
    assert "Within labeled range" in head and "Pair-weighted AAFE" in head


def test_a_sensitivity_analysis_without_a_label_stops_the_build():
    import copy
    import pytest
    results, refset = _committed()
    r = copy.deepcopy(results)
    r["sensitivity"]["S11_new"] = r["sensitivity"]["S1_exclude_mgkg_shared"]
    with pytest.raises(KeyError, match="S11_new"):
        build.sensitivity_table(r, _ext())


def _ext():
    import json
    import os
    with open(os.path.join(build.EXT_OUTPUT, "results.json")) as f:
        return json.load(f)


def test_the_external_flow_counts_come_from_the_snapshot_and_the_final_record():
    flow = build.external_flow(build.EXT)
    assert flow["drugs"] == 20
    assert flow["ped_screened"] <= flow["ped_prefilter"] <= flow["ped_hits"]
    assert flow["ped_included"] == 69 and flow["adult_included"] == 34
    assert sum(flow["ped_reasons"].values()) == flow["ped_screened"] - flow["ped_included"]


def test_the_hypothesis_table_holds_both_studies():
    results, _ = _committed()
    table = build.hypothesis_table(results, _ext())
    assert table.count("\n") == 6                       # header, rule, H1–H3, HE1–HE2
    assert "| HE1 |" in table and "Children under 2 years" in table


def test_the_external_method_table_lists_four_methods_for_two_populations():
    table = build.external_method_table(_ext())
    assert table.count("\n") == 5 and "| PaedScale |" in table and "Allometry" in table


def test_the_sensitivity_table_has_a_row_for_every_analysis_of_both_studies():
    results, _ = _committed()
    table = build.sensitivity_table(results, _ext())
    for k in ("E1", "E6", "E9", "S1", "S10"):
        assert f"| {k} " in table


def test_the_word_count_skips_tables_figures_and_captions():
    md = "# Abstract\nx y\n# Introduction\none two\n| a | b |\n![cap](f.png)\nTable: **T1.** c\n# Declarations\nz"
    assert build.word_count(md) == 4          # "#", "Introduction", "one", "two"


def test_the_clearance_validation_read_every_prefiltered_pediatric_abstract():
    flow = build.external_flow(build.EXT)
    assert flow["ped_screened"] == flow["ped_prefilter"]     # the manuscript says no list stopped early
