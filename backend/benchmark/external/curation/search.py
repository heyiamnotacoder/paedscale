"""External validation, step 1 (network): snapshot the PubMed searches fixed in PROTOCOL.md.

Usage (from backend/): python3 -m benchmark.external.curation.search
Writes benchmark/external/search/<drug>.json (committed): the queries, the retrieval date, every
PMID returned (ascending), and per PMID the SHA-256 of the abstract text and whether the
mechanical pre-filter matched. Abstract texts go to benchmark/external/abstracts/ (gitignored,
copyright) so screening can read them offline. Nothing here screens, extracts or predicts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET

import httpx

from benchmark.external.curation.prefilter import has_clearance_value

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HERE = os.path.dirname(os.path.abspath(__file__))
EXTERNAL = os.path.dirname(HERE)
REFSET = os.path.join(os.path.dirname(EXTERNAL), "reference_set.json")
SEARCH_DIR = os.path.join(EXTERNAL, "search")
ABSTRACT_DIR = os.path.join(EXTERNAL, "abstracts")

CURVE_SOURCE_DRUGS = {"morphine"}          # UGT2B7 curve source (Anand 2008)
SEARCH_TERM = {"piperacillin_tazobactam": "piperacillin[tiab]",
               "penicillin_g": '(benzylpenicillin[tiab] OR "penicillin G"[tiab])'}
PEDIATRIC = ("(neonat*[tiab] OR infant*[tiab] OR child*[tiab] OR pediatric*[tiab] OR "
             "paediatric*[tiab])")
ADULT = "(healthy[tiab] OR volunteer*[tiab] OR adult*[tiab])"
COMMON = "AND humans[mh] AND english[la] AND hasabstract"


def drugs() -> list[str]:
    with open(REFSET) as f:
        ref = json.load(f)["drugs"]
    return sorted(k for k, d in ref.items() if d.get("included") and k not in CURVE_SOURCE_DRUGS)


def queries(drug: str) -> tuple[str, str]:
    term = SEARCH_TERM.get(drug, f"{drug}[tiab]")
    stem = f"{term} AND clearance[tiab] AND pharmacokinetic*[tiab] AND"
    return f"{stem} {PEDIATRIC} {COMMON}", f"{stem} {ADULT} {COMMON}"


def _esearch(term: str) -> list[str]:
    ids, start = [], 0
    while True:
        r = httpx.get(f"{EUTILS}/esearch.fcgi", params={"db": "pubmed", "term": term, "retmode": "json",
                                                       "retmax": 500, "retstart": start}, timeout=60)
        r.raise_for_status()
        res = r.json()["esearchresult"]
        ids += res["idlist"]
        start += 500
        if start >= int(res["count"]):
            return sorted(set(ids), key=int)
        time.sleep(0.4)


def _abstracts(pmids: list[str]) -> dict[str, str]:
    """Title + abstract text per PMID, as PubMed returns it in XML."""
    out = {}
    for i in range(0, len(pmids), 150):
        r = httpx.post(f"{EUTILS}/efetch.fcgi", data={"db": "pubmed", "id": ",".join(pmids[i:i + 150]),
                                                      "retmode": "xml"}, timeout=120)
        r.raise_for_status()
        for art in ET.fromstring(r.content).iter("PubmedArticle"):
            pmid = art.findtext(".//MedlineCitation/PMID")
            title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
            parts = []
            for a in art.iter("AbstractText"):
                label = a.get("Label")
                text = "".join(a.itertext()).strip()
                parts.append(f"{label}: {text}" if label else text)
            out[pmid] = (title.strip() + "\n\n" + "\n".join(parts)).strip()
        time.sleep(0.4)
    return out


def snapshot(drug: str, today: str) -> dict:
    ped_q, adult_q = queries(drug)
    record = {"drug": drug, "retrieved": today, "queries": {"pediatric": ped_q, "adult": adult_q}}
    os.makedirs(os.path.join(ABSTRACT_DIR, drug), exist_ok=True)
    for kind, q in (("pediatric", ped_q), ("adult", adult_q)):
        pmids = _esearch(q)
        texts = _abstracts(pmids)
        rows = []
        for p in pmids:
            t = texts.get(p, "")
            with open(os.path.join(ABSTRACT_DIR, drug, f"{p}.txt"), "w") as f:
                f.write(t)
            rows.append({"pmid": p, "sha256": hashlib.sha256(t.encode()).hexdigest(),
                         "prefilter": has_clearance_value(t)})
        record[kind] = rows
    return record


if __name__ == "__main__":
    os.makedirs(SEARCH_DIR, exist_ok=True)
    today = dt.date.today().isoformat()
    for d in drugs():
        rec = snapshot(d, today)
        with open(os.path.join(SEARCH_DIR, f"{d}.json"), "w") as f:
            json.dump(rec, f, indent=1)
        print(d, "pediatric", len(rec["pediatric"]), sum(r["prefilter"] for r in rec["pediatric"]),
              "adult", len(rec["adult"]), sum(r["prefilter"] for r in rec["adult"]))
