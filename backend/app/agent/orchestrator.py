"""The multi-agent orchestrator (cost-bounded).

A Sonnet orchestrator plans the case, delegates research to three context-isolated
Haiku subagents (pathway / PK / safety) spawned in parallel, folds in a guideline
lookup, computes every number through the deterministic `paedscale_math` tools,
runs one Sonnet self-critique pass, and emits a single structured recommendation.

Golden rule: the orchestrator may only obtain a dose by calling the math tools.
Cost discipline: cheap models, low turn caps, no bulk WebFetch (one surgical fetch
for the PK agent only), compact subagent I/O, and a hard budget guard. Everything
tunable via env so a query stays ≤ $0.50.
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
from app.agent.research_tools import LITERATURE_TOOL_NAMES, build_literature_server

load_dotenv()

# Cheap defaults; override via env without code changes.
ORCHESTRATOR_MODEL = os.environ.get("PAEDSCALE_ORCH_MODEL", "claude-sonnet-5")
SUBAGENT_MODEL = os.environ.get("PAEDSCALE_SUBAGENT_MODEL", "claude-haiku-4-5-20251001")
CRITIC_MODEL = os.environ.get("PAEDSCALE_CRITIC_MODEL", "claude-sonnet-5")
MAX_TURNS = int(os.environ.get("PAEDSCALE_MAX_TURNS", "14"))
SUBAGENT_MAX_TURNS = int(os.environ.get("PAEDSCALE_SUBAGENT_MAX_TURNS", "3"))
BUDGET_USD = float(os.environ.get("PAEDSCALE_BUDGET_USD", "0.40"))

# Research subagents get literature MCP + WebSearch snippets. Bulk WebFetch is
# banned; only the PK agent may make ONE surgical full-text/label fetch.
RESEARCH_TOOLS = [*LITERATURE_TOOL_NAMES, "WebSearch"]
PK_TOOLS = [*RESEARCH_TOOLS, "WebFetch"]

EFFICIENCY = (
    " Be efficient: at most 2 targeted searches (the PK agent may add ONE full-text/label "
    "WebFetch only if a key number needs confirming). Then reply with a COMPACT structured "
    "finding — the fm split / PK values / bounds and citations — not prose. Do not survey the "
    "literature."
)

SUBMIT_TOOL = "mcp__result__submit_recommendation"


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
        "dose_recommendation": {
            "type": "object",
            "description": "The computed dose. Copy the numbers verbatim from extrapolate_dose / "
            "check_safety_bounds — do not alter them. Include safety_bounds.",
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
            },
        },
        "safety_flags": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string", "description": "The full cited clinical reasoning narrative."},
    },
    "required": ["drug_name", "dose_recommendation", "rationale", "evidence_grade"],
}


def _build_result_capture():
    """A per-request MCP server whose one tool records the final recommendation."""
    holder: dict = {}

    @tool(
        "submit_recommendation",
        "Record the final structured recommendation. Call this exactly once, last, "
        "after the dose is computed, safety-checked, and critiqued. Copy computed "
        "numbers verbatim from the math tools.",
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
    "pathway-agent": AgentDefinition(
        description="Decomposes a drug's elimination into ALL contributing pathways (the multi-fm split).",
        model=SUBAGENT_MODEL,
        tools=RESEARCH_TOOLS,
        maxTurns=SUBAGENT_MAX_TURNS,
        prompt=(
            "You are a drug-metabolism specialist. For the given drug, determine EVERY "
            "elimination pathway and the fraction of total clearance (fm) each carries — "
            "hepatic enzymes (specific CYPs, UGTs, sulfation), renal excretion, biliary. Real "
            "drugs use several routes; do not collapse to one. Map each route to the modelled "
            "pathway names where possible (CYP3A4, CYP1A2, CYP2C9, CYP2C19, CYP2D6, CYP2E1, "
            "UGT1A1, UGT2B7, sulfation, renal_GFR, hepatic_other). Report fm's summing to ~1, each "
            "route's organ, a citation per fm, and your confidence." + EFFICIENCY
        ),
    ),
    "pk-agent": AgentDefinition(
        description="Retrieves adult pharmacokinetics and the drug's PK/PD-driving exposure metric.",
        model=SUBAGENT_MODEL,
        tools=PK_TOOLS,
        maxTurns=SUBAGENT_MAX_TURNS,
        prompt=(
            "You are a clinical pharmacokineticist. Retrieve adult PK: clearance (L/h, 70 kg), "
            "volume of distribution (L), plasma protein binding, oral bioavailability, and — "
            "critically — which exposure metric drives efficacy/toxicity (total AUC, steady-state "
            "concentration, peak Cmax, or trough), since that dictates the dosing method. You may "
            "make ONE full-text/label WebFetch to confirm the single most important number. Cite "
            "each value. Flag sparse/low-quality data explicitly." + EFFICIENCY
        ),
    ),
    "safety-agent": AgentDefinition(
        description="Establishes the safe-maximum and minimum-effective dose window and TDM needs.",
        model=SUBAGENT_MODEL,
        tools=RESEARCH_TOOLS,
        maxTurns=SUBAGENT_MAX_TURNS,
        prompt=(
            "You are a medication-safety pharmacist. For this drug and population determine: the "
            "maximum safe dose (mg/kg), the minimum effective dose (mg/kg), whether it is a "
            "narrow-therapeutic-index drug needing therapeutic drug monitoring, and key toxicities. "
            "Cite sources. These bounds are enforced — a dose outside them is clamped and flagged." + EFFICIENCY
        ),
    ),
    "critic-agent": AgentDefinition(
        description="Red-teams the assembled recommendation before it is finalized.",
        model=CRITIC_MODEL,
        tools=[],  # no tools: one reasoning pass over the assembled facts (cheap)
        maxTurns=1,
        prompt=(
            "You are a skeptical senior reviewer. Given the drug, covariates, pathway split, chosen "
            "dosing method, computed dose, and safety bounds, argue against them. Is the method right "
            "for this drug's PK/PD driver? Is the fm split defensible and complete? Were maturation "
            "and organ function applied to the correct routes? Is the dose within the safe/effective "
            "window and clinically plausible? Are missing-data assumptions acknowledged? List concrete "
            "objections, mark each material or not, and give a one-line verdict. Do not rubber-stamp."
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Orchestrator system prompt and options.                                     #
# --------------------------------------------------------------------------- #

ORCHESTRATOR_SYSTEM = f"""\
You are PaedScale's orchestrator: a pediatric dose-extrapolation agent. You derive a
defensible pediatric STARTING dose from adult pharmacokinetics using allometric scaling
× organ maturation, generalising to any drug, and you show and cite every step.

