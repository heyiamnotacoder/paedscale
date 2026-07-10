"""In-process Messages-API orchestrator (no Node subprocess, no Agent SDK).

Whiteboard shape:
  USER → intake.parse → DRUG + AGE + WT + EDGE_CASE
    ├─ fetch_drug_pk (openFDA, deterministic)   ┐  run concurrently
    └─ guideline-agent (parallel Sonnet call)   ┘  (asyncio.gather)
        → LLM ORCH (Sonnet tool-use loop, adaptive thinking, prompt-cached):
             tools: PK Maths (deterministic) + research (edge-gated: pubmed / MCP)
             ends by calling submit_recommendation with the self-critiqued payload
        → RESULT: mechanistic/guideline dose · rationale & grading · citations

Golden rule: mechanistic numbers only ever come from the PK-maths tools; the LLM feeds structured
inputs and explains. Guideline short-path may convert a published mg/kg to mg for the weight.

The critic subagent is gone — the orchestrator argues against its own dose and fills `critique`
(with `dose_grade`) in the submit payload.
"""

import asyncio
import json
import os
import re

import anthropic
from dotenv import load_dotenv

from app.agent import intake
from app.agent.math_tools import MATH_TOOLS, is_math_tool, run_math_tool
from app.agent.recovery import assemble_partial_payload
from app.agent.research_tools import RESEARCH_TOOLS, is_research_tool, run_research_tool

load_dotenv()

ORCH_MODEL = os.environ.get("PAEDSCALE_ORCH_MODEL", "claude-sonnet-5")
MAX_TURNS = int(os.environ.get("PAEDSCALE_MAX_TURNS", "8"))
MAX_TOKENS = int(os.environ.get("PAEDSCALE_MAX_TOKENS", "8000"))
GUIDELINE_AGENT_ON = os.environ.get("PAEDSCALE_GUIDELINE_AGENT", "1") != "0"

# MCP connector (edge branch) — gated on an env-configured server list so the app works offline and
# in tests. Set PAEDSCALE_MCP_SERVERS to a JSON array of {type:"url",name,url[,authorization_token]}
# to route edge-case literature through a PubMed / ClinicalTrials.gov MCP instead of pubmed_search.
_MCP_SERVERS_RAW = os.environ.get("PAEDSCALE_MCP_SERVERS", "").strip()
MCP_BETA = "mcp-client-2025-11-20"

# Sonnet-5 intro pricing ($/token) for a rough cost estimate (observability only).
_PRICE_IN, _PRICE_OUT = 2.0 / 1e6, 10.0 / 1e6
_PRICE_CACHE_READ, _PRICE_CACHE_WRITE = 0.2 / 1e6, 2.5 / 1e6

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        _client = anthropic.AsyncAnthropic()
    return _client


def _mcp_servers() -> list[dict]:
    if not _MCP_SERVERS_RAW:
        return []
    try:
        servers = json.loads(_MCP_SERVERS_RAW)
        return servers if isinstance(servers, list) else []
    except ValueError:
        return []


def _usage_cost(usage) -> float:
    if usage is None:
        return 0.0
    g = lambda a: getattr(usage, a, 0) or 0  # noqa: E731
    return (
        g("input_tokens") * _PRICE_IN
        + g("output_tokens") * _PRICE_OUT
        + g("cache_read_input_tokens") * _PRICE_CACHE_READ
        + g("cache_creation_input_tokens") * _PRICE_CACHE_WRITE
    )


# --------------------------------------------------------------------------- #
# Final payload — captured via a submit_recommendation tool (loop terminator). #
# --------------------------------------------------------------------------- #

