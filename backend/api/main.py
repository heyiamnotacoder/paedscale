"""
PaedScale — FastAPI backend.

Serves the lightweight frontend and a /calculate endpoint that runs a case through the
Claude orchestration layer. Also exposes /pk for the deterministic engine alone (no key).

Run:  uvicorn api.main:app --reload --port 8000   (from the backend/ directory)
Then open http://localhost:8000
"""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()  # pulls ANTHROPIC_API_KEY from backend/.env

from agents.agent import ORCHESTRATOR_MODEL, run_case  # noqa: E402  (after load_dotenv)
from engine.child_pugh import hi_gate_error  # noqa: E402
from engine.pk_engine import (  # noqa: E402
    compute_pediatric_dose,
    renal_function_fraction_from_labs,
    result_to_dict,
)

# Chat follow-ups are a single cheap call; default to the orchestrator model so it always works,
# override with CHAT_MODEL (e.g. claude-sonnet-5) to make them cheaper/faster.
CHAT_MODEL = os.environ.get("CHAT_MODEL", ORCHESTRATOR_MODEL)

app = FastAPI(title="PaedScale", version="0.2-mvp")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

HERE = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(HERE, "..", "..", "frontend")
FRONTEND = os.path.join(FRONTEND_DIR, "index.html")
EVAL_PK = os.path.join(HERE, "..", "eval_data", "drug_pk.json")

# Browser-tab / home-screen marks. Keep this allow-list tight — these are
# the only files besides index.html that the product path serves from frontend/.
_FRONTEND_ASSETS = {
    "favicon.ico": "image/x-icon",
    "favicon.svg": "image/svg+xml",
    "favicon-32.png": "image/png",
    "apple-touch-icon.png": "image/png",
}


def _oracle_pk() -> dict:
    """Reviewed adult-PK oracle — DEV/EVAL ONLY. The product path (/calculate) never reads it;
    it exists so the no-key /pk engine check can run against known drugs."""
    with open(EVAL_PK) as f:
        return json.load(f)["drugs"]


def _renal_fraction(case: "Case") -> float:
    """Renal organ-function modifier from labs (bedside Schwartz). No labs / no impairment
    → 1.0 (no silent reduction). Mirrors agent._normalize_case for the /calculate path."""
    if not case.renal_impairment:
        return 1.0
    frac = renal_function_fraction_from_labs(case.height_cm, case.serum_creatinine_mg_dl)
    return frac if frac is not None else 1.0


def _enforce_hi_gate(case: "Case") -> None:
    """Same incomplete-HI rejection as the form. Age does not switch facades."""
    err = hi_gate_error(case.model_dump())
    if err:
        raise HTTPException(400, err)


class Case(BaseModel):
    drug: str
    indication: str | None = None
    age_years: float = Field(..., ge=0, description="Postnatal age in years (0 = neonate day 0)")
    weight_kg: float = Field(..., gt=0, description="Body weight in kg; must be positive")
    pma_weeks: float | None = None
    gestational_age_weeks: float | None = None
    postnatal_age_weeks: float | None = None
    renal_impairment: bool = False
    hepatic_impairment: bool = False
    serum_creatinine_mg_dl: float | None = None  # for bedside-Schwartz eGFR when renal-impaired
    height_cm: float | None = None               # required alongside creatinine for Schwartz
    child_pugh: str | None = None                # "A" | "B" | "C" — noted only (drug-specific)
    # Child-Pugh calculate-from-labs mode (optional; server computes class when all three labs set)
    bilirubin_mg_dl: float | None = None
    albumin_g_dl: float | None = None
    inr: float | None = None
    ascites: str | None = None                   # none | mild | moderate
    encephalopathy: str | None = None            # none | 1-2 | 3-4
    # Safety context for contraindication hard-stop / avoid-list
    allergies: list[str] | None = None
    conditions: list[str] | None = None
    route: str = "iv"  # "iv" | "oral" — governs the oral-bioavailability correction
    # Optional vial / oral-liquid strength the clinician actually has. Used only
    # to convert the rounded dose into mL. Never invents a concentration.
    formulation_mg_per_ml: float | None = Field(
        default=None, gt=0, description="Optional formulation strength in mg/mL"
    )
    # Facade: age must not switch this. adult_hi implies hepatic impairment on.
    calculator_mode: Literal["pediatric", "adult_hi"] = "pediatric"


@app.get("/")
def index():
    return FileResponse(FRONTEND)


def _serve_frontend_asset(name: str) -> FileResponse:
    media = _FRONTEND_ASSETS.get(name)
    if not media:
        raise HTTPException(404)
    path = os.path.abspath(os.path.join(FRONTEND_DIR, name))
    root = os.path.abspath(FRONTEND_DIR) + os.sep
    if not path.startswith(root) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path, media_type=media)


@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
def favicon_ico():
    return _serve_frontend_asset("favicon.ico")


@app.api_route("/favicon.svg", methods=["GET", "HEAD"])
def favicon_svg():
    return _serve_frontend_asset("favicon.svg")


@app.api_route("/favicon-32.png", methods=["GET", "HEAD"])
def favicon_png():
    return _serve_frontend_asset("favicon-32.png")


@app.api_route("/apple-touch-icon.png", methods=["GET", "HEAD"])
def apple_touch_icon():
    return _serve_frontend_asset("apple-touch-icon.png")


