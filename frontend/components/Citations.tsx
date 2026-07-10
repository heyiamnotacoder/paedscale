import type { Citation } from "@/lib/types";
import { citeLabel, safeHttpUrl } from "@/lib/citations";

export default function Citations({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="card">
      <div className="ctitle">Sources ({citations.length})</div>
      <ol className="citations">
        {citations.map((c, i) => {
          const href = safeHttpUrl(c.url);
          const label = c.title || c.identifier || (href ?? "source");
          const meta = [c.authors, c.year, c.source, c.identifier].filter(Boolean).join(" · ");
          return (
            <li key={i}>
              <span className="cite-num">{i + 1}</span>
              <div className="cite-body">
                <div className="cite-title">
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer">
                      {label}
                    </a>
                  ) : (
                    label
                  )}
                </div>
                {meta && <div className="cite-meta">{meta}</div>}
                {c.claim_supported && <div className="cite-claim">Supports: {c.claim_supported}</div>}
                <span className="cite-source-pill">
                  <span className="cite-chip" style={{ cursor: "default" }}>
                    {citeLabel(c)}
                  </span>
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
