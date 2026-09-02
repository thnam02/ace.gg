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
