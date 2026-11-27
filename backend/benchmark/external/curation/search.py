"""External validation, step 1 (network): snapshot the PubMed searches fixed in PROTOCOL.md.

Usage (from backend/): python3 -m benchmark.external.curation.search restore|authors|snapshot
`restore` re-fetches the committed snapshot's abstracts and checks them against its hashes;
`authors` writes dataset/authors.json for the frozen dataset (E7); `snapshot` re-runs the searches and overwrites the committed snapshot (done once, 2026-11-27).
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
               "penicillin_g": '(benzylpenicillin[tiab] OR "penicillin G"[tiab])',
               "acyclovir": "(acyclovir[tiab] OR aciclovir[tiab])",              # Amendment 2
               "zidovudine": "(zidovudine[tiab] OR azidothymidine[tiab])"}       # Amendment 2
# NCBI asks clients to identify themselves. A generic project address only, never a person's.
NCBI = {"tool": "paedscale", "email": os.environ.get("NCBI_EMAIL", "paedscale@example.com")}
if os.environ.get("NCBI_API_KEY"):
    NCBI["api_key"] = os.environ["NCBI_API_KEY"]
PEDIATRIC = ("(neonat*[tiab] OR infant*[tiab] OR child*[tiab] OR pediatric*[tiab] OR "
             "paediatric*[tiab])")
ADULT = "(healthy[tiab] OR volunteer*[tiab] OR adult*[tiab])"
COMMON = "AND humans[mh] AND english[la] AND hasabstract"


def drugs() -> list[str]:
    with open(REFSET, encoding="utf-8") as f:
        ref = json.load(f)["drugs"]
    return sorted(k for k, d in ref.items() if d.get("included") and k not in CURVE_SOURCE_DRUGS)


def queries(drug: str) -> tuple[str, str]:
    term = SEARCH_TERM.get(drug, f"{drug}[tiab]")
    stem = f"{term} AND clearance[tiab] AND pharmacokinetic*[tiab] AND"
    return f"{stem} {PEDIATRIC} {COMMON}", f"{stem} {ADULT} {COMMON}"


def _request(method: str, url: str, **kw) -> httpx.Response:
    """NCBI request with backoff on 429, 5xx and transport errors (five tries)."""
    for attempt in range(5):
        try:
            r = httpx.request(method, url, timeout=120, **kw)
        except httpx.TransportError:          # connection reset, timeout: retry like a 5xx
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
            continue
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
            return r
        time.sleep(2 ** attempt)
    r.raise_for_status()
    return r


def checked_ids(res: dict) -> list[str]:
    """PMIDs of one esearch result, ascending. Errors, warnings and counts esearch cannot page
    in one call stop the snapshot rather than silently shrinking it."""
    if res.get("errorlist") or res.get("ERROR"):
        raise RuntimeError(f"esearch error: {res.get('errorlist') or res.get('ERROR')}")
    warnings = {k: v for k, v in (res.get("warninglist") or {}).items() if v}
    if warnings:
        raise RuntimeError(f"esearch warning: {warnings}")
    if int(res["count"]) >= 10000:
        raise RuntimeError(f"esearch count {res['count']} reaches the 10000 retrieval limit")
    if len(res["idlist"]) != int(res["count"]):
        raise RuntimeError(f"esearch returned {len(res['idlist'])} of {res['count']} ids")
    return sorted(set(res["idlist"]), key=int)


def _esearch(term: str) -> tuple[list[str], str]:
    r = _request("GET", f"{EUTILS}/esearch.fcgi",
                 params={**NCBI, "db": "pubmed", "term": term, "retmode": "json", "retmax": 9999})
    res = r.json()["esearchresult"]
    return checked_ids(res), res.get("querytranslation", "")


def parse_efetch(xml: bytes) -> dict[str, dict]:
    """Per journal-article PMID: the hashed text and the publication year.

    The text is the title, a blank line, then each English abstract section on its own line as
    "LABEL: text" (or the text alone when unlabelled). Inline markup is flattened. Abstracts in
    other languages (OtherAbstract) and book records are left out."""
    out = {}
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = art.findtext("MedlineCitation/PMID")
        title_el = art.find("MedlineCitation/Article/ArticleTitle")
        title = " ".join("".join(title_el.itertext()).split()) if title_el is not None else ""
        parts = []
        for a in art.findall("MedlineCitation/Article/Abstract/AbstractText"):
            text = " ".join("".join(a.itertext()).split())
            parts.append(f"{a.get('Label')}: {text}" if a.get("Label") else text)
        year = (art.findtext("MedlineCitation/Article/Journal/JournalIssue/PubDate/Year")
                or (art.findtext("MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate") or "")[:4])
        out[pmid] = {"text": (title + "\n\n" + "\n".join(parts)).strip(), "year": year,
                     "has_abstract": any(p.strip() for p in parts)}
    return out


def parse_authors(xml: bytes) -> dict[str, list[str]]:
    """Per PMID, its personal authors as "LastName Initials" (for sensitivity analysis E7)."""
    out = {}
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = art.findtext("MedlineCitation/PMID")
        out[pmid] = [f"{a.findtext('LastName')} {a.findtext('Initials') or ''}".strip()
                     for a in art.findall("MedlineCitation/Article/AuthorList/Author")
                     if a.findtext("LastName")]
    return out


def fetch_authors(pmids: list[str]) -> dict[str, list[str]]:
    out = {}
    for i in range(0, len(pmids), 150):
        r = _request("POST", f"{EUTILS}/efetch.fcgi",
                     data={**NCBI, "db": "pubmed", "id": ",".join(pmids[i:i + 150]), "retmode": "xml"})
        out.update(parse_authors(r.content))
        time.sleep(0.4)
    return out


def require_all(pmids: list[str], recs: dict) -> None:
    missing = [p for p in pmids if p not in recs or not recs[p].get("has_abstract")]
    if missing:
        raise RuntimeError(f"efetch returned no journal abstract for PMIDs: {', '.join(missing)}")


def _abstracts(pmids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(pmids), 150):
        r = _request("POST", f"{EUTILS}/efetch.fcgi",
                     data={**NCBI, "db": "pubmed", "id": ",".join(pmids[i:i + 150]), "retmode": "xml"})
        out.update(parse_efetch(r.content))
        time.sleep(0.4)
    return out


def matching_texts(rows: list[dict], recs: dict) -> dict[str, str]:
    """The abstract text of every snapshot row, re-fetched. A text whose SHA-256 differs from
    the committed one, or a PMID that no longer returns, stops the restore: screening reads
    only the snapshot (PROTOCOL.md, Literature search)."""
    out, bad = {}, []
    for r in rows:
        t = (recs.get(r["pmid"]) or {}).get("text")
        if t is None or hashlib.sha256(t.encode()).hexdigest() != r["sha256"]:
            bad.append(r["pmid"])
        else:
            out[r["pmid"]] = t
    if bad:
        raise RuntimeError(f"re-fetched abstracts differ from the snapshot for PMIDs: {', '.join(bad)}")
    return out


def restore(drug: str) -> int:
    """Re-fetch the abstract texts of a committed snapshot into ABSTRACT_DIR (gitignored),
    checking each against its committed hash. Returns the number of texts written."""
    with open(os.path.join(SEARCH_DIR, f"{drug}.json"), encoding="utf-8") as f:
        snap = json.load(f)
    os.makedirs(os.path.join(ABSTRACT_DIR, drug), exist_ok=True)
    rows = snap["pediatric"] + snap["adult"]
    texts = matching_texts(rows, _abstracts(sorted({r["pmid"] for r in rows}, key=int)))
    for p, t in texts.items():
        with open(os.path.join(ABSTRACT_DIR, drug, f"{p}.txt"), "w", encoding="utf-8") as f:
            f.write(t)
    return len(texts)


def snapshot(drug: str, today: str) -> dict:
    ped_q, adult_q = queries(drug)
    record = {"drug": drug, "retrieved": today, "queries": {"pediatric": ped_q, "adult": adult_q}}
    os.makedirs(os.path.join(ABSTRACT_DIR, drug), exist_ok=True)
    for kind, q in (("pediatric", ped_q), ("adult", adult_q)):
        pmids, translation = _esearch(q)
        recs = _abstracts(pmids)
        require_all(pmids, recs)
        rows = []
        for p in pmids:
            t = recs[p]["text"]
            with open(os.path.join(ABSTRACT_DIR, drug, f"{p}.txt"), "w", encoding="utf-8") as f:
                f.write(t)
            rows.append({"pmid": p, "year": recs[p]["year"], "sha256": hashlib.sha256(t.encode()).hexdigest(),
                         "prefilter": has_clearance_value(t)})
        record[kind] = rows
        record.setdefault("query_translation", {})[kind] = translation
    return record


def main(argv: list[str]) -> None:
    """`restore` re-fetches the committed snapshot's abstracts; `authors` writes dataset/authors.json for the frozen dataset (E7); `snapshot` re-runs the searches
    and overwrites the committed snapshot. Anything else stops, so a typo never re-searches."""
    if argv == ["restore"]:
        for d in drugs():
            print(d, restore(d))
        return
    if argv == ["authors"]:                # E7: authors of the frozen dataset's pediatric studies
        final = os.path.join(EXTERNAL, "extraction", "final")
        pmids = sorted({s["pmid"] for fn in os.listdir(final) if fn.endswith(".json")
                        for s in json.load(open(os.path.join(final, fn), encoding="utf-8"))["pediatric"]
                        if s["decision"] == "include"}, key=int)
        os.makedirs(os.path.join(EXTERNAL, "dataset"), exist_ok=True)
        with open(os.path.join(EXTERNAL, "dataset", "authors.json"), "w", encoding="utf-8") as f:
            json.dump(fetch_authors(pmids), f, indent=1, sort_keys=True)
        return
    if argv != ["snapshot"]:
        raise SystemExit("usage: python3 -m benchmark.external.curation.search restore|authors|snapshot")
    os.makedirs(SEARCH_DIR, exist_ok=True)
    today = dt.date.today().isoformat()
    for d in drugs():
        rec = snapshot(d, today)
        with open(os.path.join(SEARCH_DIR, f"{d}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        print(d, "pediatric", len(rec["pediatric"]), sum(r["prefilter"] for r in rec["pediatric"]),
              "adult", len(rec["adult"]), sum(r["prefilter"] for r in rec["adult"]))


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
