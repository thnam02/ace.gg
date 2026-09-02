import type {
  CirMetricMetadata,
  CirPlayerDetail,
  CirRankingResponse,
  HealthResponse,
  PlayerComparison,
  PlayerDetailResponse,
  PlayerProfile,
  PlayerSummary,
} from "@/lib/types";

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

export function summaryToProfile(summary: PlayerSummary): PlayerProfile {
  return {
    id: summary.id,
    display_name: summary.handle,
    riot_id: `VLR ${summary.vlr_player_id}`,
    team: summary.team?.name ?? null,
    region: summary.team?.region ?? summary.country ?? "—",
    rank: summary.stats.maps_played > 0 ? "Pro" : "—",
    stats: {
      matches: summary.stats.matches,
      acs: summary.stats.acs ?? 0,
      kd: summary.stats.kd ?? 0,
      hs_percent: summary.stats.hs_percent ?? 0,
      adr: summary.stats.adr ?? 0,
      win_rate: summary.stats.win_rate ?? 0,
    },
  };
}

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    return await apiFetch<HealthResponse>("/health");
  } catch {
    return null;
  }
}

export async function fetchPlayers(): Promise<PlayerProfile[]> {
  const summaries = await apiFetch<PlayerSummary[]>("/players");
  return summaries.map(summaryToProfile);
}

export async function fetchPlayer(playerId: string): Promise<PlayerProfile | null> {
  const detail = await fetchPlayerDetail(playerId);
  if (detail == null) {
    return null;
  }
  return summaryToProfile({
    id: detail.player.id,
    vlr_player_id: detail.player.vlr_player_id,
    handle: detail.player.handle,
    real_name: detail.player.real_name,
    country: detail.player.country,
    team: detail.player.team,
    stats: detail.stats,
  });
}

export async function fetchPlayerDetail(playerId: string): Promise<PlayerDetailResponse | null> {
  try {
    return await apiFetch<PlayerDetailResponse>(`/players/${encodeURIComponent(playerId)}`);
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
    params.append("player_ids", id);
  }
  return apiFetch<PlayerComparison>(`/players/compare?${params.toString()}`);
}

export async function fetchCirRankings(options?: {
  includeProvisional?: boolean;
  limit?: number;
  offset?: number;
}): Promise<CirRankingResponse> {
  const params = new URLSearchParams();
  if (options?.includeProvisional) {
    params.set("include_provisional", "true");
  }
  params.set("limit", String(options?.limit ?? 50));
  params.set("offset", String(options?.offset ?? 0));
  const query = params.toString();
  return apiFetch<CirRankingResponse>(`/rankings/cir?${query}`);
}

export async function fetchPlayerCir(playerId: string): Promise<CirPlayerDetail | null> {
  try {
    return await apiFetch<CirPlayerDetail>(`/players/${encodeURIComponent(playerId)}/cir`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function fetchCirMetadata(): Promise<CirMetricMetadata | null> {
  try {
    return await apiFetch<CirMetricMetadata>("/metrics/cir");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}
