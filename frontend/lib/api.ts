import type { CaseRequest, ExtrapolationResponse } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function fetchDrugs(): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/drugs`);
  if (!res.ok) throw new Error("Failed to load drug list");
  const data = await res.json();
  return data.drugs;
}

export async function extrapolate(payload: CaseRequest): Promise<ExtrapolationResponse> {
  const res = await fetch(`${API_BASE_URL}/extrapolate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Request failed");
  }

  return res.json();
}
