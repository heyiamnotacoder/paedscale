"""Curation step 1 (network): fetch one FDA SPL per candidate from openFDA by the PROTOCOL.md rule.

Rule (Amendment 1 §10): among labels whose openfda.generic_name matches and whose
openfda.route includes INTRAVENOUS, prefer those whose Dosage and Administration text
matches /pediatric|neonat/i; break ties by the latest effective_time, then (Amendment 3) the
highest SPL version, then the highest set_id. All pages are read.

Usage (from backend/): python3 benchmark/curation/fetch_labels.py vancomycin gentamicin ...
Writes raw label JSON to ./labels_raw/ and prints the selected set_id per drug. With
--write-snapshots it also overwrites benchmark/labels/<drug>.json (an amendment-level change).
Snapshots in benchmark/labels/ keep set_id, effective_time, version, openfda names and the
D&A / pediatric use / clinical pharmacology / pharmacokinetics sections. Retrieved 2026-11-27.
"""
import json
import os
import re
import sys
import time
import urllib.parse

import httpx

API = "https://api.fda.gov/drug/label.json"
PEDS = re.compile(r"pediatric|neonat", re.I)


DILUENT_WORDS = {"dextrose", "water", "sodium", "chloride"}
# Dosage-form, package and strength words. Listed in PROTOCOL.md Amendment 3 §1.
QUALIFIERS = {"usp", "nf", "sterile", "injection", "injectable", "for", "solution", "powder", "premix",
              "in", "plastic", "container", "single", "dose", "vial", "bulk", "package", "pharmacy",
              "units", "unit", "iu", "mg", "g", "mcg", "ml", "meq", "per"}


def _words(component: str) -> set[str]:
    return set(re.findall(r"[a-z]+", component.lower()))   # numbers and punctuation ignored


def _is_qualifier(component: str) -> bool:
    return _words(component) <= QUALIFIERS


def _is_diluent(component: str) -> bool:
    """A premix diluent, possibly with a strength: "IN 0.9% SODIUM CHLORIDE", "5% DEXTROSE"."""
    w = _words(component)
    named = "dextrose" in w or "water" in w or {"sodium", "chloride"} <= w
    return named and w <= DILUENT_WORDS | QUALIFIERS


def same_active_ingredient(generic: str, label: dict) -> bool:
    """Amendment 3: the label's active ingredients are exactly the candidate's (salts allowed;
    premix diluents such as dextrose are not active ingredients). Drops combination products
    that the openFDA phrase query also matches, e.g. ampicillin AND sulbactam for ampicillin.
    Components split on the word "and" and on commas; a component made only of dosage-form,
    package or strength words or numbers ("INJECTION", "USP", "1,000 UNITS") is dropped. Each wanted ingredient must match a different
    component as whole words."""
    wanted = [w.strip().lower() for w in re.split(r"\band\b", generic, flags=re.I)]
    for name in label.get("openfda", {}).get("generic_name") or []:
        parts = [p.strip() for p in re.split(r"\band\b|,", name, flags=re.I) if p.strip()]
        actives = [p for p in parts if not _is_diluent(p) and not _is_qualifier(p)]
        if len(actives) != len(wanted):
            continue
        free = list(actives)
        for w in wanted:
            hit = next((a for a in free if re.search(rf"\b{re.escape(w)}\b", a, re.I)), None)
            if hit is None:
                break
            free.remove(hit)
        else:
            return True
    return False


def candidates(generic: str) -> list[dict]:
    q = f'openfda.generic_name:"{generic}" AND openfda.route:"INTRAVENOUS"'
    out, skip = [], 0
    while True:
        r = httpx.get(f"{API}?search={urllib.parse.quote(q)}&limit=100&skip={skip}", timeout=30)
        if r.status_code == 404:          # openFDA: no (more) matches
            break
        r.raise_for_status()
        page = r.json()
        out += page.get("results", [])
        total = page["meta"]["results"]["total"]
        skip += 100
        if skip >= total:
            break
        time.sleep(0.3)
    return [x for x in out if same_active_ingredient(generic, x)]


def select(results: list[dict]) -> dict | None:
    def key(x):
        da = " ".join(x.get("dosage_and_administration") or [])
        # Amendment 3: openFDA result order is not guaranteed, so ties on effective_time go to
        # the most-revised SPL (highest version), then the highest set_id.
        return (bool(PEDS.search(da)), x.get("effective_time", ""), int(x.get("version") or 0),
                x.get("set_id", ""))
    return max(results, key=key) if results else None


SECTIONS = ("dosage_and_administration", "pediatric_use", "clinical_pharmacology", "pharmacokinetics")


def snapshot(x: dict) -> dict:
    """The committed form of a selected label (benchmark/labels/<drug>.json)."""
    return {"source": "openFDA /drug/label.json (FDA SPL); retrieved 2026-11-27",
            "set_id": x.get("set_id"), "effective_time": x.get("effective_time"), "version": x.get("version"),
            "generic_name": x.get("openfda", {}).get("generic_name"),
            "manufacturer_name": x.get("openfda", {}).get("manufacturer_name"),
            "sections": {s: " ".join(x[s]) for s in SECTIONS if x.get(s)}}


if __name__ == "__main__":
    os.makedirs("labels_raw", exist_ok=True)
    LABELS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "labels")
    write_snapshots = "--write-snapshots" in sys.argv
    for d in [a for a in sys.argv[1:] if not a.startswith("--")]:
        res = candidates(d)
        x = select(res)
        if x is None:
            print(d, "NONE")
            continue
        fn = d.replace(" ", "_").replace("/", "_")
        with open(f"labels_raw/{fn}.json", "w") as f:
            json.dump(x, f, indent=1)
        if write_snapshots:   # replacing a committed snapshot is a protocol amendment
            with open(os.path.join(LABELS, f"{fn}.json"), "w") as f:
                json.dump(snapshot(x), f, indent=1, ensure_ascii=False)
        print(d, len(res), x.get("set_id"), x.get("version"), x.get("effective_time"))
        time.sleep(0.3)
