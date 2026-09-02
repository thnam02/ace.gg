import { describe, expect, it } from "vitest";

import {
  DEFAULT_RANKING_FILTERS,
  applyRankingExplore,
  defaultOrderForSort,
  rankingFiltersActive,
} from "@/lib/ranking-filters";
import type { CirRankingPlayer } from "@/lib/types";

function player(
  overrides: Partial<CirRankingPlayer> & { handle: string; rank: number },
): CirRankingPlayer {
  return {
    player_id: overrides.player_id ?? overrides.handle.toLowerCase(),
    team: overrides.team ?? {
      id: "t",
      vlr_team_id: 1,
      name: "Team",
      tag: "TM",
      region: overrides.region ?? "Americas",
    },
    role: overrides.role ?? "Duelist",
    tier: overrides.tier ?? "T1",
    region: overrides.region ?? "Americas",
    primary_agent: null,
    cir: overrides.cir ?? 80,
    reliability: "HIGH",
    rounds: overrides.rounds ?? 400,
    maps: overrides.maps ?? 20,
    kpr: overrides.kpr ?? 0.8,
    dpr: overrides.dpr ?? 0.6,
    sample_status: "ESTABLISHED",
    metric_version: "v0.2-real-2026",
    ...overrides,
  };
}

describe("ranking explore filters", () => {
  const pool = [
    player({
      rank: 1,
      handle: "TenZ",
      cir: 99,
      kpr: 0.9,
      dpr: 0.55,
      role: "Duelist",
      tier: "T1",
      region: "Americas",
    }),
    player({
      rank: 2,
      handle: "Boaster",
      cir: 88,
      kpr: 0.7,
      dpr: 0.62,
      role: "Controller",
      tier: "T1",
      region: "EMEA",
    }),
    player({
      rank: 3,
      handle: "something",
      cir: 70,
      kpr: 0.85,
      dpr: 0.7,
      role: "Duelist",
      tier: "T2",
      region: "Pacific",
      rounds: 220,
    }),
  ];

  it("filters the current pool by tier, region, and role without changing CIR rank", () => {
    const filtered = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      tier: "T1",
      region: "Americas",
      role: "Duelist",
    });
    expect(filtered.map((item) => item.handle)).toEqual(["TenZ"]);
    expect(filtered[0]?.rank).toBe(1);
  });

  it("sorts by descriptive scouting metrics and keeps CIR as the tie-break", () => {
    const byKpr = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      sort: "kpr",
      order: "desc",
    });
    expect(byKpr.map((item) => item.handle)).toEqual(["TenZ", "something", "Boaster"]);
    expect(byKpr.map((item) => item.rank)).toEqual([1, 3, 2]);

    const byDpr = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      sort: "dpr",
      order: defaultOrderForSort("dpr"),
    });
    expect(byDpr.map((item) => item.handle)).toEqual(["TenZ", "Boaster", "something"]);
  });

  it("treats search together with category filters", () => {
    const filtered = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      query: "boa",
      role: "Controller",
    });
    expect(filtered.map((item) => item.handle)).toEqual(["Boaster"]);
    expect(
      applyRankingExplore(pool, {
        ...DEFAULT_RANKING_FILTERS,
        query: "boa",
        role: "Duelist",
      }),
    ).toEqual([]);
  });

  it("marks non-default explore state as active", () => {
    expect(rankingFiltersActive(DEFAULT_RANKING_FILTERS)).toBe(false);
    expect(
      rankingFiltersActive({ ...DEFAULT_RANKING_FILTERS, region: "China" }),
    ).toBe(true);
  });
});
