"use client";

import { useEffect, useRef } from "react";
import type { TraceEvent } from "@/lib/types";

const AGENT_CLASS: Record<string, string> = {
  orchestrator: "ag-orch",
  "research-agent": "ag-path",
  "critic-agent": "ag-critic",
  // legacy labels (older traces)
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

export default function ReasoningSidebar({ events, running }: { events: TraceEvent[]; running: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  return (
    <aside className="sidebar card">
      <div className="ctitle sidebar-title">
        Agent reasoning {running && <span className="live-dot" aria-label="running" />}
      </div>
      <div className="trace">
        {events.length === 0 && (
          <div className="trace-empty">
            {running ? "Spinning up the agents…" : "The agents' live reasoning will stream here."}
          </div>
        )}
        {events.map((e, i) => (
          <div className="trace-item" key={i}>
            <span className={`agent-chip ${AGENT_CLASS[e.agent] ?? "ag-orch"}`}>{e.agent}</span>
            <span className={`trace-text tk-${e.kind}`}>
              <span className="trace-icon">{icon(e.kind)}</span> {e.text}
            </span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </aside>
  );
}
