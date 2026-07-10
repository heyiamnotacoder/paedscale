"""The multi-agent orchestrator (cost-bounded, result-guaranteed).

A Sonnet orchestrator plans the case:
  - Guideline short path when a solid published regimen matches and the child is
    NOT renally/hepatically impaired.
  - Otherwise one research-agent (Haiku) gathers pathways + adult PK + safety,
    then Python math tools compute the dose.
  - A mandatory critic-agent grades the dose before submit_recommendation.

Golden rule: the orchestrator may only obtain a dose by calling the math tools
(or returning a published guideline dose on the short path). Cost ceiling ~$2;
typical runs should stay well under that. Empty results are recovered from math
tool outputs when submit never fires.
"""

import os

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    create_sdk_mcp_server,
    tool,
)
from dotenv import load_dotenv

from app.agent.intake import COVARIATE_SPEC, INTAKE_INSTRUCTIONS
from app.agent.math_tools import MATH_TOOL_NAMES, build_math_server
from app.agent.recovery import assemble_partial_payload
from app.agent.research_tools import LITERATURE_TOOL_NAMES, build_literature_server

load_dotenv()

# Cheap defaults; override via env without code changes.
ORCHESTRATOR_MODEL = os.environ.get("PAEDSCALE_ORCH_MODEL", "claude-sonnet-5")
SUBAGENT_MODEL = os.environ.get("PAEDSCALE_SUBAGENT_MODEL", "claude-haiku-4-5-20251001")
CRITIC_MODEL = os.environ.get("PAEDSCALE_CRITIC_MODEL", "claude-sonnet-5")
MAX_TURNS = int(os.environ.get("PAEDSCALE_MAX_TURNS", "14"))
RESEARCH_MAX_TURNS = int(os.environ.get("PAEDSCALE_RESEARCH_MAX_TURNS", "7"))
SUBAGENT_MAX_TURNS = int(os.environ.get("PAEDSCALE_SUBAGENT_MAX_TURNS", str(RESEARCH_MAX_TURNS)))
BUDGET_USD = float(os.environ.get("PAEDSCALE_BUDGET_USD", "2.0"))

# Research agent: literature + web + one optional full-text fetch.
RESEARCH_TOOLS = [*LITERATURE_TOOL_NAMES, "WebSearch", "WebFetch"]

# Async multi-agent / team plumbing that caused thrash in live runs.
DISALLOWED_TOOLS = [
    "ScheduleWakeup",
    "SendMessage",
    "TaskOutput",
    "TaskGet",
    "ToolSearch",
    "NotebookEdit",
    "Bash",
    "Edit",
    "Write",
    "Read",
    "Glob",
    "Grep",
]

SUBMIT_TOOL = "mcp__result__submit_recommendation"

RESEARCH_EFFICIENCY = (
    " You may run several targeted searches (PubMed, Semantic Scholar, WebSearch) and at most "
    "ONE WebFetch for a label/full text if a key number is missing. End with ONE compact JSON "
    "block covering all required fields — no prose survey. If a source rate-limits, switch "
    "source; do not loop on the same failed call."
)


# --------------------------------------------------------------------------- #
# Final structured output — captured via a per-request in-process tool.        #
# --------------------------------------------------------------------------- #

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "drug_name": {"type": "string"},
        "covariates": {
            "type": "object",
            "description": "Parsed case covariates; include assumed_defaults[] for anything you defaulted.",
        },
        "adult_pk": {
            "type": "object",
            "description": "Adult PK used: clearance, volume, protein binding, bioavailability, PK/PD driver.",
        },
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
        "source_of_dose": {
            "type": "string",
            "enum": ["guideline", "mechanistic", "partial_recovery"],
            "description": "guideline = published regimen short path; mechanistic = allometry×maturation.",
        },
        "dose_recommendation": {
            "type": "object",
            "description": "The dose. On mechanistic path copy numbers verbatim from extrapolate_dose / "
            "check_safety_bounds. On guideline path convert published mg/kg to mg for this weight.",
        },
        "evidence_grade": {
            "type": "object",
            "properties": {
                "grade": {"type": "string", "enum": ["high", "moderate", "low", "very-low"]},
                "rationale": {"type": "string"},
            },
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "authors": {"type": "string"},
                    "year": {"type": "string"},
                    "source": {"type": "string"},
                    "identifier": {"type": "string"},
                    "url": {"type": "string"},
                    "claim_supported": {"type": "string"},
                },
            },
        },
        "concordance": {"type": "object"},
        "critique": {
            "type": "object",
            "properties": {
                "objections": {"type": "array", "items": {"type": "string"}},
                "resolution": {"type": "string"},
                "residual_risks": {"type": "array", "items": {"type": "string"}},
                "dose_grade": {
                    "type": "string",
                    "enum": ["accept", "accept_with_caveats", "revise"],
                    "description": "From critic-agent.",
                },
            },
        },
        "safety_flags": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string", "description": "The full cited clinical reasoning narrative."},
    },
    "required": ["drug_name", "dose_recommendation", "rationale", "evidence_grade", "critique"],
}


