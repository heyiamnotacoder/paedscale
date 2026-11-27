"""Curation step 1 (network): fetch one FDA SPL per candidate from openFDA by the PROTOCOL.md rule.

Rule (Amendment 1 §10): among labels whose openfda.generic_name matches and whose
openfda.route includes INTRAVENOUS, prefer those whose Dosage and Administration text
matches /pediatric|neonat/i; break ties by the latest effective_time. All pages are read.

Usage (from backend/): python3 benchmark/curation/fetch_labels.py vancomycin gentamicin ...
Writes raw label JSON to ./labels_raw/ and prints the selected set_id per drug.
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
    return out


def select(results: list[dict]) -> dict | None:
    def key(x):
        da = " ".join(x.get("dosage_and_administration") or [])
        return (bool(PEDS.search(da)), x.get("effective_time", ""))
    return max(results, key=key) if results else None


if __name__ == "__main__":
    os.makedirs("labels_raw", exist_ok=True)
    for d in sys.argv[1:]:
        res = candidates(d)
        x = select(res)
        if x is None:
            print(d, "NONE")
            continue
        fn = d.replace(" ", "_").replace("/", "_")
        json.dump(x, open(f"labels_raw/{fn}.json", "w"), indent=1)
        print(d, len(res), x.get("set_id"), x.get("effective_time"))
        time.sleep(0.3)
