import type { Concordance } from "@/lib/types";

export default function ConcordanceBadge({ concordance }: { concordance: Concordance | null }) {
  if (!concordance || concordance.verdict === "no_guideline_available" || !concordance.matched) {
    return <span className="badge unmatched">No guideline — mechanistic estimate only</span>;
  }
  const { verdict, ratio, guideline_age_group } = concordance;
  const ratioText = ratio != null ? `${ratio.toFixed(2)}× guideline` : "";
  return (
    <span className={`badge ${verdict}`}>
      {verdict === "concordant" ? "Concordant" : "Divergent"}
      {guideline_age_group ? ` vs. ${guideline_age_group}` : ""} {ratioText && `(${ratioText})`}
    </span>
  );
}
