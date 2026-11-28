"""
PaedScale — retrieval subagent (cheap/fast leg of the multi-agent split).

Separate Anthropic loop on a cheaper model. Returns a structured, CITED adult-PK +
mechanism dossier via PubMed + openFDA + optional web_fetch. Skills hold retrieval
detail so this system prompt stays lean.

On failure: null dossier (source_mode="unavailable") — never fabricate PK.
"""

from __future__ import annotations

import json
import os

from anthropic import Anthropic

from engine.pathway_map import curve_catalogue
from engine.pk_cache import CACHE as PK_CACHE
from retrieval.retrieval_tools import TOOL_FUNCS, TOOL_SCHEMAS, openfda_label
from skills import load_skill, list_skills

RETRIEVAL_MODEL = os.environ.get("RETRIEVAL_MODEL", "claude-sonnet-5")
RETRIEVAL_MAX_TOKENS = int(os.environ.get("RETRIEVAL_MAX_TOKENS", "4000"))

SYSTEM = """You retrieve CITED adult PK + mechanism for one drug, then call submit_dossier once.

Budget: ≤3 retrieval tool calls, then submit. Prefer openFDA pre-fetch in the user message;
fill gaps with pubmed (skill 'pubmed') or web_fetch (skill 'webfetch') for a specific URL.
Load a skill with load_skill before using that method if you need the protocol.

Cite-or-abstain: null any number you cannot source. Empty lists OK.
Adult values = 70 kg. fm keys (engine maturation curves):
{curves}
Map real enzymes onto these; a drug-specific key only for its own drug. Omit fm for a
pathway with no key — do not invent a curve.""".format(curves=curve_catalogue())

DOSSIER_TOOL = {
    "name": "submit_dossier",
    "description": "Emit the structured, cited PK + mechanism dossier. Call exactly once, last.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cl_adult_l_h": {"type": ["number", "null"]},
            "vd_adult_l": {"type": ["number", "null"]},
            "fm": {"type": "object", "additionalProperties": {"type": "number"},
                   "description": "engine pathway key -> fraction of clearance"},
            "target_metric": {"type": "string", "enum": ["css", "auc", "cmax", "time_mic"]},
            "typical_adult_dose_mg_per_day": {"type": ["number", "null"]},
            "oral_bioavailability": {"type": ["number", "null"]},
            "elimination": {"type": "string", "enum": ["renal", "hepatic", "mixed"]},
            "enzymes": {"type": "array", "items": {"type": "string"}},
            "transporters": {"type": "array", "items": {"type": "string"}},
            "active_metabolites": {"type": "array", "items": {"type": "string"}},
            "protein_binding_percent": {"type": ["number", "null"]},
            "toxic_dose_mg_per_kg_per_day": {"type": ["number", "null"]},
            "effective_dose_mg_per_kg_per_day": {"type": ["number", "null"]},
            "citations": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"claim": {"type": "string"}, "source": {"type": "string"}}},
            },
            "hi_table": {
                "type": ["object", "null"],
                "description": "Cited per-class HI dosing table (filled by live extract, not invented)",
            },
            "confidence": {"type": "string", "description": "brief note on data quality / gaps"},
        },
        "required": ["fm", "elimination", "enzymes", "transporters", "active_metabolites",
                     "citations"],
    },
}

LOAD_SKILL_TOOL = {
    "name": "load_skill",
    "description": f"Load a lean skill protocol. Names: {', '.join(list_skills())}.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
}

TOOLS = [
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 1},
    *TOOL_SCHEMAS,
    LOAD_SKILL_TOOL,
    DOSSIER_TOOL,
]

def _abstention(reason: str) -> dict:
    return {
        "cl_adult_l_h": None, "vd_adult_l": None, "fm": {}, "target_metric": "css",
        "typical_adult_dose_mg_per_day": None, "oral_bioavailability": None,
        "elimination": "mixed", "enzymes": [], "transporters": [], "active_metabolites": [],
        "protein_binding_percent": None, "toxic_dose_mg_per_kg_per_day": None,
        "effective_dose_mg_per_kg_per_day": None, "citations": [],
        "hi_table": None,
        "confidence": f"RETRIEVAL UNAVAILABLE ({reason}) — no values retrieved; abstain, do not dose.",
    }


