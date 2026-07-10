"""FastAPI app for PaedScale — generalizable pediatric dose extrapolation.

POST /extrapolate takes a free-text clinical query and runs an in-process Sonnet Messages-API agent
loop: deterministic openFDA drug-data fetch + a parallel guideline sub-agent feed the orchestrator,
which computes every number through the deterministic PK-maths tools, self-critiques, and returns the
assembled, cited recommendation. POST /report exports it as a PDF via the pdf Agent Skill.
"""

import asyncio
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.agent.orchestrator import run_orchestrator
from app.schemas import ExtrapolationResponse, QueryRequest, assemble_lenient_response

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
    # Coerce nested JSON-strings and fail-open on soft fields so a finished run
    # (with dose numbers) is never discarded over critique shape quirks.
    data = {**payload, "query": query, "disclaimer": DISCLAIMER, "cost_usd": cost_usd}
    try:
        return assemble_lenient_response(data)
    except Exception as exc:  # only if even the minimal repair path fails
        raise HTTPException(status_code=502, detail=f"Malformed recommendation: {exc}") from exc


@app.post("/extrapolate", response_model=ExtrapolationResponse)
async def extrapolate_case(request: QueryRequest) -> ExtrapolationResponse:
    try:
        payload, cost_usd, _messages = await run_orchestrator(
            request.query, overrides=request.overrides
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_response(request.query, payload, cost_usd)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/extrapolate/stream")
async def extrapolate_stream(request: QueryRequest):
    """Run the pipeline and stream reasoning-trace events (SSE), then the result.

    Streaming is the core UX mitigation for multi-agent runs — the client renders
    the trace live in the right sidebar instead of a spinner.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(ev: dict):
        await queue.put(("trace", ev))

    async def run():
        try:
            payload, cost_usd, _ = await run_orchestrator(
                request.query, on_event=on_event, overrides=request.overrides
            )
            if not payload:
                await queue.put(("error", {"detail": "The agent did not produce a recommendation."}))
            else:
                resp = _to_response(request.query, payload, cost_usd)
                await queue.put(("result", resp.model_dump()))
        except HTTPException as exc:
            await queue.put(("error", {"detail": exc.detail}))
        except Exception as exc:  # surface any run failure to the client, don't hang the stream
            await queue.put(("error", {"detail": str(exc)}))
        finally:
            await queue.put(("done", {}))

    async def gen():
        task = asyncio.create_task(run())
        try:
            while True:
                kind, data = await queue.get()
                yield _sse(kind, data)
                if kind == "done":
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/report")
async def report(recommendation: dict):
    """Export a recommendation as a PDF via the `pdf` Agent Skill (off the query hot path)."""
    from app.report import generate_report_pdf

    try:
        data, filename = await generate_report_pdf(recommendation)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Report generation failed: {exc}") from exc
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
