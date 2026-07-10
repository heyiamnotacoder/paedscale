"""FastAPI app for PaedScale.

The prefill drug set (midazolam / vancomycin / morphine) has been removed —
PaedScale is being rebuilt into a generalizable multi-agent system (free-text
query -> Opus-4.8 orchestrator + specialist subagents -> deterministic dose
solve -> cited, self-critiqued rationale).

Phase 0 ships the data removal and keeps the deterministic `pk/` engine and its
validation suite green. The generalized `/extrapolate` pipeline lands in Phase 2;
until then the endpoint returns 503 rather than a number it can no longer solve
without the curated reference dose.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import CaseRequest

DISCLAIMER = (
    "Decision support only, not an autonomous prescribing order. This is a defensible "
    "starting estimate for a qualified clinician to review. Narrow-therapeutic-index "
    "drugs must be confirmed with therapeutic drug monitoring."
)

app = FastAPI(title="PaedScale", version="0.2.0-dev")

# Comma-separated list of allowed frontend origins. Defaults to the local dev
# server; in production set ALLOWED_ORIGINS to the deployed frontend URL(s).
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


@app.post("/extrapolate")
def extrapolate_case(case: CaseRequest):
    # Transitional: the generalized multi-agent pipeline is under construction
    # (Phase 2). The old curated exposure-match path was removed with the prefill
    # drug set. Pydantic still validates the request shape before we reach here.
    raise HTTPException(
        status_code=503,
        detail=(
            "The generalized dose-extrapolation pipeline is under construction. "
            "PaedScale is being rebuilt into a multi-agent system; this endpoint "
            "will return in Phase 2."
        ),
    )
