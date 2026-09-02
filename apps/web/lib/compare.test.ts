import { describe, expect, it } from "vitest";

import {
  MAX_COMPARE_MESSAGE,
  MAX_COMPARE_PLAYERS,
  addCompareId,
  compareCardGridClass,
  compareDensity,
  compareEmptyMessage,
  compareHref,
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
});
