"""FastAPI app for PaedScale — generalizable multi-agent dose extrapolation.

POST /extrapolate takes a free-text clinical query, runs the Opus-4.8
orchestrator + specialist subagents (which research the literature and compute
every number through the deterministic paedscale_math tools), and returns the
assembled, cited, self-critiqued recommendation.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent.orchestrator import run_orchestrator
from app.schemas import ExtrapolationResponse, QueryRequest

DISCLAIMER = (
    "Decision support only, not an autonomous prescribing order. This is a defensible "
    "starting estimate for a qualified clinician to review. Narrow-therapeutic-index "
    "drugs must be confirmed with therapeutic drug monitoring."
)

app = FastAPI(title="PaedScale", version="0.2.0")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


def _to_response(query: str, payload: dict | None, cost_usd: float | None) -> ExtrapolationResponse:
    if not payload:
        raise HTTPException(
            status_code=502,
            detail="The agent did not produce a structured recommendation. Please retry.",
        )
    data = {**payload, "query": query, "disclaimer": DISCLAIMER, "cost_usd": cost_usd}
    try:
        return ExtrapolationResponse.model_validate(data)
    except Exception as exc:  # lenient schema, but guard against a malformed payload
        raise HTTPException(status_code=502, detail=f"Malformed recommendation: {exc}") from exc


@app.post("/extrapolate", response_model=ExtrapolationResponse)
async def extrapolate_case(request: QueryRequest) -> ExtrapolationResponse:
    try:
        payload, cost_usd, _messages = await run_orchestrator(request.query)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_response(request.query, payload, cost_usd)
