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
export const RANKING_SORT_KEYS = [
  "cir",
  "kpr",
  "dpr",
  "rounds",
  "maps",
  "acs",
  "adr",
  "kast",
  "opening_efficiency",
  "opening_frequency",
] as const;
export const RANKING_SORT_ORDERS = ["desc", "asc"] as const;
export const RANKING_MIN_ROUNDS_OPTIONS = [null, 50, 100, 250] as const;

export type RankingSortKey = (typeof RANKING_SORT_KEYS)[number];
export type RankingSortOrder = (typeof RANKING_SORT_ORDERS)[number];
export type RankingMinRounds = (typeof RANKING_MIN_ROUNDS_OPTIONS)[number];

export type RankingExploreFilters = {
  query: string;
  tier: string | null;
  region: string | null;
  eventId: string | null;
  role: string | null;
  sort: RankingSortKey;
  order: RankingSortOrder;
  minRounds: number | null;
};

export const DEFAULT_RANKING_FILTERS: RankingExploreFilters = {
  query: "",
  tier: null,
  region: null,
  eventId: null,
  role: null,
  sort: "cir",
  order: "desc",
  minRounds: null,
};

export const RANKING_SORT_LABELS: Record<RankingSortKey, string> = {
  cir: "CIR",
  kpr: "KPR",
  dpr: "DPR",
  rounds: "Rounds",
  maps: "Maps",
  acs: "ACS",
  adr: "ADR",
  kast: "KAST",
  opening_efficiency: "Opening eff.",
  opening_frequency: "Opening freq.",
};

export const RANKING_MIN_ROUNDS_LABELS: Record<string, string> = {
  all: "All",
  "50": "50+",
  "100": "100+",
  "250": "250+",
};

export function defaultOrderForSort(sort: RankingSortKey): RankingSortOrder {
  return sort === "dpr" ? "asc" : "desc";
}

export function rankingFiltersActive(filters: RankingExploreFilters): boolean {
  return (
    filters.query.trim() !== "" ||
    filters.tier != null ||
    filters.region != null ||
    filters.eventId != null ||
    filters.role != null ||
    filters.minRounds != null ||
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
  if (
    !filters.eventId &&
    filters.tier &&
    (player.tier ?? "").toLowerCase() !== filters.tier.toLowerCase()
  ) {
    return false;
  }
  if (
    !filters.eventId &&
    filters.region &&
    (player.region ?? "").toLowerCase() !== filters.region.toLowerCase()
  ) {
    return false;
  }
  if (filters.role && (player.role ?? "").toLowerCase() !== filters.role.toLowerCase()) {
    return false;
  }
  if (filters.minRounds != null && player.rounds < filters.minRounds) {
    return false;
  }
  const needle = filters.query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const team = `${player.team?.tag ?? ""} ${player.team?.name ?? ""}`.toLowerCase();
  const playedRoles = (player.roles ?? []).map((item) => item.role).join(" ").toLowerCase();
  return (
    player.handle.toLowerCase().includes(needle) ||
    team.includes(needle) ||
    (player.role ?? "").toLowerCase().includes(needle) ||
    playedRoles.includes(needle) ||
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
  if (sort === "maps") {
    return player.maps;
  }
  if (sort === "acs") {
    return player.acs ?? null;
  }
  if (sort === "adr") {
    return player.adr ?? null;
  }
  if (sort === "kast") {
    return player.kast ?? null;
  }
  if (sort === "opening_efficiency") {
    return player.opening_efficiency ?? null;
  }
  return player.opening_frequency ?? null;
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
    left.eventId === right.eventId &&
    left.role === right.role &&
    left.sort === right.sort &&
    left.order === right.order &&
    left.minRounds === right.minRounds
  );
}

export type RankingUrlState = {
  filters: RankingExploreFilters;
  includeProvisional: boolean;
};

function firstParam(value: string | string[] | undefined | null): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

function readParam(
  params: URLSearchParams | Record<string, string | string[] | undefined>,
  key: string,
): string | null {
  if (params instanceof URLSearchParams) {
    return params.get(key);
  }
  return firstParam(params[key]);
}

export function parseRankingSearchParams(
  params: URLSearchParams | Record<string, string | string[] | undefined>,
): RankingUrlState {
  const sortRaw = readParam(params, "sort");
  const sort = RANKING_SORT_KEYS.includes(sortRaw as RankingSortKey)
    ? (sortRaw as RankingSortKey)
    : DEFAULT_RANKING_FILTERS.sort;
  const orderRaw = readParam(params, "order");
  const order = RANKING_SORT_ORDERS.includes(orderRaw as RankingSortOrder)
    ? (orderRaw as RankingSortOrder)
    : defaultOrderForSort(sort);
  const minRoundsRaw = readParam(params, "min_rounds");
  const minRoundsParsed =
    minRoundsRaw != null && minRoundsRaw !== "" ? Number(minRoundsRaw) : null;
  const minRounds =
    minRoundsParsed != null &&
    Number.isFinite(minRoundsParsed) &&
    (RANKING_MIN_ROUNDS_OPTIONS as readonly (number | null)[]).includes(minRoundsParsed)
      ? minRoundsParsed
      : null;
  const eventRaw = readParam(params, "event");
  const eventId = eventRaw && isUuid(eventRaw) ? eventRaw : null;
  const includeFlag = readParam(params, "include_provisional");
  const includeProvisional =
    includeFlag === "1" || includeFlag === "true" || eventId != null;

  return {
    filters: {
      query: "",
      tier: asOptionalChoice(readParam(params, "tier"), RANKING_TIERS),
      region: asOptionalChoice(readParam(params, "region"), RANKING_REGIONS),
      eventId,
      role: asOptionalChoice(readParam(params, "role"), RANKING_ROLES),
      sort,
      order,
      minRounds,
    },
    includeProvisional,
  };
}

export function buildRankingSearchParams(
  filters: RankingExploreFilters,
  options?: { includeProvisional?: boolean },
): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.tier) {
    params.set("tier", filters.tier);
  }
  if (filters.region) {
    params.set("region", filters.region);
  }
  if (filters.eventId) {
    params.set("event", filters.eventId);
  }
  if (filters.role) {
    params.set("role", filters.role);
  }
  if (filters.sort !== DEFAULT_RANKING_FILTERS.sort) {
    params.set("sort", filters.sort);
  }
  if (filters.order !== defaultOrderForSort(filters.sort)) {
    params.set("order", filters.order);
  }
  if (filters.minRounds != null) {
    params.set("min_rounds", String(filters.minRounds));
  }
  const includeProvisional =
    options?.includeProvisional === true || filters.eventId != null;
  if (includeProvisional && filters.eventId == null) {
    params.set("include_provisional", "1");
  }
  return params;
}

export function rankingHref(
  filters: RankingExploreFilters,
  options?: { includeProvisional?: boolean },
): string {
  const query = buildRankingSearchParams(filters, options).toString();
  return query ? `/rankings?${query}` : "/rankings";
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
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
  const minRounds =
    typeof raw.minRounds === "number" &&
    (RANKING_MIN_ROUNDS_OPTIONS as readonly (number | null)[]).includes(raw.minRounds)
      ? raw.minRounds
      : null;
  return {
    query: typeof raw.query === "string" ? raw.query : "",
    tier: asOptionalChoice(raw.tier, RANKING_TIERS),
    region: asOptionalChoice(raw.region, RANKING_REGIONS),
    eventId:
      typeof raw.eventId === "string" && isUuid(raw.eventId) ? raw.eventId : null,
    role: asOptionalChoice(raw.role, RANKING_ROLES),
    sort,
    order,
    minRounds,
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