SUBMIT_TOOL = {
    "name": "submit_recommendation",
    "description": "Record the final structured recommendation. Call this exactly once, LAST, after "
    "you have argued against your own dose and filled `critique`. Copy computed numbers verbatim "
    "from extrapolate_dose / check_safety_bounds (or published mg/kg on the guideline short path).",
    "input_schema": {
        "type": "object",
        "properties": {
            "drug_name": {"type": "string"},
            "covariates": {"type": "object"},
            "adult_pk": {"type": "object", "description": "clearance, volume, protein binding, F, driver"},
            "pathways": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "fm": {"type": "number"},
                        "organ": {"type": "string"},
                        "tm50_weeks": {"type": "number"},
                        "hill": {"type": "number"},
                        "maturation_fraction": {"type": "number"},
                    },
                    "required": ["name", "fm"],
                },
            },
            "dosing_method": {"type": "string"},
            "source_of_dose": {"type": "string", "enum": ["guideline", "mechanistic", "partial_recovery"]},
            "dose_recommendation": {
                "type": "object",
                "description": "MUST contain numeric dose_mg, dose_mg_per_kg, interval_h, method. On the "
                "mechanistic path copy them verbatim from extrapolate_dose / check_safety_bounds. On the "
                "guideline path fill them from the mg/kg × weight conversion — put the NUMBERS here, not "
                "only in the rationale.",
                "properties": {
                    "dose_mg": {"type": "number"},
                    "dose_mg_per_kg": {"type": "number"},
                    "interval_h": {"type": "number"},
                    "method": {"type": "string"},
                },
            },
            "evidence_grade": {
                "type": "object",
                "properties": {
                    "grade": {"type": "string", "enum": ["high", "moderate", "low", "very-low"]},
                    "rationale": {"type": "string"},
                },
            },
            "citations": {"type": "array", "items": {"type": "object"}},
            "concordance": {"type": "object"},
            "critique": {
                "type": "object",
                "properties": {
                    "objections": {"type": "array", "items": {"type": "string"}},
                    "resolution": {"type": "string"},
                    "residual_risks": {"type": "array", "items": {"type": "string"}},
                    "dose_grade": {"type": "string", "enum": ["accept", "accept_with_caveats", "revise"]},
                },
            },
            "safety_flags": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string", "description": "Cited clinical reasoning, concise (≤180 words)."},
        },
        "required": ["drug_name", "dose_recommendation", "rationale", "evidence_grade", "critique"],
    },
}

SYSTEM_PROMPT = f"""\
You are PaedScale's orchestrator: a pediatric dose-extrapolation agent. Derive a defensible pediatric
STARTING dose, cite every step, then finish with submit_recommendation.

HARD RULE: never invent arithmetic for mechanistic doses. Every mechanistic number — clearance,
volume, maturation, eGFR, the dose, the safety check, concordance — comes from a PK-maths tool
(extrapolate_dose / check_safety_bounds / find_concordance / list_pathways). Guideline short-path
doses may convert a published mg/kg to mg for this weight (state the conversion; no allometry theatre).

{intake.INTAKE_INSTRUCTIONS}{intake.COVARIATE_SPEC}
ORGAN IMPAIRMENT: if renal/hepatic impairment, low eGFR, high SCr for age, Child-Pugh ≥7, liver
disease, or AKI → FULL mechanistic path only. Never use the guideline short path.

PIPELINE:
 1. You are given `parsed` covariates and pre-fetched `drug_data` (+ maybe `guideline_cases`). Use them.
 2. PATH: (A) GUIDELINE SHORT PATH if NOT organ-impaired AND a solid published pediatric mg/kg exists
    for this drug+age+route — convert to mg for THIS weight and put dose_mg, dose_mg_per_kg, interval_h
    (numbers) in dose_recommendation; set source_of_dose="guideline", skip extrapolate_dose. Only call
    find_concordance when guideline_cases include a numeric pma_weeks.
    (B) FULL MECHANISTIC PATH otherwise — pick the pathway fm split (list_pathways for allowed names),
    choose a method from the PK/PD driver, call extrapolate_dose ONCE, then check_safety_bounds ONCE,
    then find_concordance if guideline_cases exist. source_of_dose="mechanistic".
 3. SELF-CRITIQUE (mandatory): argue against the dose — right path? method vs driver? fm complete?
    within safe/effective window? assumptions acknowledged? Fill critique{{objections, dose_grade,
    residual_risks}}. If dose_grade would be "revise" and the fix is obvious, do it once, then submit.
 4. submit_recommendation exactly once. Copy math numbers verbatim. Never end without submitting.

Be economical: on the happy path this is one extrapolate + one safety check + submit. Only use
pubmed_search / edge tools for genuinely unlabelled or edge-case drugs. Decision support only.
"""


async def _emit(on_event, agent: str, kind: str, text: str = "", **extra) -> None:
    if on_event is None:
        return
    ev = {"agent": agent, "kind": kind, "text": text, **extra}
    res = on_event(ev)
    if asyncio.iscoroutine(res):
        await res