def _attach_live_hi_table(dossier: dict, label: dict, drug: str, indication: str | None) -> dict:
    """Deterministic live extract — one parser, never a second HI table.

    Always write the live result (including None) so a model-invented
    submit_dossier.hi_table cannot be cached as a citation.
    """
    from engine.hi_table import maybe_extract_hi_table

    dossier = dict(dossier)
    dossier["hi_table"] = maybe_extract_hi_table(label, drug=drug, indication=indication)
    return dossier


def fetch(drug: str, indication: str | None = None, *, max_turns: int = 5,
          use_cache: bool = True) -> dict:
    """Retrieve a cited PK+mechanism dossier. Returns live, cache, or unavailable; never raises."""
    trace: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "model": RETRIEVAL_MODEL, "cache_hit": False}

    if use_cache:
        hit = PK_CACHE.get(drug, indication)
        if hit:
            usage["cache_hit"] = True
            return {
                "dossier": hit["dossier"],
                "source_mode": "cache",
                "trace": ["pk_cache hit — skipped live retrieval"],
                "usage": usage,
            }
    try:
        client = Anthropic()
        label = openfda_label(drug)
        hint = ""
        if label.get("found"):
            keep = {k: v for k, v in label.items() if k not in ("drug", "found")}
            hint = "\n\nopenFDA label (pre-fetched — use it, search only for gaps):\n" + \
                   json.dumps(keep)[:2500]
        user = (f"Drug: {drug}\nIndication: {indication or 'unspecified'}\n"
                "Retrieve/confirm adult PK + mechanism, then submit_dossier." + hint)
        messages = [{"role": "user", "content": user}]

        for i in range(max_turns):
            kwargs = {}
            if i == max_turns - 1:
                kwargs["tool_choice"] = {"type": "tool", "name": "submit_dossier"}
            resp = client.messages.create(
                model=RETRIEVAL_MODEL, max_tokens=RETRIEVAL_MAX_TOKENS,
                system=SYSTEM, tools=TOOLS, messages=messages,
                cache_control={"type": "ephemeral"}, **kwargs,
            )
            usage["input_tokens"] += resp.usage.input_tokens
            usage["output_tokens"] += resp.usage.output_tokens

            tool_uses = []
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    trace.append(block.text.strip())
                elif block.type == "tool_use":
                    tool_uses.append(block)
            messages.append({"role": "assistant", "content": resp.content})

            for tu in tool_uses:
                if tu.name == "submit_dossier" and tu.input:
                    dossier = _attach_live_hi_table(tu.input, label, drug, indication)
                    if use_cache:
                        PK_CACHE.set(drug, indication, dossier, source_mode="live")
                    return {"dossier": dossier, "source_mode": "live",
                            "trace": trace, "usage": usage}

            if resp.stop_reason != "tool_use":
                break

            results = []
            for tu in tool_uses:
                if tu.name == "load_skill":
                    out = load_skill(tu.input.get("name", ""))
                elif tu.name in TOOL_FUNCS:
                    try:
                        out = TOOL_FUNCS[tu.name](tu.input)
                    except Exception as te:
                        out = {"error": f"{tu.name} failed: {te}"}
                else:
                    continue  # web_search is server-side
                results.append({"type": "tool_result", "tool_use_id": tu.id,
                                "content": json.dumps(out)})
            if results:
                messages.append({"role": "user", "content": results})

        return {"dossier": _abstention("no dossier submitted in budget"),
                "source_mode": "unavailable",
                "trace": trace + ["retrieval did not submit a dossier in budget"], "usage": usage}
    except Exception as e:
        return {"dossier": _abstention(str(e)), "source_mode": "unavailable",
                "trace": trace + [f"retrieval error: {e}"], "usage": usage}


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "gentamicin"
    out = fetch(d, "sepsis")
    print(f"source_mode = {out['source_mode']}   (model {out['usage']['model']})")
    print(json.dumps(out["dossier"], indent=2)[:1600])
