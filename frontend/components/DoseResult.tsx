import type { ExtrapolationResponse } from "@/lib/types";
import ConcordanceBadge from "./ConcordanceBadge";
import EvidenceGradeBadge from "./EvidenceGrade";
import MaturationChart from "./MaturationChart";
import PathwayBreakdown from "./PathwayBreakdown";
import SafetyBoundsBar from "./SafetyBounds";
import Citations from "./Citations";
import CritiquePanel from "./CritiquePanel";
import Disclaimer from "./Disclaimer";
import InlineCitedText from "./InlineCitedText";

function fmtNum(n: number | null | undefined, digits = 2): string {
  return n == null ? "—" : n.toFixed(digits);
}

export default function DoseResult({ result }: { result: ExtrapolationResponse }) {
  const { dose_recommendation: rec, covariates: cov, pathways, concordance, evidence_grade } = result;
  const cov_defaults = cov?.assumed_defaults ?? [];
  const citations = result.citations ?? [];

  return (
    <div>
      <div className="card">
        <div className="result-header">
          <div>
            <div className="ctitle">{result.drug_name || "Recommendation"} · starting dose</div>
            <div className="dose-mg">
              {fmtNum(rec.dose_mg)} mg{" "}
              <span className="dose-sub">
                ({fmtNum(rec.dose_mg_per_kg, 3)} mg/kg
                {rec.interval_h ? ` every ${rec.interval_h}h` : ""})
              </span>
            </div>
            {rec.method && (
              <div className="method-line">
                Method: <b>{rec.method}</b>
                {rec.matched_metric ? ` — matches ${rec.matched_metric}` : ""}
              </div>
            )}
            {result.source_of_dose && (
              <div className="method-line" style={{ marginTop: 4 }}>
                Source:{" "}
                <b>
                  {result.source_of_dose === "guideline"
                    ? "published guideline"
                    : result.source_of_dose === "partial_recovery"
                      ? "partial recovery (incomplete run)"
                      : "mechanistic extrapolation"}
                </b>
              </div>
            )}
          </div>
          <div className="header-badges">
            <ConcordanceBadge concordance={concordance} />
          </div>
        </div>

        {evidence_grade && <EvidenceGradeBadge grade={evidence_grade} />}

        {rec.method_rationale && (
          <p className="rationale-text" style={{ marginTop: 12 }}>
            {rec.method_rationale}
          </p>
        )}

        <table className="facts">
          <tbody>
            <tr>
              <td>Postmenstrual age</td>
              <td>{cov?.pma_weeks != null ? `${cov.pma_weeks} weeks` : "—"}</td>
            </tr>
            <tr>
              <td>Weight</td>
              <td>{cov?.weight_kg != null ? `${cov.weight_kg} kg` : "—"}</td>
            </tr>
            <tr>
              <td>Maturation applied</td>
              <td>
                {rec.maturation_fraction != null
                  ? `${(rec.maturation_fraction * 100).toFixed(1)}% of adult clearance capacity`
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>Child clearance / volume</td>
              <td>
                {fmtNum(rec.child_clearance_l_per_h)} L/h · {fmtNum(rec.child_volume_l)} L
              </td>
            </tr>
            {cov?.child_pugh_score != null && (
              <tr>
                <td>Child-Pugh</td>
                <td>{cov.child_pugh_score}</td>
              </tr>
            )}
            {cov?.egfr_ml_min_1_73 != null && (
              <tr>
                <td>eGFR</td>
                <td>{fmtNum(cov.egfr_ml_min_1_73)} mL/min/1.73m²</td>
              </tr>
            )}
          </tbody>
        </table>

        {cov_defaults.length > 0 && (
          <div className="assumed">
            <span className="assumed-h">Assumed defaults (no value given):</span> {cov_defaults.join(", ")}
          </div>
        )}

        {result.safety_flags?.length > 0 && (
          <ul className="clean" style={{ marginTop: 12 }}>
            {result.safety_flags.map((f, i) => (
              <li className="flag" key={i}>
                {f}
              </li>
            ))}
          </ul>
        )}

        <Disclaimer disclaimer={result.disclaimer} ntiWarning="" />
        {result.cost_usd != null && (
          <div className="cost-note">run cost ${result.cost_usd.toFixed(3)}</div>
        )}
      </div>

      <SafetyBoundsBar dose={rec} />
      <PathwayBreakdown pathways={pathways} />

      {pathways?.some((p) => p.tm50_weeks != null) && (
        <div className="card">
          <div className="ctitle">Maturation curves</div>
          <MaturationChart pathways={pathways} pmaWeeks={cov?.pma_weeks ?? 40} />
        </div>
      )}

      {result.rationale && (
        <div className="card">
          <div className="ctitle">Rationale — full auditable derivation</div>
          <InlineCitedText text={result.rationale} citations={citations} />
        </div>
      )}

      <CritiquePanel critique={result.critique} />
      <Citations citations={citations} />
    </div>
  );
}
