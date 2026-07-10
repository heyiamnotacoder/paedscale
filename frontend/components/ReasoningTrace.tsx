"use client";

import { useEffect, useRef, useState } from "react";
import type { TraceEvent } from "@/lib/types";

const AGENT_CLASS: Record<string, string> = {
  orchestrator: "ag-orch",
  "research-agent": "ag-path",
  "critic-agent": "ag-critic",
  "pathway-agent": "ag-path",
  "pk-agent": "ag-pk",
  "safety-agent": "ag-safety",
  local_agent: "ag-pk",
};

function icon(kind: TraceEvent["kind"]): string {
  if (kind === "tool") return "⚙";
  if (kind === "tool_result") return "↩";
  if (kind === "status") return "•";
  return "›";
}

function statusLine(events: TraceEvent[], running: boolean): string {
  if (!running && events.length === 0) return "Agent reasoning";
  if (running && events.length === 0) return "Starting agents…";

  const last = events[events.length - 1];
  const blob = `${last?.agent ?? ""} ${last?.tool ?? ""} ${last?.text ?? ""}`.toLowerCase();

  if (blob.includes("critic")) return "Critiquing recommendation…";
  if (
    blob.includes("extrapolate") ||
    blob.includes("maturation") ||
    blob.includes("allometr") ||
    blob.includes("safety") ||
    blob.includes("concordance") ||
    last?.agent === "local_agent"
  ) {
    return "Computing dose…";
  }
  if (
    blob.includes("pubmed") ||
    blob.includes("scholar") ||
    blob.includes("search") ||
    blob.includes("fetch") ||
    blob.includes("literature") ||
    blob.includes("web") ||
    last?.agent === "research-agent"
  ) {
    return "Researching literature…";
  }
  if (running) return "Working…";
  return events.length === 1 ? "1 step completed" : `${events.length} steps completed`;
}

export default function ReasoningTrace({
  events,
  running,
}: {
  events: TraceEvent[];
  running: boolean;
}) {
  const [open, setOpen] = useState(running);
  const endRef = useRef<HTMLDivElement>(null);
  const wasRunning = useRef(running);

  // Expand while streaming; collapse once the run finishes.
  useEffect(() => {
    if (running) setOpen(true);
    else if (wasRunning.current && !running) setOpen(false);
    wasRunning.current = running;
  }, [running]);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length, open]);

  if (!running && events.length === 0) return null;

  const label = statusLine(events, running);

  return (
    <div className="reasoning">
      <button
        type="button"
        className={`reasoning-toggle${running ? " live" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {running ? <span className="live-dot" aria-hidden /> : <span aria-hidden>🌐</span>}
        <span>{label}</span>
        <span className={`reasoning-chevron${open ? " open" : ""}`} aria-hidden>
          ›
        </span>
      </button>

      {open && (
        <div className="reasoning-panel" role="log" aria-live="polite">
          {events.length === 0 ? (
            <div className="trace-empty">Spinning up the agents…</div>
          ) : (
            events.map((e, i) => (
              <div className="trace-item" key={i}>
                <span className={`agent-chip ${AGENT_CLASS[e.agent] ?? "ag-orch"}`}>{e.agent}</span>
                <span className={`trace-text tk-${e.kind}`}>
                  <span className="trace-icon">{icon(e.kind)}</span> {e.text}
                </span>
              </div>
            ))
          )}
          <div ref={endRef} />
        </div>
      )}
    </div>
  );
}
