import type { HealthResponse, PlayerComparison, PlayerProfile } from "@valorant-scout/shared";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${path}`);
  }
  return (await response.json()) as T;
}

export function getApiUrl(): string {
  return API_URL;
}

export function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export function getPlayers(): Promise<PlayerProfile[]> {
  return fetchJson<PlayerProfile[]>("/players");
}

export function comparePlayers(ids: string[]): Promise<PlayerComparison> {
  const params = new URLSearchParams();
  for (const id of ids) {
    params.append("ids", id);
  }
  return fetchJson<PlayerComparison>(`/players/compare?${params.toString()}`);
}
