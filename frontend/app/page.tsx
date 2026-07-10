"use client";

import { useCallback, useRef, useState } from "react";
import { extrapolateStream } from "@/lib/api";
import type { ExtrapolationResponse, TraceEvent } from "@/lib/types";
import AppShell, { type HistoryItem } from "@/components/AppShell";
import HomeLanding from "@/components/HomeLanding";
import QueryComposer from "@/components/QueryComposer";
import ReasoningTrace from "@/components/ReasoningTrace";
import DoseResult from "@/components/DoseResult";

const EXAMPLES = [
  "What should be the starting dose of paracetamol in a 2-day-old neonate weighing 3.1 kg with hepatic impairment (Child-Pugh 7)?",
  "Vancomycin starting dose for a 6-month-old, 7 kg, serum creatinine 0.4 mg/dL, height 65 cm?",
  "Gentamicin dose for a preterm neonate, 32 weeks gestation, 10 days old, 1.6 kg?",
];

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [result, setResult] = useState<ExtrapolationResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Cache results per history id for re-open (same session)
  const cacheRef = useRef<
    Map<string, { events: TraceEvent[]; result: ExtrapolationResponse | null; error: string | null }>
  >(new Map());

  const started = running || events.length > 0 || result !== null || error !== null;

  const run = useCallback(async (q: string) => {
    if (!q.trim() || running) return;
    abortRef.current?.abort();

    const id = makeId();
    const trimmed = q.trim();

    setActiveHistoryId(id);
    setActiveQuery(trimmed);
    setQuery("");
    setEvents([]);
    setResult(null);
    setError(null);
    setRunning(true);
    setHistory((prev) => [{ id, query: trimmed }, ...prev.filter((h) => h.query !== trimmed)].slice(0, 20));

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const collected: TraceEvent[] = [];
    let finalResult: ExtrapolationResponse | null = null;
    let finalError: string | null = null;

    await extrapolateStream(
      trimmed,
      {
        onTrace: (ev) => {
          collected.push(ev);
          setEvents((prev) => [...prev, ev]);
        },
        onResult: (res) => {
          finalResult = res;
          setResult(res);
        },
        onError: (detail) => {
          finalError = detail;
          setError(detail);
        },
        onDone: () => {
          setRunning(false);
          cacheRef.current.set(id, {
            events: [...collected],
            result: finalResult,
            error: finalError,
          });
        },
      },
      ctrl.signal,
    );
  }, [running]);

  function handleNew() {
    abortRef.current?.abort();
    setRunning(false);
    setEvents([]);
    setResult(null);
    setError(null);
    setActiveQuery("");
    setQuery("");
    setActiveHistoryId(null);
  }

  function handleSelectHistory(item: HistoryItem) {
    const cached = cacheRef.current.get(item.id);
    setActiveHistoryId(item.id);
    setActiveQuery(item.query);
    setQuery("");
    if (cached) {
      setEvents(cached.events);
      setResult(cached.result);
      setError(cached.error);
      setRunning(false);
    } else {
      // Re-run if we don't have a cache entry (e.g. mid-flight abort)
      void run(item.query);
    }
  }

  function handleTryExample() {
    const ex = EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)];
    void run(ex);
  }

  function handleFocusComposer() {
    const el = document.querySelector<HTMLTextAreaElement>(".landing .composer-input");
    el?.focus();
  }

  return (
    <AppShell
      history={history}
      activeHistoryId={activeHistoryId}
      onNew={handleNew}
      onSelectHistory={handleSelectHistory}
    >
      {!started ? (
        <HomeLanding
          query={query}
          onChange={setQuery}
          onSubmit={() => void run(query)}
          onFocusComposer={handleFocusComposer}
          onTryExample={handleTryExample}
          running={running}
        />
      ) : (
        <div className="answer-view">
          {activeQuery && (
            <div className="answer-query-row">
              <div className="answer-query" title={activeQuery}>
                <span className="answer-query-text">{activeQuery}</span>
              </div>
            </div>
          )}

          <div className="answer-body">
            <ReasoningTrace events={events} running={running} />

            {error && <div className="error-box">{error}</div>}

            {result ? (
              <DoseResult result={result} />
            ) : running ? (
              <div className="answer-loading">
                Agents are researching the literature and computing the dose. The recommendation
                appears here when they finish.
              </div>
            ) : (
              !error && <div className="answer-loading">No recommendation was produced.</div>
            )}

            <QueryComposer
              value={query}
              onChange={setQuery}
              onSubmit={() => void run(query)}
              disabled={running}
              compact
              placeholder="Ask a follow-up…"
            />
          </div>
        </div>
      )}
    </AppShell>
  );
}