@app.get("/health")
def health():
    from engine.pk_cache import CACHE as PK_CACHE
    return {"ok": True, "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "model": os.environ.get("ORCHESTRATOR_MODEL", "claude-opus-4-8"),
            "eval_drugs": sorted(_oracle_pk()),  # scored drug set (oracle), not a runtime source
            "pk_cache": PK_CACHE.stats()}


def _requires_anthropic(case: Case) -> bool:
    """Adult HI is a deterministic openFDA label lookup — no orchestrator."""
    return (case.calculator_mode or "pediatric") != "adult_hi"


@app.post("/calculate")
def calculate(case: Case):
    """Full agentic pipeline — needs ANTHROPIC_API_KEY except Adult HI lookup."""
    _enforce_hi_gate(case)
    if _requires_anthropic(case) and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "ANTHROPIC_API_KEY not set. Add it to backend/.env")
    result = run_case(case.model_dump())
    if result.get("recommendation") is None:
        raise HTTPException(502, result.get("error", "no recommendation produced"))
    return result


@app.post("/calculate/stream")
def calculate_stream(case: Case):
    """Same pipeline as /calculate, but streams the agent's reasoning as it happens.

    Server-Sent Events: `step` events carry one-line reasoning/tool traces as they occur,
    then a single `done` event carries the full result JSON (or an `error` event on failure).
    The frontend reads this to drive the live loading screen.
    """
    _enforce_hi_gate(case)
    if _requires_anthropic(case) and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "ANTHROPIC_API_KEY not set. Add it to backend/.env")

    q: queue.Queue = queue.Queue()
    _END = object()

    def on_step(text: str) -> None:
        q.put(("step", text))

    def worker() -> None:
        try:
            result = run_case(case.model_dump(), on_step=on_step)
            if result.get("recommendation") is None:
                q.put(("error", result.get("error", "no recommendation produced")))
            else:
                q.put(("done", result))
        except Exception as e:  # surface any pipeline failure to the client stream
            q.put(("error", str(e)))
        finally:
            q.put((_END, None))

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            kind, payload = q.get()
            if kind is _END:
                break
            if kind == "step":
                yield f"event: step\ndata: {json.dumps({'text': payload})}\n\n"
            elif kind == "done":
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
            elif kind == "error":
                yield f"event: error\ndata: {json.dumps({'detail': payload})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    case: dict | None = None
    recommendation: dict | None = None
    history: list[ChatTurn] = []


CHAT_SYSTEM = """You are PaedScale, answering a clinician's follow-up about a pediatric
dose recommendation you already produced. You are decision support, NOT a prescriber.

Ground every answer in the provided recommendation JSON (grade, mechanism, concordance,
flags, citations, assumptions, uncertainty) and the case. Be concise and clinically precise.
If the question asks for something not supported by the provided data, say so plainly rather
than inventing PK values — cite-or-abstain still holds. Never restate a dose as an order.
Use short paragraphs or tight bullet lists. Plain text / light markdown only."""


@app.post("/chat")
def chat(req: ChatRequest):
    """Follow-up Q&A grounded in an already-produced recommendation. One cheap call, no tools."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "ANTHROPIC_API_KEY not set. Add it to backend/.env")
    from anthropic import Anthropic

    context = json.dumps({"case": req.case, "recommendation": req.recommendation}, default=str)
    messages = [{
        "role": "user",
        "content": (
            "Here is the case and the recommendation you produced. Use it to answer my "
            f"follow-up questions.\n\n{context}"
        ),
    }, {
        "role": "assistant",
        "content": "Understood — I have the recommendation in front of me. What would you like to know?",
    }]
    for turn in req.history:
        if turn.role in ("user", "assistant") and turn.content.strip():
            messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": req.question})

    client = Anthropic()
    resp = client.messages.create(
        model=CHAT_MODEL, max_tokens=900, system=CHAT_SYSTEM, messages=messages,
    )
    answer = "".join(b.text for b in resp.content if b.type == "text").strip()
    return {"answer": answer,
            "usage": {"model": CHAT_MODEL,
                      "input_tokens": resp.usage.input_tokens,
                      "output_tokens": resp.usage.output_tokens}}


@app.post("/pk")
def pk(case: Case):
    """DEV/EVAL ONLY — deterministic engine on the reviewed PK oracle, no API key required.
    This is a bench check for the math; the PRODUCT path is /calculate (live retrieval)."""
    _enforce_hi_gate(case)
    oracle = _oracle_pk()
    seed = oracle.get(case.drug.strip().lower())
    if not seed:
        raise HTTPException(404, f"'{case.drug}' not in eval oracle {sorted(oracle)}")
    r = compute_pediatric_dose(
        drug=case.drug, weight_kg=case.weight_kg,
        cl_adult_l_h=seed["cl_adult_l_h"], vd_adult_l=seed["vd_adult_l"],
        fm=seed["fm"], target_metric=seed["target_metric"],
        age_years=case.age_years, pma_weeks=case.pma_weeks,
        gestational_age_weeks=case.gestational_age_weeks,
        postnatal_age_weeks=case.postnatal_age_weeks,
        adult_dose_mg_per_day=seed.get("typical_adult_dose_mg_per_day"),
        renal_function_fraction=_renal_fraction(case),
        hepatic_function_fraction=1.0,  # drug-specific; no automatic hepatic reduction
        route=case.route,
        oral_bioavailability=seed.get("oral_bioavailability", 1.0),
        toxic_dose_mg_per_kg_per_day=seed.get("toxic_dose_mg_per_kg_per_day"),
        effective_dose_mg_per_kg_per_day=seed.get("effective_dose_mg_per_kg_per_day"),
    )
    return result_to_dict(r)
