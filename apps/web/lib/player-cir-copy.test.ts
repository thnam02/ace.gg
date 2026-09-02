import { describe, expect, it } from "vitest";

import {
  SCOUTING_DISCLAIMER,
  cirInterpretation,
  cirRankLine,
  clampPercentile,
  contextBenchmark,
  deathAvoidanceExpectation,
  expectationLabel,
  formatClutchStat,
  kprExpectation,
  kprResidualCopy,
  metricVersionLabel,
  openingEfficiencyDisplay,
  openingEfficiencyHelper,
  openingFrequencyDisplay,
  openingFrequencyHelper,
  percentileBarLabel,
  percentileOrdinal,
  playerIdentityLine,
  rankHeadline,
  reliabilityLine,
} from "@/lib/player-cir-copy";

describe("CIR hero copy", () => {
  it("uses top-percentile wording at CIR 100", () => {
    expect(cirInterpretation(100)).toBe(
      "Top percentile of the 2026 reference population",
    );
    expect(cirInterpretation(99.6)).toContain("99th percentile");
    expect(cirInterpretation(99.6)).not.toBe(
      "Top percentile of the 2026 reference population",
    );
    expect(cirInterpretation(100)).not.toContain("100+");
    expect(cirInterpretation(100)).not.toContain("percentile interpretation");
  });

  it("uses compact percentile wording below 100", () => {
    expect(cirInterpretation(90)).toBe(
      "Around the 90th percentile of the 2026 reference population",
    );
    expect(cirInterpretation(30.3)).toBe(
      "Around the 30th percentile of the 2026 reference population",
    );
    expect(cirInterpretation(99.8)).toBe(
      "Around the 99th percentile of the 2026 reference population",
    );
    expect(cirInterpretation(91)).toContain("91st percentile");
    expect(cirInterpretation(92)).toContain("92nd percentile");
    expect(cirInterpretation(23)).toContain("23rd percentile");
    expect(cirInterpretation(null)).toBe("CIR unavailable");
  });

  it("renders rank against established count", () => {
    expect(cirRankLine(1, 343, "ESTABLISHED")).toBe("Established ranking");
    expect(rankHeadline(1, 343)).toEqual({ rank: "#1 / 343", of: null });
    expect(rankHeadline(319, 408)).toEqual({ rank: "#319 / 408", of: null });
  });

  it("does not invent a rank for provisional or low-sample players", () => {
    expect(cirRankLine(null, 343, "PROVISIONAL")).toBe("Not in established ranking");
    expect(cirRankLine(undefined, 343, "LOW_SAMPLE")).toBe(
      "Not in established ranking",
    );
    expect(rankHeadline(null, 343)).toEqual({ rank: "Not ranked", of: null });
  });
});

describe("player identity copy", () => {
  it("joins team and role without a placeholder dash", () => {
    expect(playerIdentityLine("Rex Regum Qeon", "Controller")).toBe(
      "Rex Regum Qeon · Controller",
    );
    expect(playerIdentityLine(null, "Controller")).toBe("Unattached · Controller");
    expect(playerIdentityLine("  ", "Controller")).toBe("Unattached · Controller");
    expect(playerIdentityLine(null, null)).toBe("Unattached");
    expect(playerIdentityLine("Team Liquid", null)).toBe("Team Liquid");
  });
});

describe("context benchmark copy", () => {
  it("uses frozen role and tier, not agent", () => {
    expect(contextBenchmark("T1", "Sentinel")).toBe("Compared with T1 Sentinels");
    expect(contextBenchmark("T1", "Duelist")).toBe("Compared with T1 Duelists");
    expect(contextBenchmark("T2", "Controller")).toBe("Compared with T2 Controllers");
    expect(contextBenchmark("T1", "Jett")).toBe("Compared with T1 Jetts");
  });
});

describe("expectation wording", () => {
  it("formats kill production above and below expected", () => {
    expect(kprResidualCopy(0.12)).toBe("+0.12 kills/round vs expected");
    expect(kprExpectation(0.12).text).toBe("+0.12 vs expected");
    expect(kprExpectation(0.12).direction).toBe("above");
    expect(kprExpectation(-0.08).text).toBe("-0.08 vs expected");
    expect(kprExpectation(-0.04).text).toBe("-0.04 vs expected");
    expect(kprExpectation(-0.08).direction).toBe("below");
    expect(expectationLabel("above")).toBe("Above expected");
    expect(expectationLabel("below")).toBe("Below expected");
  });

  it("uses human-friendly death-avoidance wording", () => {
    expect(deathAvoidanceExpectation(0.11).text).toBe(
      "0.11 fewer deaths/round than expected",
    );
    expect(deathAvoidanceExpectation(0.11).direction).toBe("above");
    expect(deathAvoidanceExpectation(-0.09).text).toBe(
      "0.09 more deaths/round than expected",
    );
    expect(deathAvoidanceExpectation(-0.03).text).toBe(
      "0.03 more deaths/round than expected",
    );
    expect(deathAvoidanceExpectation(-0.09).direction).toBe("below");
  });
});

describe("reliability and version copy", () => {
  it("keeps reliability separate from CIR", () => {
    expect(reliabilityLine("HIGH", 977)).toBe("HIGH reliability · 977 rounds");
  });

  it("shows CIR v0.2 reference without training internals", () => {
    expect(metricVersionLabel("v0.2-real-2026")).toBe("CIR v0.2 · 2026 reference");
    expect(metricVersionLabel("v0.2-real-2026")).not.toContain("τ");
    expect(metricVersionLabel("v0.2-real-2026")).not.toContain("500");
  });
});

describe("scouting display helpers", () => {
  it("keeps the visible scouting disclaimer", () => {
    expect(SCOUTING_DISCLAIMER).toBe(
      "These stats describe playstyle and do not directly affect CIR.",
    );
  });

  it("renders missing clutch as N/A instead of 0", () => {
    expect(formatClutchStat(null)).toBe("N/A");
    expect(formatClutchStat(0)).toBe("N/A");
    expect(formatClutchStat(0, 0)).toBe("N/A");
    expect(formatClutchStat(0, 4)).toBe("0.0%");
  });

  it("formats opening frequency and efficiency as percents", () => {
    expect(openingFrequencyDisplay(0.17)).toBe("17%");
    expect(openingFrequencyDisplay(null)).toBe("N/A");
    expect(openingFrequencyHelper(0.25)).toBe(
      "25% of rounds involved in the opening duel",
    );
    expect(openingEfficiencyDisplay(0.38)).toBe("38%");
    expect(openingEfficiencyDisplay(0.6)).toBe("60%");
    expect(openingEfficiencyHelper(0.6)).toBe("Won 60% of opening duels");
  });

  it("clamps the percentile bar at 100", () => {
    expect(clampPercentile(100)).toBe(100);
    expect(clampPercentile(104)).toBe(100);
    expect(clampPercentile(-4)).toBe(0);
    expect(percentileBarLabel(100)).toBe("CIR percentile: 100 out of 100");
    expect(percentileBarLabel(87.4)).toBe("CIR percentile: 87.4 out of 100");
    expect(percentileBarLabel(30.3)).toBe("CIR percentile: 30.3 out of 100");
    expect(percentileOrdinal(90)).toBe("90th");
  });
});
