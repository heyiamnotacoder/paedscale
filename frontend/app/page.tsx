"use client";

import { useRef, useState } from "react";
import { extrapolateStream } from "@/lib/api";
import type { ExtrapolationResponse, TraceEvent } from "@/lib/types";
import DoseResult from "@/components/DoseResult";
import ReasoningSidebar from "@/components/ReasoningSidebar";

const EXAMPLES = [
  "What should be the starting dose of paracetamol in a 2-day-old neonate weighing 3.1 kg with hepatic impairment (Child-Pugh 7)?",
  "Vancomycin starting dose for a 6-month-old, 7 kg, serum creatinine 0.4 mg/dL, height 65 cm?",
  "Gentamicin dose for a preterm neonate, 32 weeks gestation, 10 days old, 1.6 kg?",
];

export default function Home() {
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [result, setResult] = useState<ExtrapolationResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function run(q: string) {
    if (!q.trim() || running) return;
    setEvents([]);
    setResult(null);
    setError(null);
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    await extrapolateStream(
      q.trim(),
      {
        onTrace: (ev) => setEvents((prev) => [...prev, ev]),
        onResult: (res) => setResult(res),
        onError: (detail) => setError(detail),
        onDone: () => setRunning(false),
      },
      ctrl.signal,
    );
  }

  const started = running || events.length > 0 || result !== null || error !== null;

  return (
    <div className="wrap">
      <header className="hero">
        <div className="eyebrow">Dev Track · Built with Claude: Life Sciences</div>
        <h1>
          Dosing children where the <em>guidelines run out</em>.
        </h1>
        <p className="lede">
          Ask in plain language. A multi-agent system researches the literature, decomposes the drug&apos;s
          elimination, scales adult PK by allometry × organ maturation, self-critiques, and returns a cited,
          auditable starting dose — watch it reason on the right.
        </p>
      </header>

      <form
        className="card querybox"
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
      >
        <label htmlFor="q">Clinical query</label>
        <textarea
          id="q"
          rows={3}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. starting dose of paracetamol in a 2-day-old neonate, 3.1 kg, Child-Pugh 7"
          disabled={running}
        />
        <div className="examples">
          {EXAMPLES.map((ex, i) => (
            <button
              type="button"
              key={i}
              className="example-chip"
              disabled={running}
              onClick={() => {
                setQuery(ex);
                run(ex);
              }}
            >
              {ex.length > 60 ? ex.slice(0, 58) + "…" : ex}
            </button>
          ))}
        </div>
        <button className="submit" type="submit" disabled={running || !query.trim()}>
          {running ? "Agents working…" : "Extrapolate dose"}
        </button>
      </form>

      {started && (
        <div className="result-grid">
          <main className="result-main">
            {error && <div className="error-box">{error}</div>}
            {result ? (
              <DoseResult result={result} />
            ) : running ? (
              <div className="card empty-state">
                Agents are researching the literature and computing the dose. The full recommendation appears
                here when they finish (~20–40s) — the live reasoning is on the right.
              </div>
            ) : (
              !error && <div className="card empty-state">No recommendation was produced.</div>
            )}
          </main>
          <ReasoningSidebar events={events} running={running} />
        </div>
      )}
    </div>
  );
}
