import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import {
  MAX_COMPARE_MESSAGE,
  MAX_COMPARE_PLAYERS,
  addCompareId,
  compareCardGridClass,
  compareChipLabel,
  compareDensity,
  compareEmptyMessage,
  compareHref,
  compareOptionFromCir,
  compareRequestErrorMessage,
  isResolvedCompareHandle,
  parseCompareIds,
  pickCompareSearchMatch,
  removeCompareId,
} from "@/lib/compare";

describe("compare selection", () => {
  it("parses URL ids and writes them back", () => {
    expect(parseCompareIds(["a", "b,c"])).toEqual(["a", "b", "c"]);
    expect(compareHref(["a", "b"])).toBe("/compare?ids=a&ids=b");
  });

  it("enforces a maximum of 4 players without dropping existing ones", () => {
    const ids = ["1", "2", "3", "4"];
    const result = addCompareId(ids, "5");
    expect(result.ids).toEqual(ids);
    expect(result.error).toBe(MAX_COMPARE_MESSAGE);
    expect(MAX_COMPARE_PLAYERS).toBe(4);
    expect(removeCompareId(ids, "2")).toEqual(["1", "3", "4"]);
  });

  it("returns empty-state copy", () => {
    expect(compareEmptyMessage(0)).toBe("Select 2–4 players to compare.");
    expect(compareEmptyMessage(1)).toBe("Add at least one more player.");
  });

  it("keeps ID copy for validation failures and uses connection copy otherwise", () => {
    expect(compareRequestErrorMessage(new ApiError(422, "bad"))).toBe(
      "The comparison request failed. Check the selected IDs and try again.",
    );
    expect(compareRequestErrorMessage(new ApiError(429, "slow down"))).toBe(
      "Too many comparison requests. Wait a moment and try again.",
    );
    expect(compareRequestErrorMessage(new Error("Failed to fetch"))).toBe(
      "Could not load this comparison. Check the connection and try again.",
    );
  });

  it("uses responsive grid classes for 2, 3, and 4 players", () => {
    expect(compareCardGridClass(2)).toContain("md:grid-cols-2");
    expect(compareCardGridClass(3)).toContain("lg:grid-cols-3");
    expect(compareCardGridClass(4)).toContain("xl:grid-cols-4");
    expect(compareCardGridClass(4)).toContain("md:grid-cols-2");
    expect(compareDensity(2)).toBe("rich");
    expect(compareDensity(3)).toBe("compact");
    expect(compareDensity(4)).toBe("dense");
  });

  it("picks a unique search match without a suggestion list", () => {
    const players = [
      { handle: "TenZ" },
      { handle: "something" },
      { handle: "Demon1" },
    ];
    expect(pickCompareSearchMatch("tenz", players)?.handle).toBe("TenZ");
    expect(pickCompareSearchMatch("som", players)?.handle).toBe("something");
    expect(pickCompareSearchMatch("e", players)).toBeNull();
    expect(pickCompareSearchMatch("", players)).toBeNull();
  });

  it("never uses a truncated player id as the selected chip label", () => {
    const id = "a4f73e58-a086-4238-ab2b-02767a7057c8";
    expect(compareChipLabel({ id, handle: id.slice(0, 8) })).toBe("Loading…");
    expect(compareChipLabel({ id, handle: "Neon" })).toBe("Neon");
    expect(isResolvedCompareHandle("a4f73e58", id)).toBe(false);
    expect(compareOptionFromCir({
      player_id: id,
      handle: "Neon",
      team: null,
      role: "Sentinel",
      cir: 99.8,
      raw_cir: 99.8,
      reliability: "HIGH",
      reliability_pct: null,
      sample_status: "ESTABLISHED",
      rounds: 1487,
      maps: 40,
      combat_factor: null,
      kpr: null,
      dpr: null,
      expected_kpr: null,
      expected_dpr: null,
      kpr_residual: null,
      negative_dpr_residual: null,
      metric_version: "v0.2-real-2026",
      reference_period_start: null,
      reference_period_end: null,
      interpretation: null,
    }).handle).toBe("Neon");
  });
});