def _first_json(text: str) -> dict | None:
    text = (text or "").strip()
    for candidate in (text, (re.search(r"\{[\s\S]*\}", text) or [None])[0] if "{" in text else None):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate) if isinstance(candidate, str) else json.loads(candidate.group(0))
            if isinstance(obj, dict):
                return obj
        except (ValueError, AttributeError):
            continue
    return None


# --------------------------------------------------------------------------- #
# Parallel guideline-agent (named sub-agent, overlaps the drug fetch).         #
# --------------------------------------------------------------------------- #

_GUIDELINE_PROMPT = """\
You are PaedScale's guideline sub-agent. For the drug and child below, list any well-established
published PEDIATRIC dosing regimens (AAP / BNFC / Lexicomp / FDA label / neonatal formularies) as
mg/kg or mg/kg/day, with the age band and source. Reply with ONE JSON object only:
{"guideline_cases": [{"age_group": "", "pma_weeks": <number|null>, "guideline_dose_mg_per_kg": <number>,
"source": ""}], "note": ""}
If you know none with confidence, return an empty list. Do not invent numbers."""


async def _guideline_agent(client, drug: str, covariates: dict, cost: list) -> dict:
    if not (GUIDELINE_AGENT_ON and drug):
        return {"guideline_cases": [], "note": "guideline-agent disabled"}
    try:
        msg = await client.messages.create(
            model=ORCH_MODEL,
            max_tokens=800,
            system=_GUIDELINE_PROMPT,
            messages=[{"role": "user", "content": f"drug: {drug}\ncovariates: {json.dumps(covariates)}"}],
        )
    except anthropic.AnthropicError as exc:
        return {"guideline_cases": [], "note": f"guideline-agent error: {exc}"}
    cost.append(_usage_cost(getattr(msg, "usage", None)))
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    parsed = _first_json(text) or {}
    return {"guideline_cases": parsed.get("guideline_cases", []) or [], "note": parsed.get("note", "")}


# --------------------------------------------------------------------------- #
# The orchestrator agent loop.                                                 #
# --------------------------------------------------------------------------- #


async def _dispatch_tool(name: str, args: dict) -> dict:
    if is_math_tool(name):
        return await run_math_tool(name, args)
    if is_research_tool(name):
        return await run_research_tool(name, args)
    return {"error": f"unknown tool {name}"}


