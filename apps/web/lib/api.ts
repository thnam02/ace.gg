import { apiRequestUrl } from "@/lib/api-origin";
import type {
  CirMetricMetadata,
  CirPlayerDetail,
  CirRankingResponse,
  EventListResponse,
  HealthResponse,
  PlayerComparison,
  PlayerDetailResponse,
  PlayerOptionsResponse,
  PlayerProfile,
  PlayerSummary,
} from "@/lib/types";

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
  const response = await fetch(apiRequestUrl(path), { cache: "no-store" });
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok) {
    throw new ApiError(response.status, `Request failed (${response.status})`);
  }
  if (!contentType.includes("application/json")) {
    throw new ApiError(response.status, "API returned a non-JSON response");
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

export async function fetchPlayerOptions(options?: {
  search?: string;
  team?: string;
  role?: string;
  tier?: string;
  limit?: number;
  offset?: number;
}): Promise<PlayerOptionsResponse> {
  const params = new URLSearchParams();
  if (options?.search) {
    params.set("search", options.search);
  }
  if (options?.team) {
    params.set("team", options.team);
  }
  if (options?.role) {
    params.set("role", options.role);
  }
  if (options?.tier) {
    params.set("tier", options.tier);
  }
  params.set("limit", String(options?.limit ?? 20));
  params.set("offset", String(options?.offset ?? 0));
  return apiFetch<PlayerOptionsResponse>(`/players/options?${params.toString()}`);
}

export const CIR_RANKING_FETCH_LIMIT = 2000;

export async function fetchCirRankings(options?: {
  includeProvisional?: boolean;
  limit?: number;
  offset?: number;
}): Promise<CirRankingResponse> {
  const params = new URLSearchParams();
  if (options?.includeProvisional) {
    params.set("include_provisional", "true");
  }
  params.set("limit", String(options?.limit ?? CIR_RANKING_FETCH_LIMIT));
  params.set("offset", String(options?.offset ?? 0));
  const query = params.toString();
  return apiFetch<CirRankingResponse>(`/rankings/cir?${query}`);
}

export async function fetchEventCirRankings(options: {
  vlrEventId: number;
  includeProvisional?: boolean;
  includeLowSample?: boolean;
  limit?: number;
  offset?: number;
}): Promise<CirRankingResponse> {
  const params = new URLSearchParams();
  if (options.includeProvisional !== false) {
    params.set("include_provisional", "true");
  }
  if (options.includeLowSample !== false) {
    params.set("include_low_sample", "true");
  }
  params.set("limit", String(options.limit ?? CIR_RANKING_FETCH_LIMIT));
  params.set("offset", String(options.offset ?? 0));
  return apiFetch<CirRankingResponse>(
    `/rankings/cir/by-event/${options.vlrEventId}?${params.toString()}`,
  );
}

export async function fetchEvents(options?: {
  region?: string | null;
  circuit?: string | null;
  seasonYear?: number | null;
  limit?: number;
}): Promise<EventListResponse> {
  const params = new URLSearchParams();
  if (options?.region) {
    params.set("region", options.region);
  }
  if (options?.circuit) {
    params.set("circuit", options.circuit);
  }
  if (options?.seasonYear != null) {
    params.set("season_year", String(options.seasonYear));
  }
  params.set("limit", String(options?.limit ?? 200));
  const query = params.toString();
  return apiFetch<EventListResponse>(`/events?${query}`);
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
