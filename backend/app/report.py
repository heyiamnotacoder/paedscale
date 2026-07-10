"""PDF dosing-report export via the Anthropic `pdf` Agent Skill.

Off the query hot path: the client calls POST /report with a recommendation payload and gets back a
downloadable PDF. Uses the pre-built `pdf` skill running in the code-execution container, so it earns
the Skills capability without adding any latency to /extrapolate.

Requires a live ANTHROPIC_API_KEY and the code-execution + skills betas; not exercised by the offline
test suite.
"""

import json
import os

import anthropic

REPORT_MODEL = os.environ.get("PAEDSCALE_REPORT_MODEL", "claude-sonnet-5")
_BETAS = ["code-execution-2025-08-25", "skills-2025-10-02"]

_PROMPT = """\
Produce a clean one-page clinical PDF titled "PaedScale — Pediatric Dose Recommendation" from the
JSON below. Include: drug + case covariates; the recommended dose (mg and mg/kg, interval, method);
source of dose (guideline / mechanistic); pathways and maturation; safety bounds and flags; evidence
grade; the critique with dose_grade; citations; and a footer disclaimer that this is decision support
only, not a prescribing order, and NTI drugs require TDM. Save it as paedscale_report.pdf.

JSON:
"""


def _find_pdf(resp) -> tuple[str | None, str | None]:
    """Scan code-execution results for a generated file id + name."""
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", "") != "bash_code_execution_tool_result":
            continue
        content = getattr(block, "content", None)
        for item in getattr(content, "content", []) or []:
            if getattr(item, "type", "") == "bash_code_execution_output":
                fid = getattr(item, "file_id", None)
                if fid:
                    return fid, None
    return None, None


async def generate_report_pdf(recommendation: dict) -> tuple[bytes, str]:
    """Return (pdf_bytes, filename). Raises RuntimeError if generation fails."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set.")
    client = anthropic.AsyncAnthropic()
    resp = await client.beta.messages.create(
        model=REPORT_MODEL,
        max_tokens=8000,
        betas=_BETAS,
        container={"skills": [{"type": "anthropic", "skill_id": "pdf", "version": "latest"}]},
        tools=[{"type": "code_execution_20260521", "name": "code_execution"}],
        messages=[{"role": "user", "content": _PROMPT + json.dumps(recommendation, default=str)}],
    )
    file_id, _ = _find_pdf(resp)
    if not file_id:
        raise RuntimeError("The pdf skill did not produce a file.")
    download = await client.beta.files.download(file_id, betas=["files-api-2025-04-14"])
    data = await download.aread() if hasattr(download, "aread") else download.read()
    return data, "paedscale_report.pdf"
