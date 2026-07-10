"""Literature-search tools, exposed as an in-process MCP server.

Grounds the research subagents' claims in real citations. Thin async wrappers
over free REST APIs — no third-party MCP binary to deploy:

  - PubMed via NCBI E-utilities (esearch + esummary). Optional NCBI_API_KEY
    raises the rate limit.
  - Semantic Scholar Graph API (paper search).

Web search is added separately as the Anthropic server-side `web_search` tool.
Every result carries what a citation needs: title, authors, year, source,
identifier (PMID/DOI), and URL.
"""

import json
import os

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
SEMANTIC_SCHOLAR = "https://api.semanticscholar.org/graph/v1/paper/search"
TIMEOUT = 20.0


def _text(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _ncbi_params(extra: dict) -> dict:
    params = {"db": "pubmed", "retmode": "json", **extra}
    key = os.environ.get("NCBI_API_KEY")
    if key:
        params["api_key"] = key
    return params


@tool(
    "pubmed_search",
    "Search PubMed for pharmacokinetics / pediatric dosing literature. Returns "
    "up to `retmax` articles with PMID, title, authors, year, and journal. Use "
    "focused queries, e.g. 'paracetamol neonate pharmacokinetics clearance'.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "retmax": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
async def pubmed_search(args):
    retmax = int(args.get("retmax", 5))
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(
                f"{EUTILS}/esearch.fcgi",
                params=_ncbi_params({"term": args["query"], "retmax": retmax, "sort": "relevance"}),
            )
            r.raise_for_status()
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return _text({"query": args["query"], "results": []})
            s = await c.get(f"{EUTILS}/esummary.fcgi", params=_ncbi_params({"id": ",".join(ids)}))
            s.raise_for_status()
            docs = s.json().get("result", {})
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return _text({"error": f"PubMed search failed: {exc}", "query": args["query"], "results": []})

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
    return _text({"query": args["query"], "results": results})


@tool(
    "semantic_scholar_search",
    "Semantic (meaning-based) paper search via Semantic Scholar. Good for "
    "finding PK-parameter papers when exact keywords are unknown. Returns title, "
    "authors, year, DOI/URL, and abstract snippet.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
async def semantic_scholar_search(args):
    limit = int(args.get("limit", 5))
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(
                SEMANTIC_SCHOLAR,
                params={
                    "query": args["query"],
                    "limit": limit,
                    "fields": "title,authors,year,abstract,externalIds,url",
                },
            )
            r.raise_for_status()
            data = r.json().get("data", [])
    except (httpx.HTTPError, ValueError) as exc:
        return _text({"error": f"Semantic Scholar search failed: {exc}", "query": args["query"], "results": []})

    results = []
    for p in data:
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI")
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:4])
        abstract = (p.get("abstract") or "")[:280]
        results.append({
            "source": "Semantic Scholar",
            "identifier": f"DOI:{doi}" if doi else (p.get("paperId", "")),
            "title": p.get("title", ""),
            "authors": authors,
            "year": p.get("year"),
            "url": p.get("url", ""),
            "snippet": abstract,
        })
    return _text({"query": args["query"], "results": results})


def build_literature_server():
    """The 'literature' in-process MCP server."""
    return create_sdk_mcp_server(
        "literature",
        tools=[pubmed_search, semantic_scholar_search],
    )


LITERATURE_TOOL_NAMES = [
    "mcp__literature__pubmed_search",
    "mcp__literature__semantic_scholar_search",
]
