import type { Citation } from "@/lib/types";

// Citation URLs come from the LLM / literature search — untrusted. Only allow
// http(s) links so a `javascript:` (XSS) or other scheme can't reach an href.
function safeHttpUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

export default function Citations({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="card">
      <div className="ctitle">Citations ({citations.length})</div>
      <ol className="citations">
        {citations.map((c, i) => {
          const href = safeHttpUrl(c.url);
          const label = c.title || c.identifier || (href ?? "source");
          const meta = [c.authors, c.year, c.source, c.identifier].filter(Boolean).join(" · ");
          return (
            <li key={i}>
              <div className="cite-title">
                {href ? (
                  <a href={href} target="_blank" rel="noreferrer">{label}</a>
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
