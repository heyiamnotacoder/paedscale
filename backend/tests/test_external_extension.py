"""The extension set of the external validation (benchmark/external/PROTOCOL.md, Amendment 19)."""
from benchmark.external.curation import trees


def test_extension_drugs_live_in_their_own_tree_and_primary_drugs_stay_put():
    assert trees.tree_of("cefazolin") == trees.EXTENSION
    assert trees.tree_of("vancomycin") == trees.PRIMARY
    assert trees.EXTENSION.search.endswith("external/extension/search")
    assert trees.PRIMARY.search.endswith("external/search")


def _label_text(entry: dict) -> str:
    import json, os
    path = os.path.join(os.path.dirname(trees.EXTERNAL), entry["label"])
    return " ".join(json.load(open(path, encoding="utf-8"))["sections"].values())


def test_the_twelve_candidates_of_amendment_19_are_all_accounted_for():
    inputs = trees.EXTENSION.engine_inputs()
    assert sorted(inputs) == sorted(["cefazolin", "digoxin", "fentanyl", "alfentanil", "sufentanil",
                                     "ganciclovir", "cefotaxime", "levofloxacin", "milrinone",
                                     "ceftriaxone", "linezolid", "metronidazole"])
    excluded = {k: d["excluded_by"] for k, d in inputs.items() if not d["included"]}
    assert excluded == {"alfentanil": "label", "linezolid": "E4"}
    assert all(d["reason"] for d in inputs.values() if not d["included"])


def test_every_engine_input_quote_is_verbatim_in_its_label_snapshot():
    for name, d in trees.EXTENSION.engine_inputs().items():
        if d.get("label") is None:
            continue
        text = _label_text(d)
        quotes = [d["quote"]] if not d["included"] else [d["fe"]["quote"], d["fe"].get("quote_2")]
        for q in filter(None, quotes):
            assert q in text, (name, q)


def test_fe_and_enzyme_map_onto_the_engine_curves():
    from benchmark.methods import pathway_fractions
    inputs = trees.EXTENSION.engine_inputs()
    assert pathway_fractions(inputs["fentanyl"]) == {"renal_gfr": 0.05, "cyp3a4": 0.95}
    assert pathway_fractions(inputs["ceftriaxone"]) == {"renal_gfr": 0.5}     # biliary: unattributed
    for d in inputs.values():
        if d["included"]:
            assert 0 <= d["fe"]["value"] <= 1 and d["nonrenal_enzyme"] in (None, "cyp3a4", "ugt2b7")
            assert d["nonrenal_enzyme"] is None or d["enzyme_evidence"]


def test_no_extension_drug_is_a_primary_drug_or_a_curve_source():
    from benchmark.external.curation import search
    assert not set(trees.extension_drugs()) & set(search.drugs())
    assert not set(trees.extension_drugs()) & {"morphine", "midazolam"}


def test_cefazolin_is_also_searched_by_its_older_spelling():
    from benchmark.external.curation import search
    assert search.queries("cefazolin")[0].startswith("(cefazolin[tiab] OR cephazolin[tiab]) AND")


def _tmp_extension(monkeypatch, tmp_path):
    from dataclasses import replace
    ext = replace(trees.EXTENSION, search=str(tmp_path / "search"), abstracts=str(tmp_path / "abstracts"),
                  extraction=str(tmp_path / "extraction"), dataset=str(tmp_path / "dataset"),
                  output=str(tmp_path / "output"))
    monkeypatch.setattr(trees, "EXTENSION", ext)
    return ext


