import { describe, expect, it } from "vitest";

import { formatCir, formatCirOrUnavailable, formatSyncDate } from "@/lib/format";
import {
  buildHomeLiveStats,
  compactPercentile,
  compactResidual,
  homeFreshnessLabel,
  playerSearchCirLabel,
  reliabilityRoundsLine,
  sampleStatusLabel,
  topPlayersPreview,
} from "@/lib/home";
import type { CirRankingPlayer } from "@/lib/types";

function player(index: number, cir = 90): CirRankingPlayer {
  return {
    rank: index,
    player_id: `player-${index}`,
    handle: `Player${index}`,
    team: {
      id: "team-1",
      vlr_team_id: 1,
      name: "Sentinels",
      tag: "SEN",
      region: "NA",
    },
    role: "Duelist",
    tier: "T1",
    region: "Americas",
    primary_agent: null,
    cir,
    reliability: "HIGH",
    rounds: 400,
    maps: 20,
    kpr: 0.8,
    dpr: 0.6,
    sample_status: "ESTABLISHED",
    metric_version: "v0.2-real-2026",
  };
}

describe("formatCir homepage display", () => {
  it("does not round 99.8 to 100 or append a percent sign", () => {
    expect(formatCir(99.8)).toBe("99.8");
    expect(formatCir(99.8)).not.toBe("100");
    expect(formatCir(99.8)).not.toContain("%");
    expect(formatCirOrUnavailable(99.8)).toBe("99.8");
    expect(formatCirOrUnavailable(null)).toBe("CIR unavailable");
    expect(formatCirOrUnavailable(undefined)).toBe("CIR unavailable");
  });
});

describe("buildHomeLiveStats", () => {
  it("omits count and season when canonical data is missing", () => {
    const stats = buildHomeLiveStats({});
    expect(stats.map((item) => item.label)).toEqual(["Competitive tiers", "Data updates"]);
    expect(stats.some((item) => item.label === "Established players")).toBe(false);
  });

  it("uses ranking total and metadata season when available", () => {
    const stats = buildHomeLiveStats({
      establishedCount: 408,
      season: 2026,
      circuit: "VCT",
    });
    expect(stats[0]).toEqual({ value: "408", label: "Established players" });
    expect(stats[1]).toEqual({ value: "2026", label: "VCT season" });
  });
});

describe("home display helpers", () => {
  it("formats freshness from last_data_sync_at", () => {
    expect(homeFreshnessLabel("2026-09-03T03:00:00+00:00")).toBe("Updated Sep 3, 2026");
    expect(homeFreshnessLabel(null)).toBe("Updated daily");
    expect(formatSyncDate("2026-09-03T03:00:00+00:00")).toBe("Sep 3, 2026");
  });

  it("keeps compact CIR percentile and residuals", () => {
    expect(compactPercentile(99.8)).toBe("99th percentile");
    expect(compactPercentile(92.4)).toBe("92nd percentile");
    expect(compactResidual(0.12)).toBe("+0.12 vs expected");
    expect(compactResidual(null)).toBeNull();
  });

  it("labels search CIR and sample status without faking zero", () => {
    expect(playerSearchCirLabel(99.8)).toBe("CIR 99.8");
    expect(playerSearchCirLabel(null)).toBe("CIR unavailable");
    expect(sampleStatusLabel("ESTABLISHED")).toBe("Established");
    expect(reliabilityRoundsLine("HIGH", 1487)).toBe("HIGH · 1,487 rounds");
  });

  it("limits the homepage preview to six players", () => {
    const preview = topPlayersPreview(
      Array.from({ length: 8 }, (_, index) => player(index + 1)),
    );
    expect(preview).toHaveLength(6);
    expect(preview.at(-1)?.handle).toBe("Player6");
  });
});
