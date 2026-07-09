import type { Rationale } from "@/lib/types";

export default function RationaleTrace({ rationale }: { rationale: Rationale }) {
  return (
    <div className="card">
      <div className="ctitle">Rationale — full auditable derivation</div>
      <p className="rationale-text">{rationale.rationale}</p>

      {rationale.assumptions.length > 0 && (
        <>
          <div className="ctitle" style={{ marginTop: 18 }}>
            Assumptions
          </div>
          <ul className="clean">
            {rationale.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </>
      )}

      {rationale.uncertainty_flags.length > 0 && (
        <>
          <div className="ctitle" style={{ marginTop: 18 }}>
            Uncertainty flags
          </div>
          <ul className="clean">
            {rationale.uncertainty_flags.map((f, i) => (
              <li className="flag" key={i}>
                {f}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