def test_the_extension_snapshot_writes_only_extension_drugs_and_never_overwrites(monkeypatch, tmp_path):
    import os
    import pytest
    from benchmark.external.curation import search
    ext = _tmp_extension(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(search, "snapshot", lambda d, today: calls.append(d) or {"drug": d, "pediatric": [], "adult": []})
    search.main(["snapshot", "extension"])
    assert calls == trees.extension_drugs()
    assert sorted(os.listdir(ext.search)) == [f"{d}.json" for d in calls]
    with pytest.raises(SystemExit):
        search.main(["snapshot", "extension"])
    assert len(calls) == len(trees.extension_drugs())


def test_restore_extension_restores_only_the_extension_drugs(monkeypatch):
    from benchmark.external.curation import search
    calls = []
    monkeypatch.setattr(search, "restore", lambda d: calls.append(d) or 0)
    search.main(["restore", "extension"])
    assert calls == trees.extension_drugs()


def _write_extension_drug(ext, drug="cefazolin"):
    """A one-abstract extension snapshot, as search.snapshot writes it."""
    import hashlib, json, os
    text = "Cefazolin in neonates\n\nIn 12 neonates (postnatal age 5 days) clearance was 0.1 L/h/kg."
    os.makedirs(os.path.join(ext.abstracts, drug))
    open(os.path.join(ext.abstracts, drug, "11.txt"), "w").write(text)
    os.makedirs(ext.search)
    row = {"pmid": "11", "year": "2001", "sha256": hashlib.sha256(text.encode()).hexdigest(), "prefilter": True}
    json.dump({"drug": drug, "pediatric": [row], "adult": []}, open(os.path.join(ext.search, f"{drug}.json"), "w"))
    return text


def test_check_reads_an_extension_drug_from_the_extension_tree(monkeypatch, tmp_path):
    import json, os
    from benchmark.external.curation import check
    ext = _tmp_extension(monkeypatch, tmp_path)
    _write_extension_drug(ext)
    assert any(ext.extraction in p for p in check.check_drug("pass1", "cefazolin"))   # no record yet
    os.makedirs(os.path.join(ext.extraction, "pass1"))
    rec = {"drug": "cefazolin", "pass": "pass1", "adult": [],
           "pediatric": [{"pmid": "11", "decision": "exclude", "reason": "P1: oral", "flags": [], "observations": []}]}
    json.dump(rec, open(os.path.join(ext.extraction, "pass1", "cefazolin.json"), "w"))
    assert check.check_drug("pass1", "cefazolin") == []


def test_the_screening_queue_prints_extension_abstracts(monkeypatch, tmp_path, capsys):
    import sys
    from benchmark.external.curation import screening
    ext = _tmp_extension(monkeypatch, tmp_path)
    text = _write_extension_drug(ext)
    monkeypatch.setattr(sys, "argv", ["screening", "next", "pass1", "cefazolin", "3"])
    screening._cli()
    assert text in capsys.readouterr().out


def _write_passes(ext, decisions=("exclude", "exclude")):
    import json, os
    for p, dec in zip(("pass1", "pass2"), decisions):
        os.makedirs(os.path.join(ext.extraction, p), exist_ok=True)
        study = {"pmid": "11", "decision": dec, "reason": "P1: oral" if dec == "exclude" else "",
                 "flags": [], "observations": []}
        json.dump({"drug": "cefazolin", "pass": p, "pediatric": [study], "adult": []},
                  open(os.path.join(ext.extraction, p, "cefazolin.json"), "w"))


def test_adjudication_of_the_extension_writes_only_the_extension_final_record(monkeypatch, tmp_path):
    import os
    from benchmark.external.curation import adjudicate
    ext = _tmp_extension(monkeypatch, tmp_path)
    _write_extension_drug(ext)
    _write_passes(ext)
    primary_before = sorted(os.listdir(trees.PRIMARY.final))
    assert adjudicate.main("extension") == 0
    assert os.listdir(ext.final) == ["cefazolin.json"]
    assert sorted(os.listdir(trees.PRIMARY.final)) == primary_before


def test_agreement_of_the_extension_passes_reads_the_extension_tree(monkeypatch, tmp_path):
    from benchmark.external.curation import agreement
    ext = _tmp_extension(monkeypatch, tmp_path)
    _write_extension_drug(ext)
    _write_passes(ext, ("exclude", "include"))
    res = agreement.main("pass1", "pass2", tree=trees.EXTENSION)
    assert res["both_read"] == 1 and res["n_decision_disagreements"] == 1


def test_the_scorer_reads_the_primary_dataset_with_the_label_benchmark_inputs():
    from benchmark.external import score
    ds = score.load_dataset(trees.PRIMARY)
    assert len(ds) == 20 and "vancomycin" in ds and "cefazolin" not in ds
    assert ds["vancomycin"]["drug"]["fe"]["value"] == 0.75


def _freeze_extension(ext):
    """A frozen one-drug extension dataset: the final record and its author list."""
    import json, os, shutil
    os.makedirs(ext.final)
    shutil.copy(os.path.join(ext.extraction, "pass1", "cefazolin.json"), os.path.join(ext.final, "cefazolin.json"))
    os.makedirs(ext.dataset)
    json.dump({"11": ["Smith J"]}, open(ext.authors, "w"))


def test_the_extension_is_scored_with_its_own_inputs_and_pooled_with_the_primary(monkeypatch, tmp_path):
    from benchmark.external import score
    ext = _tmp_extension(monkeypatch, tmp_path)
    _write_extension_drug(ext)
    _write_passes(ext)
    _freeze_extension(ext)
    ds = score.load_dataset(trees.EXTENSION)
    assert list(ds) == ["cefazolin"] and ds["cefazolin"]["drug"]["fe"]["value"] == 0.75
    pooled = score.datasets("pooled")
    assert len(pooled) == 21 and pooled["cefazolin"] == ds["cefazolin"]
    assert score.output_dir("extension") == ext.output
    assert score.output_dir("pooled").endswith("external/output/pooled")
