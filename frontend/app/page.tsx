"use client";

import { useState } from "react";
import { extrapolate } from "@/lib/api";
import type { CaseRequest, ExtrapolationResponse } from "@/lib/types";
import DoseResult from "@/components/DoseResult";

const DRUGS = [
  { key: "midazolam", label: "Midazolam (CYP3A4)" },
  { key: "vancomycin", label: "Vancomycin (renal GFR)" },
  { key: "morphine", label: "Morphine (UGT2B7)" },
];

const DEFAULT_FORM: CaseRequest = {
  drug_name: "midazolam",
  indication: "",
  weight_kg: 3.5,
  gestational_age_weeks: 40,
  postnatal_age_weeks: 2,
  renal_impairment: false,
  hepatic_impairment: false,
};

export default function Home() {
  const [form, setForm] = useState<CaseRequest>(DEFAULT_FORM);
  const [result, setResult] = useState<ExtrapolationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof CaseRequest>(key: K, value: CaseRequest[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await extrapolate(form);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="wrap">
      <header className="hero">
        <div className="eyebrow">Dev Track · Built with Claude: Life Sciences</div>
        <h1>
          Dosing children where the <em>guidelines run out</em>.
        </h1>
        <p className="lede">
          Enter a case below. PaedScale derives a defensible pediatric starting dose from adult
          pharmacokinetics using allometry x organ maturation, with a cited, auditable rationale.
        </p>
      </header>

      <div className="grid">
        <div>
          <form className="card" onSubmit={onSubmit}>
            <div className="ctitle">Case input</div>

            <label htmlFor="drug">Drug</label>
            <select id="drug" value={form.drug_name} onChange={(e) => update("drug_name", e.target.value)}>
              {DRUGS.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </select>

            <label htmlFor="indication">Indication (optional)</label>
            <input
              id="indication"
              type="text"
              value={form.indication}
              onChange={(e) => update("indication", e.target.value)}
              placeholder="e.g. procedural sedation"
            />

            <label htmlFor="weight">Weight (kg)</label>
            <input
              id="weight"
              type="number"
              step="0.1"
              min="0.3"
              value={form.weight_kg}
              onChange={(e) => update("weight_kg", parseFloat(e.target.value))}
            />

            <label htmlFor="ga">Gestational age at birth (weeks)</label>
            <input
              id="ga"
              type="number"
              step="1"
              min="22"
              max="44"
              value={form.gestational_age_weeks}
              onChange={(e) => update("gestational_age_weeks", parseFloat(e.target.value))}
            />

            <label htmlFor="pna">Postnatal age (weeks)</label>
            <input
              id="pna"
              type="number"
              step="1"
              min="0"
              value={form.postnatal_age_weeks}
              onChange={(e) => update("postnatal_age_weeks", parseFloat(e.target.value))}
            />

            <div className="checkrow">
              <input
                id="renal"
                type="checkbox"
                checked={form.renal_impairment}
                onChange={(e) => update("renal_impairment", e.target.checked)}
              />
              <label htmlFor="renal">Renal impairment</label>
            </div>
            <div className="checkrow">
              <input
                id="hepatic"
                type="checkbox"
                checked={form.hepatic_impairment}
                onChange={(e) => update("hepatic_impairment", e.target.checked)}
              />
              <label htmlFor="hepatic">Hepatic impairment</label>
            </div>

            <button className="submit" type="submit" disabled={loading}>
              {loading ? "Extrapolating…" : "Extrapolate dose"}
            </button>

            {error && <div className="error-box">{error}</div>}
          </form>
        </div>

        <div>
          {result ? (
            <DoseResult result={result} />
          ) : (
            <div className="card empty-state">
              Submit a case to see the recommended dose, maturation curve, concordance check, and
              full auditable rationale.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
