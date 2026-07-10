import type { Critique } from "@/lib/types";

export default function CritiquePanel({ critique }: { critique: Critique }) {
  const has =
    critique && (critique.objections?.length || critique.resolution || critique.residual_risks?.length);
  if (!has) return null;
  return (
    <div className="card">
      <div className="ctitle">Self-critique</div>
      {critique.objections?.length > 0 && (
        <>
          <div className="mini-h">Objections raised</div>
          <ul className="clean">
            {critique.objections.map((o, i) => (
              <li className="flag" key={i}>{o}</li>
            ))}
          </ul>
        </>
      )}
      {critique.resolution && (
        <>
          <div className="mini-h">Resolution</div>
          <p className="rationale-text">{critique.resolution}</p>
        </>
      )}
      {critique.residual_risks?.length > 0 && (
        <>
          <div className="mini-h">Residual risks</div>
          <ul className="clean">
            {critique.residual_risks.map((r, i) => (
              <li className="flag" key={i}>{r}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
