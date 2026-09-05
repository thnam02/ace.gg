import { describe, expect, it } from "vitest";

import {
  DEFAULT_RANKING_FILTERS,
  applyRankingExplore,
  buildRankingSearchParams,
  defaultOrderForSort,
  parseRankingExploreSession,
  parseRankingSearchParams,
  rankingFiltersActive,
  rankingFiltersEqual,
  rankingHref,
  serializeRankingExploreSession,
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
    acs: overrides.acs ?? 220,
    adr: overrides.adr ?? 140,
    kast: overrides.kast ?? 70,
    opening_efficiency: overrides.opening_efficiency ?? 0.55,
    opening_frequency: overrides.opening_frequency ?? 0.2,
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
      acs: 250,
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
      acs: 200,
      rounds: 80,
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
      acs: 230,
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

  it("sorts by event-capable scouting keys", () => {
    const byAcs = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      sort: "acs",
      order: "desc",
    });
    expect(byAcs.map((item) => item.handle)).toEqual(["TenZ", "something", "Boaster"]);
  });

  it("filters by minimum rounds", () => {
    const filtered = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      minRounds: 100,
    });
    expect(filtered.map((item) => item.handle)).toEqual(["TenZ", "something"]);
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
    expect(
      rankingFiltersActive({ ...DEFAULT_RANKING_FILTERS, minRounds: 250 }),
    ).toBe(true);
    expect(
      rankingFiltersActive({
        ...DEFAULT_RANKING_FILTERS,
        eventId: "11111111-1111-4111-8111-111111111111",
      }),
    ).toBe(true);
  });

  it("round-trips applied explore state so returning from a player keeps filters", () => {
    const session = {
      filters: { ...DEFAULT_RANKING_FILTERS, tier: "T1", role: "Duelist" },
      includeProvisional: true,
      page: 3,
    };
    const restored = parseRankingExploreSession(serializeRankingExploreSession(session));
    expect(restored).toEqual(session);
    expect(rankingFiltersEqual(session.filters, restored?.filters ?? DEFAULT_RANKING_FILTERS)).toBe(
      true,
    );
    expect(parseRankingExploreSession("not-json")).toBeNull();
  });

  it("parses and serializes ranking URL state", () => {
    const eventId = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
    const parsed = parseRankingSearchParams({
      tier: "T1",
      region: "Pacific",
      event: eventId,
      sort: "cir",
      min_rounds: "50",
      role: "Duelist",
      order: "asc",
    });
    expect(parsed.filters).toEqual({
      query: "",
      tier: "T1",
      region: "Pacific",
      eventId,
      role: "Duelist",
      sort: "cir",
      order: "asc",
      minRounds: 50,
    });
    expect(parsed.includeProvisional).toBe(true);

    const params = buildRankingSearchParams(parsed.filters);
    expect(params.get("tier")).toBe("T1");
    expect(params.get("region")).toBe("Pacific");
    expect(params.get("event")).toBe(eventId);
    expect(params.get("role")).toBe("Duelist");
    expect(params.get("min_rounds")).toBe("50");
    expect(params.get("order")).toBe("asc");
    expect(params.get("sort")).toBeNull();
    expect(rankingHref(DEFAULT_RANKING_FILTERS)).toBe("/rankings");
  });

  it("does not re-filter tier or region inside an event scope", () => {
    const filtered = applyRankingExplore(pool, {
      ...DEFAULT_RANKING_FILTERS,
      eventId: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
      tier: "T1",
      region: "Pacific",
    });
    expect(filtered.map((item) => item.handle)).toEqual(["TenZ", "Boaster", "something"]);
  });

  it("defaults min rounds to All and ignores invalid event ids", () => {
    const parsed = parseRankingSearchParams({ sort: "acs", event: "not-a-uuid" });
    expect(parsed.filters.minRounds).toBeNull();
    expect(parsed.filters.eventId).toBeNull();
    expect(parsed.filters.sort).toBe("acs");
    expect(parsed.includeProvisional).toBe(false);
  });
});
