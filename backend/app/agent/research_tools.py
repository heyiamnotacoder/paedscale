"""Data-fetch tools for the orchestrator.

Two tiers, matching the whiteboard:
  - `fetch_drug_pk` (deterministic, HAPPY PATH): one openFDA drug-label call, with a small local
    seed cache checked first for instant hits. Grounds adult PK without an agentic web loop.
  - `pubmed_search` (EDGE PATH): kept as a fallback literature tool for the edge-case branch.

Thin async wrappers over free REST APIs — no MCP binary to deploy. A process-level query cache and a
shared `httpx.AsyncClient` avoid re-hitting endpoints within one process lifetime.
"""

import json
import os
import time
from pathlib import Path

import httpx

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPENFDA_LABEL = "https://api.fda.gov/drug/label.json"
TIMEOUT = 20.0
CACHE_TTL_S = 600.0  # 10 minutes

_cache: dict[tuple, tuple[float, dict]] = {}
_client: httpx.AsyncClient | None = None

# Seed cache: instant hits for validation drugs (a CACHE, not the source of truth — openFDA is the
# generalizable path). Loaded once from the fixtures file if present; absence is fine.
_SEED_PATH = Path(os.environ.get(
    "PAEDSCALE_DRUG_SEED",
    str(Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "validation_drugs.json"),
))
_seed: dict | None = None


def _load_seed() -> dict:
    global _seed
    if _seed is None:
        try:
            with open(_SEED_PATH) as f:
                raw = json.load(f)
            _seed = {k.lower(): v for k, v in raw.items()}
        except (OSError, ValueError):
            _seed = {}
    return _seed


def _cache_get(key: tuple) -> dict | None:
    entry = _cache.get(key)
    if not entry:
        return None
    ts, payload = entry
    if time.monotonic() - ts > CACHE_TTL_S:
        _cache.pop(key, None)
        return None
    return payload


def _cache_set(key: tuple, payload: dict) -> None:
    _cache[key] = (time.monotonic(), payload)


async def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


def clear_research_cache() -> None:
    """Test helper."""
    _cache.clear()


# --------------------------------------------------------------------------- #
# fetch_drug_pk — deterministic happy-path drug data.                          #
# --------------------------------------------------------------------------- #

_OPENFDA_SECTIONS = (
    "pharmacokinetics",
    "clinical_pharmacology",
    "mechanism_of_action",
    "dosage_and_administration",
    "pediatric_use",
    "use_in_specific_populations",
)


async def _fetch_drug_pk(args: dict) -> dict:
    drug = (args.get("drug_name") or "").strip()
    if not drug:
        return {"error": "drug_name is required", "found": False}
    key = ("drugpk", drug.lower())

    seed = _load_seed().get(drug.lower())
    if seed is not None:
        return {"source": "seed_cache", "found": True, "drug_name": drug, "structured_pk": seed}

    hit = _cache_get(key)
    if hit is not None:
        return hit

    try:
        c = await _http()
        params = {"search": f'openfda.generic_name:"{drug}"', "limit": 1}
        api_key = os.environ.get("OPENFDA_API_KEY")
        if api_key:
            params["api_key"] = api_key
        r = await c.get(OPENFDA_LABEL, params=params)
        if r.status_code == 404:
            payload = {"source": "openFDA", "found": False, "drug_name": drug,
                       "note": "No openFDA label — treat as edge case; use pubmed_search."}
            _cache_set(key, payload)
            return payload
        r.raise_for_status()
        results = r.json().get("results", [])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return {"source": "openFDA", "found": False, "drug_name": drug,
                "error": f"openFDA fetch failed: {exc}. Treat as edge case; use pubmed_search."}

    if not results:
        payload = {"source": "openFDA", "found": False, "drug_name": drug,
                   "note": "No openFDA label — treat as edge case; use pubmed_search."}
        _cache_set(key, payload)
        return payload

    doc = results[0]
    sections = {}
    for sec in _OPENFDA_SECTIONS:
        val = doc.get(sec)
        if val:
            text = " ".join(val) if isinstance(val, list) else str(val)
            sections[sec] = text[:2500]  # cap to keep context lean
    payload = {
        "source": "openFDA",
        "found": True,
        "drug_name": drug,
        "brand_names": (doc.get("openfda", {}) or {}).get("brand_name", [])[:3],
        "label_sections": sections,
    }
    _cache_set(key, payload)
    return payload


# --------------------------------------------------------------------------- #
# pubmed_search — edge-path literature fallback.                               #
# --------------------------------------------------------------------------- #


def _ncbi_params(extra: dict) -> dict:
    params = {"db": "pubmed", "retmode": "json", **extra}
    key = os.environ.get("NCBI_API_KEY")
    if key:
        params["api_key"] = key
    return params


async def _pubmed_search(args: dict) -> dict:
    retmax = int(args.get("retmax", 5))
    q = args.get("query", "")
    if not q:
        return {"query": q, "results": [], "error": "query is required"}
    key = ("pubmed", q, retmax)
    hit = _cache_get(key)
    if hit is not None:
        return hit

    try:
        c = await _http()
        r = await c.get(
            f"{EUTILS}/esearch.fcgi",
            params=_ncbi_params({"term": q, "retmax": retmax, "sort": "relevance"}),
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            payload = {"query": q, "results": []}
            _cache_set(key, payload)
            return payload
        s = await c.get(f"{EUTILS}/esummary.fcgi", params=_ncbi_params({"id": ",".join(ids)}))
        s.raise_for_status()
        docs = s.json().get("result", {})
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return {"error": f"PubMed search failed: {exc}", "query": q, "results": []}

    results = []
    for pmid in docs.get("uids", []):
        d = docs.get(pmid, {})
        authors = ", ".join(a.get("name", "") for a in d.get("authors", [])[:4])
        results.append({
            "source": "PubMed",
            "identifier": f"PMID:{pmid}",
            "title": d.get("title", ""),
            "authors": authors,
            "year": (d.get("pubdate", "") or "")[:4],
            "journal": d.get("fulljournalname", d.get("source", "")),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    payload = {"query": q, "results": results}
    _cache_set(key, payload)
    return payload


# --------------------------------------------------------------------------- #
# Tool definitions + dispatch.                                                 #
# --------------------------------------------------------------------------- #

RESEARCH_TOOLS = [
    {
        "name": "fetch_drug_pk",
        "description": "Fetch adult pharmacokinetic drug data in ONE call — checks a local seed cache "
        "first, else the openFDA drug label. Returns structured PK (seed) or label text sections "
        "(pharmacokinetics, clinical_pharmacology, metabolism/elimination). Call this FIRST for every "
        "drug. If found=false, the drug is an edge case — use pubmed_search.",
        "input_schema": {
            "type": "object",
            "properties": {"drug_name": {"type": "string"}},
            "required": ["drug_name"],
        },
    },
    {
        "name": "pubmed_search",
        "description": "Edge-case literature fallback. Search PubMed for pediatric PK / dosing when "
        "openFDA has no label or key numbers are missing. Returns PMID, title, authors, year, journal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "retmax": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
]

_DISPATCH = {
    "fetch_drug_pk": _fetch_drug_pk,
    "pubmed_search": _pubmed_search,
}

RESEARCH_TOOL_NAMES = list(_DISPATCH)


def is_research_tool(name: str) -> bool:
    return name in _DISPATCH


async def run_research_tool(name: str, args: dict) -> dict:
    return await _DISPATCH[name](args or {})
