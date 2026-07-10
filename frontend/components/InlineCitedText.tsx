"use client";

import type { Citation } from "@/lib/types";
import { buildCitedBlocks, citeLabel, safeHttpUrl } from "@/lib/citations";

function CiteChip({ citation, extra }: { citation: Citation; extra?: number }) {
  const href = safeHttpUrl(citation.url);
  const label = citeLabel(citation);
  const title = [citation.title, citation.source, citation.claim_supported].filter(Boolean).join(" — ");

  const inner = (
    <>
      {label}
      {extra != null && extra > 0 && <span className="cite-plus">+{extra}</span>}
    </>
  );

  if (href) {
    return (
      <a className="cite-chip" href={href} target="_blank" rel="noreferrer" title={title}>
        {inner}
      </a>
    );
  }

  return (
    <span className="cite-chip" title={title}>
      {inner}
    </span>
  );
}

function SentenceWithCites({ text, citations }: { text: string; citations: Citation[] }) {
  if (!text && !citations.length) return null;
  if (!citations.length) {
    return <>{text} </>;
  }

  const primary = citations[0];
  const rest = citations.slice(1);

  return (
    <>
      {text}
      <span className="cite-chip-group">
        <CiteChip citation={primary} extra={rest.length > 0 ? rest.length : undefined} />
        {rest.length === 1 && <CiteChip citation={rest[0]} />}
      </span>{" "}
    </>
  );
}

export default function InlineCitedText({
  text,
  citations,
}: {
  text: string;
  citations: Citation[];
}) {
  if (!text?.trim()) return null;

  if (!citations?.length) {
    return <div className="rationale-text">{text}</div>;
  }

  const blocks = buildCitedBlocks(text, citations);

  return (
    <div className="rationale-text rationale-cited">
      {blocks.map((sentences, pi) => (
        <p key={pi}>
          {sentences.map((s, si) => (
            <SentenceWithCites key={si} text={s.text} citations={s.citations} />
          ))}
        </p>
      ))}
    </div>
  );
}