def _build_result_capture():
    """A per-request MCP server whose one tool records the final recommendation."""
    holder: dict = {}

    @tool(
        "submit_recommendation",
        "Record the final structured recommendation. Call this exactly once, last, "
        "AFTER the mandatory critic-agent has graded the dose. Copy computed numbers "
        "verbatim from the math tools (or published guideline numbers on the short path).",
        SUBMIT_SCHEMA,
    )
    async def submit_recommendation(args):
        holder["payload"] = args
        return {"content": [{"type": "text", "text": "Recommendation recorded."}]}

    server = create_sdk_mcp_server("result", tools=[submit_recommendation])
    return server, holder


# --------------------------------------------------------------------------- #
# Specialist subagents (context-isolated; terse task in, compact JSON out).    #
# --------------------------------------------------------------------------- #

SUBAGENTS = {
    "research-agent": AgentDefinition(
        description=(
            "Single literature agent: elimination pathways (fm), adult PK, safety bounds, "
            "and any pediatric guideline cases. Spawn once with a complete research brief."
        ),
        model=SUBAGENT_MODEL,
        tools=RESEARCH_TOOLS,
        maxTurns=RESEARCH_MAX_TURNS,
        background=False,
        prompt=(
            "You are PaedScale's research specialist. For the drug and child described in the "
            "task brief, gather ALL of the following and return ONE compact JSON object only:\n"
            "{\n"
            '  "adult_pk": {"clearance_l_per_h": <70kg>, "volume_l": <>, "protein_binding": <0-1>, '
            '"bioavailability": <0-1>, "driver": "auc|css|cmax|trough|loading", "notes": ""},\n'
            '  "pathways": [{"name": "<library name>", "fm": <0-1>, "organ": "hepatic|renal|other"}],\n'
            '  "safety": {"min_effective_mg_per_kg": <>, "max_safe_mg_per_kg": <>, "nti": false, '
            '"tdm_required": false, "toxicities": []},\n'
            '  "guideline_cases": [{"age_group": "", "pma_weeks": <>, "guideline_dose_mg_per_kg": <>, '
            '"source": ""}],\n'
            '  "citations": [{"title": "", "authors": "", "year": "", "source": "", "identifier": "", '
            '"url": "", "claim_supported": ""}]\n'
            "}\n"
            "Pathway names MUST be from: CYP3A4, CYP1A2, CYP2C9, CYP2C19, CYP2D6, CYP2E1, UGT1A1, "
            "UGT2B7, sulfation, renal_GFR, hepatic_other. fm values should sum to ~1. "
            "Flag sparse data explicitly in adult_pk.notes."
            + RESEARCH_EFFICIENCY
        ),
    ),
    "critic-agent": AgentDefinition(
        description="Mandatory red-team and dose grading before the recommendation is submitted.",
        model=CRITIC_MODEL,
        tools=[],
        maxTurns=1,
        background=False,
        prompt=(
            "You are a skeptical senior pediatric clinical pharmacist. You receive an assembled "
            "draft recommendation (drug, covariates, organ function, pathways/fm, method, computed "
            "or guideline dose, safety bounds, evidence notes). Argue against it. Check:\n"
            "- Is the path correct (guideline vs mechanistic)? Organ impairment MUST use mechanistic.\n"
            "- Method vs PK/PD driver; fm split complete; maturation/organ modifiers on the right routes.\n"
            "- Dose within safe/effective window and clinically plausible for age/weight.\n"
            "- Missing-data assumptions acknowledged.\n"
            "Reply with ONE compact JSON only:\n"
            "{\n"
            '  "objections": [{"text": "...", "material": true|false}],\n'
            '  "dose_grade": "accept" | "accept_with_caveats" | "revise",\n'
            '  "resolution": "one short paragraph",\n'
            '  "residual_risks": ["..."],\n'
            '  "verdict": "one line"\n'
            "}\n"
            "Do not rubber-stamp. If dose_grade is revise, say exactly what must change."
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Orchestrator system prompt and options.                                     #
# --------------------------------------------------------------------------- #

ORCHESTRATOR_SYSTEM = f"""\
You are PaedScale's orchestrator: a pediatric dose-extrapolation agent. You derive a
defensible pediatric STARTING dose, show and cite every step, and always finish with
submit_recommendation after a mandatory critic-agent pass.

HARD RULE: you never invent arithmetic for mechanistic doses. Every mechanistic number —
clearance, volume, maturation, eGFR, the dose, the safety check, concordance — comes from a
`mcp__paedscale_math__*` tool call. Guideline short-path doses may use published mg/kg converted
to mg for this weight (state the conversion; no allometry theater).

{INTAKE_INSTRUCTIONS}
{COVARIATE_SPEC}

TOOLS: All tools are already available by full name. Call them DIRECTLY — never ToolSearch.
Never use ScheduleWakeup, SendMessage, TaskOutput, TaskGet, Bash, or file tools. Task is
SYNCHRONOUS: when a subagent returns, its findings are already in your context. Never end a
turn to "wait". Use only named agents: research-agent, critic-agent (background=false).

ORGAN IMPAIRMENT (critical):
  Treat as renally or hepatically impaired if ANY of: query states renal/hepatic impairment;
  reduced eGFR/CrCl; elevated serum creatinine for age; Child-Pugh ≥7 or described liver disease;
  acute kidney injury. If impaired → FULL mechanistic path ONLY. Never use the guideline short path.

PIPELINE — be economical:

  1. INTAKE — parse covariates; flag assumed defaults; decide organ_impaired yes/no.

  2. PATH SELECTION
     A) GUIDELINE SHORT PATH — only if NOT organ_impaired AND a solid published pediatric
        regimen exists for this drug + age band + route (+ indication if relevant): clear
        numeric mg/kg or mg/kg/day from AAP/BNFC/label/trusted guideline.
        - Do 1–2 WebSearch or pubmed_search only (no research-agent).
        - Convert to dose_mg and dose_mg_per_kg for this child; set dosing_method="guideline",
          source_of_dose="guideline".
        - Optional: note concordance as self-match.
        - Skip extrapolate_dose on this path.
     B) FULL MECHANISTIC PATH — if organ_impaired OR no solid guideline:
        - Call list_pathways once if you need allowed pathway names.
        - Spawn research-agent ONCE via Task with a COMPLETE brief: drug, indication, route,
          weight, PMA, organ function labs/flags, and the exact JSON fields required.
        - Choose method from the PK/PD driver (auc|css|cmax|trough|loading|mgkg_linear).
        - Call extrapolate_dose ONCE with pathways, method, method_params, organ covariates.
        - Call check_safety_bounds ONCE.
        - Call find_concordance if guideline cases exist (comparison only — does not replace dose).
        - Set source_of_dose="mechanistic".

  3. CRITIC (mandatory on BOTH paths) — Task critic-agent ONCE with the full draft (dose,
     method, covariates, organ flags, bounds, path chosen). Fold its JSON into critique
     (include dose_grade). If dose_grade is "revise" and the fix is clear, apply ONE fix
     (one re-extrapolate or adjusted flags) then proceed — do not re-research.

  4. GRADE evidence (high/moderate/low/very-low) from data quality + critic caveats.

  5. submit_recommendation exactly once. Include critique with dose_grade. Copy math numbers
     verbatim. Never end the run without submit_recommendation.

CONTROL RULES:
  - Do NOT spawn pathway-agent / pk-agent / safety-agent (removed). One research-agent only.
  - Do NOT re-run research you already have.
  - Prefer finishing with an honest low-grade result over stopping empty.

Safety: decision support only, not a prescribing order. Surface uncertainty and NTI→TDM warnings.
"""


def build_options(result_server) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=ORCHESTRATOR_MODEL,
        system_prompt=ORCHESTRATOR_SYSTEM,
        mcp_servers={
            "paedscale_math": build_math_server(),
            "literature": build_literature_server(),
            "result": result_server,
        },
        agents=SUBAGENTS,
        allowed_tools=[
            *MATH_TOOL_NAMES,
            *LITERATURE_TOOL_NAMES,
            "WebSearch",
            "Task",
            SUBMIT_TOOL,
        ],
        disallowed_tools=DISALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        setting_sources=[],  # isolate: ignore the user's global CLAUDE.md / settings / skills
        max_turns=MAX_TURNS,
        max_budget_usd=BUDGET_USD,
        strict_mcp_config=True,
    )


def _math_succeeded(messages: list) -> bool:
    """True if extrapolate_dose (or equivalent) already produced a dose in the stream."""
    from app.agent.recovery import extract_math_results

    return "extrapolate_dose" in extract_math_results(messages)


async def run_orchestrator(query: str, on_message=None):
    """Run the full pipeline for a query.

    Returns (payload | None, cost_usd | None, messages). `on_message`, if given,
    is awaited per streamed message (used by the SSE endpoint). Budget ceiling is
    PAEDSCALE_BUDGET_USD (~$2). If submit_recommendation never fires, a partial
    payload is assembled from math tool results when possible.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set.")

    result_server, holder = _build_result_capture()
    options = build_options(result_server)
    messages = []
    cost_usd = None
    interrupted = False

    async with ClaudeSDKClient(options=options) as client:
        await client.query(query)
        async for msg in client.receive_response():
            messages.append(msg)
            if on_message is not None:
                await on_message(msg)
            tc = getattr(msg, "total_cost_usd", None)
            if tc is not None:
                cost_usd = tc
                # Soft interrupt only when over budget AND no payload yet AND math
                # has not already succeeded (prefer letting critic+submit finish).
                if (
                    not interrupted
                    and tc >= BUDGET_USD
                    and holder.get("payload") is None
                    and not _math_succeeded(messages)
                ):
                    interrupted = True
                    await client.interrupt()

    payload = holder.get("payload")
    if payload is None:
        payload = assemble_partial_payload(messages, query=query)
    return payload, cost_usd, messages
