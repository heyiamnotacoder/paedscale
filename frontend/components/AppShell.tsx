"use client";

import type { ReactNode } from "react";

export interface HistoryItem {
  id: string;
  query: string;
}

interface Props {
  children: ReactNode;
  history: HistoryItem[];
  activeHistoryId?: string | null;
  onNew: () => void;
  onSelectHistory: (item: HistoryItem) => void;
}

export default function AppShell({
  children,
  history,
  activeHistoryId,
  onNew,
  onSelectHistory,
}: Props) {
  return (
    <div className="app-shell">
      <aside className="sidebar-rail" aria-label="Navigation">
        <a className="sidebar-brand" href="/" onClick={(e) => { e.preventDefault(); onNew(); }}>
          <span className="sidebar-brand-mark">PS</span>
          <span className="sidebar-brand-name">PaedScale</span>
        </a>

        <button type="button" className="sidebar-new" onClick={onNew}>
          <span className="sidebar-new-plus">+</span>
          New
        </button>

        <nav className="sidebar-nav" aria-label="Primary">
          <button type="button" className="sidebar-nav-item active" onClick={onNew}>
            <span className="sidebar-nav-icon">◎</span>
            Dose query
          </button>
        </nav>

        <div className="sidebar-section">
          <div className="sidebar-section-label">History</div>
          <div className="sidebar-history">
            {history.length === 0 ? (
              <div className="sidebar-history-empty">No recent sessions</div>
            ) : (
              history.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={`sidebar-history-item${activeHistoryId === item.id ? " active" : ""}`}
                  title={item.query}
                  onClick={() => onSelectHistory(item)}
                >
                  {item.query}
                </button>
              ))
            )}
          </div>
        </div>

        <div className="sidebar-foot">
          Decision support only · not prescribing advice
        </div>
      </aside>

      <div className="shell-main">{children}</div>
    </div>
  );
}