async def run_orchestrator(query: str, on_event=None, overrides: dict | None = None):
    """Run the pipeline. Returns (payload|None, cost_usd, messages).

    `on_event(event_dict)` is called (awaited if coroutine) per trace event for the SSE endpoint.
    """
    client = _get_client()
    cost: list[float] = []

    # 0. Intake (Python, deterministic).
    await _emit(on_event, "orchestrator", "status", "parsing the case")
    parsed = intake.parse(query)
    covariates = intake.merge_overrides(parsed["covariates"], overrides)
    drug = covariates.get("drug_name") or parsed.get("drug_name") or ""
    organ_impaired = parsed["organ_impaired"] or bool((overrides or {}).get("organ_impaired"))

    # 1. Deterministic drug fetch  ∥  guideline-agent  (concurrent).
    await _emit(on_event, "guideline-agent", "status", f"searching guidelines for {drug or 'drug'}")
    await _emit(on_event, "orchestrator", "tool", f"fetch_drug_pk: {drug}", tool="fetch_drug_pk")
    drug_data, guideline = await asyncio.gather(
        run_research_tool("fetch_drug_pk", {"drug_name": drug}),
        _guideline_agent(client, drug, covariates, cost),
    )
    edge_case = bool(parsed["edge_case"]) or not drug_data.get("found", False)
    if guideline.get("guideline_cases"):
        await _emit(on_event, "guideline-agent", "tool_result",
                    f"{len(guideline['guideline_cases'])} guideline case(s)")

    # 2. Orchestrator tool-use loop.
    tools = list(MATH_TOOLS) + [SUBMIT_TOOL]
    mcp_servers = _mcp_servers()
    use_mcp = edge_case and bool(mcp_servers)
    if edge_case and not use_mcp:
        tools += RESEARCH_TOOLS  # native pubmed fallback
        await _emit(on_event, "edge-research-agent", "status", "edge case — literature tools enabled")
    if use_mcp:
        tools += [{"type": "mcp_toolset", "mcp_server_name": s["name"]} for s in mcp_servers]
        await _emit(on_event, "edge-research-agent", "status", "edge case — MCP literature enabled")

    context = {
        "query": query,
        "parsed": covariates,
        "organ_impaired": organ_impaired,
        "edge_case": edge_case,
        "drug_data": drug_data,
        "guideline_cases": guideline.get("guideline_cases", []),
    }
    messages = [{"role": "user", "content": "Analyse this case and submit a recommendation.\n"
                 + json.dumps(context, default=str)}]
    system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    thinking = {"type": "adaptive", "display": "summarized"}

    holder: dict = {}
    math_results: dict = {}
    raw_messages: list = []

    for _turn in range(MAX_TURNS):
        create = client.beta.messages.stream if use_mcp else client.messages.stream
        kwargs = dict(model=ORCH_MODEL, max_tokens=MAX_TOKENS, system=system,
                      tools=tools, messages=messages, thinking=thinking)
        if use_mcp:
            kwargs["mcp_servers"] = mcp_servers
            kwargs["betas"] = [MCP_BETA]

        async with create(**kwargs) as stream:
            async for event in stream:
                et = getattr(event, "type", "")
                if et == "content_block_start":
                    blk = getattr(event, "content_block", None)
                    if getattr(blk, "type", "") == "tool_use":
                        await _emit(on_event, "orchestrator", "tool",
                                    _tool_label(blk.name), tool=blk.name)
                elif et == "content_block_delta":
                    d = getattr(event, "delta", None)
                    if getattr(d, "type", "") == "thinking_delta" and getattr(d, "thinking", ""):
                        await _emit(on_event, "orchestrator", "thinking", d.thinking)
            final = await stream.get_final_message()

        raw_messages.append(final)
        cost.append(_usage_cost(getattr(final, "usage", None)))
        messages.append({"role": "assistant", "content": final.content})

        if final.stop_reason != "tool_use":
            break

        tool_results = []
        submitted = False
        for blk in final.content:
            if getattr(blk, "type", "") != "tool_use":
                continue
            args = blk.input or {}
            if blk.name == "submit_recommendation":
                holder["payload"] = args
                submitted = True
                tool_results.append({"type": "tool_result", "tool_use_id": blk.id,
                                     "content": "Recorded."})
                continue
            try:
                result = await _dispatch_tool(blk.name, args)
                if is_math_tool(blk.name) and not (isinstance(result, dict) and result.get("error")):
                    math_results[blk.name] = result
                await _emit(on_event, "orchestrator", "tool_result", _result_line(blk.name, result))
            except Exception as exc:  # keep the loop alive; report the error to the model
                result = {"error": str(exc)}
                await _emit(on_event, "orchestrator", "tool_result", f"{blk.name} errored")
            tool_results.append({"type": "tool_result", "tool_use_id": blk.id,
                                 "content": json.dumps(result, default=str)})
        messages.append({"role": "user", "content": tool_results})
        if submitted:
            break

    payload = holder.get("payload")
    if payload is None:
        payload = assemble_partial_payload(math_results, query=query)
        if payload is not None:
            await _emit(on_event, "orchestrator", "status", "assembled partial result from math tools")

    total_cost = round(sum(cost), 6) if cost else None
    await _emit(on_event, "orchestrator", "status",
                "run complete" + (f" (${total_cost:.4f})" if total_cost else ""))
    return payload, total_cost, raw_messages


_TOOL_LABELS = {
    "fetch_drug_pk": "fetched adult PK (openFDA)",
    "pubmed_search": "searched PubMed",
    "list_pathways": "loaded the maturation curve library",
    "extrapolate_dose": "computed the dose (allometry × maturation × organ fn)",
    "check_safety_bounds": "checked the safe/effective bounds",
    "find_concordance": "compared against guideline (concordance)",
    "submit_recommendation": "assembled the final recommendation",
}


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, name)


def _result_line(name: str, result: dict) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"{_tool_label(name)}: error"
    if name == "extrapolate_dose" and isinstance(result.get("dose"), dict):
        d = result["dose"]
        return f"dose {d.get('dose_mg')} mg ({d.get('dose_mg_per_kg')} mg/kg)"
    return f"{_tool_label(name)}: ok"
