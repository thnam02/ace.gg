import { describe, expect, it } from "vitest";

import {
  rankingPageBounds,
  rankingPageCount,
  rankingPageTokens,
} from "@/lib/ranking-pagination";

describe("ranking pagination", () => {
  it("splits 343 established players into 7 pages of 50", () => {
    expect(rankingPageCount(343)).toBe(7);
    expect(rankingPageBounds(343, 1)).toMatchObject({
      safePage: 1,
      from: 1,
      to: 50,
      totalPages: 7,
    });
    expect(rankingPageBounds(343, 7)).toMatchObject({
      safePage: 7,
      from: 301,
      to: 343,
    });
  });

  it("clamps out-of-range pages", () => {
    expect(rankingPageBounds(120, 0).safePage).toBe(1);
    expect(rankingPageBounds(120, 99).safePage).toBe(3);
  });

  it("shows every page number when there are few pages", () => {
    expect(rankingPageTokens(1, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("compacts long page lists around the current page", () => {
    expect(rankingPageTokens(1, 10)).toEqual([1, 2, 3, "ellipsis", 10]);
    expect(rankingPageTokens(5, 10)).toEqual([1, "ellipsis", 4, 5, 6, "ellipsis", 10]);
    expect(rankingPageTokens(10, 10)).toEqual([1, "ellipsis", 8, 9, 10]);
  });
});
