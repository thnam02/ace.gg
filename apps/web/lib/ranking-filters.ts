import type { CirRankingPlayer } from "@/lib/types";

export const RANKING_TIERS = ["T1", "T2"] as const;
export const RANKING_REGIONS = [
  "Americas",
  "EMEA",
  "Pacific",
  "China",
  "INTL",
] as const;
export const RANKING_ROLES = [
  "Duelist",
  "Initiator",
  "Controller",
  "Sentinel",
] as const;
export const RANKING_SORT_KEYS = ["cir", "kpr", "dpr", "rounds", "maps"] as const;
export const RANKING_SORT_ORDERS = ["desc", "asc"] as const;

export type RankingSortKey = (typeof RANKING_SORT_KEYS)[number];
export type RankingSortOrder = (typeof RANKING_SORT_ORDERS)[number];

export type RankingExploreFilters = {
  query: string;
  tier: string | null;
  region: string | null;
  role: string | null;
  sort: RankingSortKey;
  order: RankingSortOrder;
};

export const DEFAULT_RANKING_FILTERS: RankingExploreFilters = {
  query: "",
  tier: null,
  region: null,
  role: null,
  sort: "cir",
  order: "desc",
};

export const RANKING_SORT_LABELS: Record<RankingSortKey, string> = {
  cir: "CIR",
  kpr: "KPR",
  dpr: "DPR",
  rounds: "Rounds",
  maps: "Maps",
};

export function defaultOrderForSort(sort: RankingSortKey): RankingSortOrder {
  return sort === "dpr" ? "asc" : "desc";
}

export function rankingFiltersActive(filters: RankingExploreFilters): boolean {
  return (
    filters.query.trim() !== "" ||
    filters.tier != null ||
    filters.region != null ||
    filters.role != null ||
    filters.sort !== DEFAULT_RANKING_FILTERS.sort ||
    filters.order !== DEFAULT_RANKING_FILTERS.order
  );
}

export function applyRankingExplore(
  players: CirRankingPlayer[],
  filters: RankingExploreFilters,
): CirRankingPlayer[] {
  const filtered = players.filter((player) => matchesRankingFilters(player, filters));
  return sortRankingPlayers(filtered, filters.sort, filters.order);
}

export function matchesRankingFilters(
  player: CirRankingPlayer,
  filters: RankingExploreFilters,
): boolean {
  if (filters.tier && (player.tier ?? "").toLowerCase() !== filters.tier.toLowerCase()) {
    return false;
  }
  if (
    filters.region &&
    (player.region ?? "").toLowerCase() !== filters.region.toLowerCase()
  ) {
    return false;
  }
  if (filters.role && (player.role ?? "").toLowerCase() !== filters.role.toLowerCase()) {
    return false;
  }
  const needle = filters.query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const team = `${player.team?.tag ?? ""} ${player.team?.name ?? ""}`.toLowerCase();
  return (
    player.handle.toLowerCase().includes(needle) ||
    team.includes(needle) ||
    (player.role ?? "").toLowerCase().includes(needle) ||
    (player.tier ?? "").toLowerCase().includes(needle) ||
    (player.region ?? "").toLowerCase().includes(needle)
  );
}

export function sortRankingPlayers(
  players: CirRankingPlayer[],
  sort: RankingSortKey,
  order: RankingSortOrder,
): CirRankingPlayer[] {
  return [...players].sort((left, right) => {
    const compared = compareSortValue(
      rankingSortValue(left, sort),
      rankingSortValue(right, sort),
      order,
    );
    if (compared !== 0) {
      return compared;
    }
    const cir = compareSortValue(left.cir, right.cir, "desc");
    if (cir !== 0) {
      return cir;
    }
    const rounds = compareSortValue(left.rounds, right.rounds, "desc");
    if (rounds !== 0) {
      return rounds;
    }
    return left.rank - right.rank;
  });
}

