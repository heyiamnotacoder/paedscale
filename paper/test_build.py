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


def test_exclusion_reasons_are_grouped_by_what_failed():
    g = build._reason_group
    assert g("CL/F: oral apparent clearance only") == g("P1: intramuscular administration")
    assert g("P1: pregnant women, not patients under 18") != g("CL/F: oral")
    assert g("not total IV CL: per 70 kg without age") != g("range only: CL 0.1-0.3")
    assert g("P4/P2: single child with stated renal impairment") == g("P4: ECMO")
    assert g("no age: GA only") != g("P2: no numeric clearance")


def test_lists_end_with_and():
    assert build._and(["a", "b", "c"]) == "a, b and c"
    assert build._and(["a"]) == "a" and build._and([]) == "none"


def test_the_bjcp_limits_are_checked_on_the_rendered_manuscript():
    import os
    results, refset = _committed()
    with open(os.path.join(build.HERE, "manuscript.md")) as f:
        text = build.render_manuscript(f.read(), build.all_values(results, refset, *build.load_external()))
    assert build.bjcp_problems(text) == []
    assert build.bjcp_problems(text.replace("**Aim.**", "**Aims.**"))         # a missing heading is caught


def test_outputs_from_a_dirty_tree_stop_the_build():
    with pytest.raises(ValueError, match="dirty"):
        build.check_provenance({"working_tree_dirty": True, "engine_commit": "x"})


def test_the_clearance_strata_use_the_clearance_protocol_ages():
    assert "12–17" in build.external_stratum_table(_ext())


def test_table_s1_uses_words_not_code_names():
    results, refset = _committed()
    t = build.drug_table(refset)
    assert "css" not in t and "cyp3a4" not in t and "Average concentration" in t


def test_a_recorded_value_without_a_display_name_is_shown_as_recorded():
    refset = {"drugs": {"x": {"included": True, "class": "other", "target_metric": "auc",
                              "fe": {"value": 0.5}, "nonrenal_enzyme": "cyp2d6", "bands": []}}}
    t = build.drug_table(refset)
    assert "| cyp2d6 |" in t and "auc" in t.lower()


def test_a_drug_with_no_non_renal_enzyme_shows_a_dash():
    refset = {"drugs": {"x": {"included": True, "class": "other", "target_metric": "css",
                              "fe": {"value": 0.9}, "bands": []}}}
    assert "| — |" in build.drug_table(refset)


def test_label_criteria_are_renamed_l_without_touching_other_letters():
    t = build.exclusion_table({"excluded": {"x": {"criterion": "E2 and E1", "reason": "Every E1 dose"}}})
    assert "| L2 and L1 | Every E1 dose |" in t


def test_a_hypothesis_verdict_is_read_from_the_results():
    he = {"confirmatory": True, "success": False, "tested": None}
    assert build._status(he) == "confirmatory" and build._status({}) == "descriptive"
    assert build._verdict(he) == "did not succeed" and build._verdict({"success": True}) == "succeeded"


def test_he2_is_reported_as_untested_when_he1_failed():
    assert "not tested" in build._he2_sentence({"tested": False, "success": None}, "0.9")
    assert "also succeeded" in build._he2_sentence({"tested": True, "success": True}, "0.7")
    assert "did not succeed" in build._he2_sentence({"tested": True, "success": False}, "0.9")


def test_a_reason_outside_every_group_stops_the_build():
    with pytest.raises(ValueError, match="no group"):
        build._reason_group("Q9: something new")
    assert build._reason_group("P1/P2: review") == build._reason_group("P1: review")


def test_outputs_made_with_different_software_versions_stop_the_build():
    results, refset = _committed()
    ext, agreement, flow = build.load_external()
    ext = {**ext, "provenance": {**ext["provenance"], "versions": {"python": "0"}}}
    with pytest.raises(ValueError, match="software versions"):
        build.all_values(results, refset, ext, agreement, flow)


def test_a_missing_title_is_a_problem_not_a_crash():
    assert "title" in " ".join(build.bjcp_problems("---\n---\n# Abstract\n# Introduction\n# Declarations\n"
                                                    "# Supporting information\n"))


def test_supporting_figures_take_the_right_plural():
    assert build._n_of(1, "figure") == "1 figure" and build._n_of(2, "figure") == "2 figures"


def test_the_external_method_table_reports_the_share_within_1_5_fold():
    assert "0.67–1.5" in build.external_method_table(_ext()).splitlines()[0]


def test_drugs_take_their_international_nonproprietary_names():
    assert build.drug_name("acyclovir") == "aciclovir" and build.drug_name("penicillin_g") == "benzylpenicillin"


def test_an_afe_interval_that_barely_crosses_one_is_not_rounded_onto_it():
    assert build._fold(0.83, [0.643, 1.0019]) == "0.83 (0.64–1.0019)"
