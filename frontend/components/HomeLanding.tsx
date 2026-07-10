"use client";

import QueryComposer from "./QueryComposer";

interface Props {
  query: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onFocusComposer: () => void;
  onTryExample: () => void;
  running?: boolean;
}

export default function HomeLanding({
  query,
  onChange,
  onSubmit,
  onFocusComposer,
  onTryExample,
  running,
}: Props) {
  return (
    <div className="landing">
      <h1 className="landing-wordmark">paedscale</h1>

      <QueryComposer
        value={query}
        onChange={onChange}
        onSubmit={onSubmit}
        disabled={running}
        autoFocus
        placeholder="Ask anything…"
      />

      <div className="landing-cards">
        <button type="button" className="mode-card" onClick={onFocusComposer}>
          <div className="mode-card-title">
            <span>⌕</span> Ask a dose question
          </div>
          <p className="mode-card-desc">
            Get a cited starting dose from literature, allometry, and organ maturation.
          </p>
        </button>
        <button type="button" className="mode-card alt" onClick={onTryExample}>
          <div className="mode-card-title">
            <span>◈</span> Try an example
            <span className="badge-new">demo</span>
          </div>
          <p className="mode-card-desc">
            Run a sample neonate or infant scenario and watch the agents reason live.
          </p>
        </button>
      </div>
    </div>
  );
}
