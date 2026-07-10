import type { EvidenceGrade } from "@/lib/types";

const GRADE_CLASS: Record<string, string> = {
  high: "grade-high",
  moderate: "grade-moderate",
  low: "grade-low",
  "very-low": "grade-verylow",
};

export default function EvidenceGradeBadge({ grade }: { grade: EvidenceGrade }) {
  const cls = GRADE_CLASS[grade.grade] ?? "grade-verylow";
  return (
    <div className="evidence">
      <span className={`grade-badge ${cls}`}>{(grade.grade || "very-low").replace("-", " ")} evidence</span>
      {grade.rationale && <p className="evidence-why">{grade.rationale}</p>}
    </div>
  );
}
