import type { DoseOut } from "@/lib/types";

export default function SafetyBoundsBar({ dose }: { dose: DoseOut }) {
  const sb = dose.safety_bounds;
  const min = sb.min_effective_mg_per_kg ?? null;
  const max = sb.max_safe_mg_per_kg ?? null;
  const rec = dose.dose_mg_per_kg ?? null;
  if (min == null && max == null) return null;

  const lo = min != null ? min * 0.6 : 0;
  const hi = max != null ? max * 1.15 : (rec ?? 1) * 1.5;
  const span = Math.max(hi - lo, 1e-6);
  const pos = (v: number) => Math.min(100, Math.max(0, ((v - lo) / span) * 100));

  return (
    <div className="card">
      <div className="ctitle">Safety window — mg/kg</div>
      <div className="bounds-track">
        {min != null && max != null && (
          <div className="bounds-safe" style={{ left: `${pos(min)}%`, width: `${pos(max) - pos(min)}%` }} />
        )}
        {min != null && <div className="bounds-edge" style={{ left: `${pos(min)}%` }} />}
        {max != null && <div className="bounds-edge" style={{ left: `${pos(max)}%` }} />}
        {rec != null && (
          <div
            className={`bounds-rec ${sb.within ? "" : "out"}`}
            style={{ left: `${pos(rec)}%` }}
            title={`recommended ${rec} mg/kg`}
          />
        )}
      </div>
      <div className="bounds-labels">
        <span>{min != null ? `min effective ${min}` : "min —"}</span>
        <span className="bounds-rec-label">recommended {rec != null ? rec.toFixed(3) : "—"}</span>
        <span>{max != null ? `max safe ${max}` : "max —"}</span>
      </div>
      {sb.flag && <div className="disclaimer nti">⚠ {sb.flag}</div>}
    </div>
  );
}
