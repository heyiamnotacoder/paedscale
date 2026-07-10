import type { PathwayOut } from "@/lib/types";

export default function PathwayBreakdown({ pathways }: { pathways: PathwayOut[] }) {
  if (!pathways?.length) return null;
  return (
    <div className="card">
      <div className="ctitle">Elimination pathways — fm split × maturation</div>
      <div className="pathways">
        {pathways.map((p, i) => {
          const fmPct = Math.round((p.fm ?? 0) * 100);
          const mat = p.maturation_fraction != null ? Math.round(p.maturation_fraction * 100) : null;
          return (
            <div className="pathway-row" key={i}>
              <div className="pathway-head">
                <span className="pathway-name">{p.name}</span>
                <span className={`organ-tag organ-${p.organ}`}>{p.organ}</span>
                <span className="pathway-fm">{fmPct}% of clearance</span>
              </div>
              <div className="fm-bar">
                <div className="fm-fill" style={{ width: `${fmPct}%` }} />
              </div>
              {mat != null && (
                <div className="pathway-mat">
                  matured to {mat}% of adult activity
                  {p.tm50_weeks ? ` · TM50 ${p.tm50_weeks} wk, Hill ${p.hill}` : ""}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
