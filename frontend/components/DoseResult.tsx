import type { ExtrapolationResponse } from "@/lib/types";
import ConcordanceBadge from "./ConcordanceBadge";
import MaturationChart from "./MaturationChart";
import Disclaimer from "./Disclaimer";
import RationaleTrace from "./RationaleTrace";

export default function DoseResult({ result }: { result: ExtrapolationResponse }) {
  const { dose_recommendation: rec, pathway_split: pathway, adult_pk: adultPk, concordance, rationale } = result;

  return (
    <div>
      <div className="card">
        <div className="result-header">
          <div>
            <div className="ctitle">{result.drug_name} · recommended starting dose</div>
            <div className="dose-mg">
              {rec.dose_mg.toFixed(2)} mg{" "}
              <span className="dose-sub">
                ({rec.dose_mg_per_kg.toFixed(3)} mg/kg) every {rec.interval_h}h
              </span>
            </div>
          </div>
          <ConcordanceBadge concordance={concordance} />
        </div>

        <table className="facts">
          <tbody>
            <tr>
              <td>Postmenstrual age</td>
              <td>{result.pma_weeks} weeks</td>
            </tr>
            <tr>
              <td>Elimination pathway</td>
              <td>
                {pathway.primary_pathway} (fm = {pathway.fm_primary})
              </td>
            </tr>
            <tr>
              <td>Maturation fraction applied</td>
              <td>{(rec.maturation_fraction * 100).toFixed(1)}% of adult pathway activity</td>
            </tr>
            <tr>
              <td>Child clearance / volume</td>
              <td>
                {rec.child_clearance_l_per_h.toFixed(2)} L/h · {rec.child_volume_l.toFixed(2)} L
              </td>
            </tr>
            <tr>
              <td>Adult reference PK</td>
              <td>
                CL {adultPk.adult_clearance_l_per_h} L/h · Vd {adultPk.adult_volume_l} L · fu{" "}
                {(1 - adultPk.adult_protein_binding).toFixed(2)} ({adultPk.confidence} confidence)
              </td>
            </tr>
          </tbody>
        </table>

        <Disclaimer disclaimer={result.disclaimer} ntiWarning={rationale.narrow_therapeutic_index_warning} />
      </div>

      <div className="card">
        <div className="ctitle">Maturation curve — {pathway.primary_pathway}</div>
        <MaturationChart
          tm50Weeks={pathway.tm50_weeks}
          hill={pathway.hill}
          pmaWeeks={result.pma_weeks}
          pathwayName={pathway.primary_pathway}
        />
      </div>

      <RationaleTrace rationale={result.rationale} />
    </div>
  );
}
