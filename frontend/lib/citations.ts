import type { Citation } from "./types";

/** Only allow http(s) links so javascript: / other schemes cannot reach an href. */
export function safeHttpUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

/** Short Perplexity-style label for an inline chip. */
export function citeLabel(c: Citation): string {
  const href = safeHttpUrl(c.url);
  if (href) {
    try {
      let host = new URL(href).hostname.replace(/^www\./, "");
      host = host
        .replace(/\.com$/, "")
        .replace(/\.org$/, "")
        .replace(/\.gov$/, "")
        .replace(/\.edu$/, "")
        .replace(/\.net$/, "")
        .replace(/\.io$/, "");
      const parts = host.split(".").filter(Boolean);
      if (parts.length > 1) {
        const last = parts[parts.length - 1];
        if (last === "nih" || last === "pubmed" || last.length <= 12) return last;
      }
      if (host.length <= 18) return host;
      return host.slice(0, 16);
    } catch {
      /* fall through */
    }
  }
  const src = (c.source || "").trim().toLowerCase();
  if (src) {
    const token = src.split(/[\s,/|]+/)[0] ?? src;
    return token.slice(0, 16);
  }
  return "source";
}

const STOP = new Set([
  "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "is", "are",
  "was", "were", "be", "as", "at", "from", "that", "this", "it", "its", "into", "via",
]);

function tokens(s: string): Set<string> {
  return new Set(
    s
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, " ")
      .split(/\s+/)
      .filter((t) => t.length > 2 && !STOP.has(t)),
  );
}

function overlapScore(a: Set<string>, b: Set<string>): number {
  let n = 0;
  for (const t of a) if (b.has(t)) n += 1;
  return n;
}

/** Split prose into sentences while keeping trailing punctuation. */
export function splitSentences(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const parts = trimmed.split(/(?<=[.!?])\s+(?=[A-Z0-9“"(])/);
  return parts.map((p) => p.trim()).filter(Boolean);
}

export interface SentenceCites {
  text: string;
  citations: Citation[];
}

/**
 * Attach citations to sentences by simple token overlap with claim_supported.
 * Unmatched citations are returned for the caller to place (next paragraph or trailing).
 */
export function assignCitationsToSentences(
  text: string,
  citations: Citation[],
): { sentences: SentenceCites[]; unmatched: Citation[] } {
  const sentences = splitSentences(text).map((s) => ({ text: s, citations: [] as Citation[] }));
  if (!sentences.length) {
    return { sentences: [], unmatched: [...citations] };
  }

  const sentenceTokens = sentences.map((s) => tokens(s.text));
  const unmatched: Citation[] = [];

  for (const c of citations) {
    const claim = (c.claim_supported || "").trim();
    if (!claim) {
      unmatched.push(c);
      continue;
    }
    const ct = tokens(claim);
    if (ct.size === 0) {
      unmatched.push(c);
      continue;
    }
    let best = -1;
    let bestScore = 0;
    sentenceTokens.forEach((st, si) => {
      const score = overlapScore(ct, st);
      if (score > bestScore) {
        bestScore = score;
        best = si;
      }
    });
    if (best >= 0 && bestScore >= 1) {
      sentences[best].citations.push(c);
    } else {
      unmatched.push(c);
    }
  }

  return { sentences, unmatched };
}

/** Assign across full text; force-show chips if nothing matched. */
export function buildCitedBlocks(
  text: string,
  citations: Citation[],
): SentenceCites[][] {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  if (!paragraphs.length) return [];

  let remaining = [...citations];
  const blocks: SentenceCites[][] = [];

  for (const para of paragraphs) {
    const { sentences, unmatched } = assignCitationsToSentences(para, remaining);
    blocks.push(sentences);
    remaining = unmatched;
  }

  // Pin leftovers to the last sentence so chips always appear when sources exist.
  if (remaining.length && blocks.length) {
    const lastBlock = blocks[blocks.length - 1];
    if (lastBlock.length) {
      lastBlock[lastBlock.length - 1].citations.push(...remaining);
    } else {
      // empty block edge case
      lastBlock.push({ text: "", citations: remaining });
    }
  } else if (citations.length && blocks.every((b) => b.every((s) => !s.citations.length))) {
    // No claim_supported matches at all — put all on first sentence
    if (blocks[0]?.[0]) {
      blocks[0][0].citations = [...citations];
    }
  }

  return blocks;
}