function rankingSortValue(
  player: CirRankingPlayer,
  sort: RankingSortKey,
): number | null {
  if (sort === "cir") {
    return player.cir;
  }
  if (sort === "kpr") {
    return player.kpr;
  }
  if (sort === "dpr") {
    return player.dpr;
  }
  if (sort === "rounds") {
    return player.rounds;
  }
  return player.maps;
}

function compareSortValue(
  left: number | null | undefined,
  right: number | null | undefined,
  order: RankingSortOrder,
): number {
  if (left == null && right == null) {
    return 0;
  }
  if (left == null) {
    return 1;
  }
  if (right == null) {
    return -1;
  }
  return order === "asc" ? left - right : right - left;
}

export function rankingFiltersEqual(
  left: RankingExploreFilters,
  right: RankingExploreFilters,
): boolean {
  return (
    left.query === right.query &&
    left.tier === right.tier &&
    left.region === right.region &&
    left.role === right.role &&
    left.sort === right.sort &&
    left.order === right.order
  );
}

export const RANKING_EXPLORE_STORAGE_KEY = "valorant-scout:ranking-explore";

export type RankingExploreSession = {
  filters: RankingExploreFilters;
  includeProvisional: boolean;
  page: number;
};

export function parseRankingExploreSession(
  raw: string | null | undefined,
): RankingExploreSession | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as {
      filters?: Partial<RankingExploreFilters>;
      includeProvisional?: boolean;
      page?: number;
    };
    const filters = normalizeExploreFilters(parsed.filters);
    if (filters == null) {
      return null;
    }
    return {
      filters,
      includeProvisional: Boolean(parsed.includeProvisional),
      page: Number.isInteger(parsed.page) && (parsed.page ?? 0) >= 1 ? parsed.page! : 1,
    };
  } catch {
    return null;
  }
}

export function serializeRankingExploreSession(session: RankingExploreSession): string {
  return JSON.stringify({
    filters: session.filters,
    includeProvisional: session.includeProvisional,
    page: session.page,
  });
}

export function readRankingExploreSession(): RankingExploreSession | null {
  return parseRankingExploreSession(rankingExploreStorage()?.getItem(RANKING_EXPLORE_STORAGE_KEY));
}

export function writeRankingExploreSession(session: RankingExploreSession): void {
  const storage = rankingExploreStorage();
  if (storage == null) {
    return;
  }
  if (
    !rankingFiltersActive(session.filters) &&
    !session.includeProvisional &&
    session.page <= 1
  ) {
    storage.removeItem(RANKING_EXPLORE_STORAGE_KEY);
    return;
  }
  storage.setItem(RANKING_EXPLORE_STORAGE_KEY, serializeRankingExploreSession(session));
}

export function clearRankingExploreSession(): void {
  rankingExploreStorage()?.removeItem(RANKING_EXPLORE_STORAGE_KEY);
}

function rankingExploreStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function normalizeExploreFilters(
  raw: Partial<RankingExploreFilters> | undefined,
): RankingExploreFilters | null {
  if (raw == null || typeof raw !== "object") {
    return null;
  }
  const sort = RANKING_SORT_KEYS.includes(raw.sort as RankingSortKey)
    ? (raw.sort as RankingSortKey)
    : DEFAULT_RANKING_FILTERS.sort;
  const order = RANKING_SORT_ORDERS.includes(raw.order as RankingSortOrder)
    ? (raw.order as RankingSortOrder)
    : defaultOrderForSort(sort);
  return {
    query: typeof raw.query === "string" ? raw.query : "",
    tier: asOptionalChoice(raw.tier, RANKING_TIERS),
    region: asOptionalChoice(raw.region, RANKING_REGIONS),
    role: asOptionalChoice(raw.role, RANKING_ROLES),
    sort,
    order,
  };
}

function asOptionalChoice<T extends string>(
  value: string | null | undefined,
  allowed: readonly T[],
): T | null {
  if (value == null || value === "") {
    return null;
  }
  return allowed.includes(value as T) ? (value as T) : null;
}