HARD RULE: you never do arithmetic yourself. Every number — clearance, volume, maturation,
eGFR, the dose, the safety check, concordance — comes from a `mcp__paedscale_math__*` tool
call. If you are tempted to compute, call a tool instead.

{INTAKE_INSTRUCTIONS}
{COVARIATE_SPEC}

PIPELINE — be economical (this runs on a tight token/latency budget):
  1. INTAKE — parse covariates from the query.
  2. In ONE turn, spawn all three research subagents IN PARALLEL via the Task tool, each with a
     TERSE task string (drug + relevant covariates + exactly what to return):
       pathway-agent → full multi-pathway fm split (with citations)
       pk-agent      → adult PK + the exposure metric that drives effect
       safety-agent  → max-safe and min-effective mg/kg bounds, NTI/TDM status
  3. Do ONE quick guideline lookup yourself (pubmed_search or WebSearch) for any published
     pediatric/neonatal dose for the scenario, for the concordance check.
  4. Choose the dosing METHOD from the PK/PD driver: AUC/steady-state exposure → 'auc'; target
     steady-state conc → 'css'; concentration-dependent/peak → 'cmax'; trough-driven → 'trough';
     one-off fill-the-volume → 'loading'. Justify it briefly.
  5. Call `extrapolate_dose` with the pathways, method, method_params, and organ covariates.
  6. Call `check_safety_bounds` on the resulting mg/kg dose against the safety window.
  7. Call `find_concordance` if you found guideline dose(s).
  8. Delegate ONE review to critic-agent (Task). If an objection is material, fix it once, then proceed.
  9. GRADE the evidence high/moderate/low/very-low by how much real PK you found and its quality —
     sparse PK or many assumed defaults ⇒ low or very-low.
 10. Call `submit_recommendation` exactly once with the full structured result. Copy computed numbers
     verbatim from the tools. Write the rationale as a clear, cited clinical narrative.

CONTROL RULES:
  - The Task tool is SYNCHRONOUS: when a subagent returns, its findings are already in your context.
    Never say you are "waiting" and never end your turn to wait.
  - Do NOT end your turn until you have called `submit_recommendation`. If research is thin, proceed
    with explicit assumptions and a low evidence grade rather than stopping.
  - Keep it to one Task call per subagent. Do not re-run searches you already have.

Safety: decision support only, not a prescribing order. Surface uncertainty and NTI→TDM warnings;
never emit a false-confident number.
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
        permission_mode="bypassPermissions",
        setting_sources=[],  # isolate: ignore the user's global CLAUDE.md / settings / skills
        max_turns=MAX_TURNS,
    )


async def run_orchestrator(query: str, on_message=None):
    """Run the full pipeline for a query.

    Returns (payload | None, cost_usd | None, messages). `on_message`, if given,
    is awaited per streamed message (used by the SSE endpoint). A best-effort
    budget guard interrupts the run if the reported cost crosses PAEDSCALE_BUDGET_USD;
    the hard structural cap is `max_turns`.
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
                if not interrupted and tc >= BUDGET_USD and holder.get("payload") is None:
                    interrupted = True
                    await client.interrupt()
    return holder.get("payload"), cost_usd, messages
