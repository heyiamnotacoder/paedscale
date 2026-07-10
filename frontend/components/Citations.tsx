import type { Citation } from "@/lib/types";

export default function Citations({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="card">
      <div className="ctitle">Citations ({citations.length})</div>
      <ol className="citations">
        {citations.map((c, i) => {
          const label = c.title || c.identifier || c.url || "source";
          const meta = [c.authors, c.year, c.source, c.identifier].filter(Boolean).join(" · ");
          return (
            <li key={i}>
              <div className="cite-title">
                {c.url ? (
                  <a href={c.url} target="_blank" rel="noreferrer">{label}</a>
                ) : (
                  label
                )}
              </div>
              {meta && <div className="cite-meta">{meta}</div>}
              {c.claim_supported && <div className="cite-claim">Supports: {c.claim_supported}</div>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
