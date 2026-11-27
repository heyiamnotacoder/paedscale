"""Curation step 1 (network): fetch one FDA SPL per candidate from openFDA by the PROTOCOL.md rule.

Usage (from backend/): python3 benchmark/curation/fetch_labels.py vancomycin gentamicin ...
Writes raw label JSON to ./labels_raw/. Snapshots in benchmark/labels/ were trimmed from these
(set_id, effective_time, version, openfda names, and the D&A / pediatric use / clinical
pharmacology / pharmacokinetics sections). Retrieved 2026-11-27.
"""
import json, sys, time, urllib.parse, httpx
import os
os.makedirs("labels_raw", exist_ok=True)
drugs = sys.argv[1:]
for d in drugs:
    q = f'openfda.generic_name:"{d}" AND openfda.route:"INTRAVENOUS"'
    url = "https://api.fda.gov/drug/label.json?search=" + urllib.parse.quote(q) + "&limit=20"
    r = httpx.get(url, timeout=30)
    if r.status_code != 200:
        q = f'openfda.generic_name:"{d}"'
        r = httpx.get("https://api.fda.gov/drug/label.json?search=" + urllib.parse.quote(q) + "&limit=20", timeout=30)
    res = r.json().get("results", [])
    # prefer labels with pediatric dosing text and most recent
    def score(x):
        t = json.dumps(x.get("dosage_and_administration", "")).lower()
        return (("pediatric" in t) + ("neonat" in t), x.get("effective_time", ""))
    res.sort(key=score, reverse=True)
    if not res:
        print(d, "NONE"); continue
    x = res[0]
    keep = {k: x.get(k) for k in ["set_id","id","effective_time","version","openfda","dosage_and_administration","dosage_and_administration_table","pediatric_use","clinical_pharmacology","pharmacokinetics","indications_and_usage"]}
    keep["openfda"] = {k: (x.get("openfda") or {}).get(k) for k in ["generic_name","brand_name","manufacturer_name","route","spl_set_id"]}
    json.dump(keep, open(f"labels_raw/{d.replace(' ','_').replace('/','_')}.json","w"), indent=1)
    print(d, len(res), x.get("effective_time"), (x.get("openfda") or {}).get("manufacturer_name"), score(x)[0])
    time.sleep(0.3)
