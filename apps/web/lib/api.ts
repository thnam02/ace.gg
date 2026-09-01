import type { HealthResponse, PlayerComparison, PlayerProfile } from "@/lib/types";

function serverApiUrl(): string {
  return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${serverApiUrl()}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(response.status, `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    return await apiFetch<HealthResponse>("/health");
  } catch {
    return null;
  }
}

export async function fetchPlayers(): Promise<PlayerProfile[]> {
  return apiFetch<PlayerProfile[]>("/players");
}

export async function fetchPlayer(playerId: string): Promise<PlayerProfile | null> {
  try {
    return await apiFetch<PlayerProfile>(`/players/${encodeURIComponent(playerId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function fetchComparison(ids: string[]): Promise<PlayerComparison> {
  const params = new URLSearchParams();
  for (const id of ids) {
    params.append("ids", id);
  }
  return apiFetch<PlayerComparison>(`/players/compare?${params.toString()}`);
}
