import { describe, expect, it } from "vitest";

import { isBestOfSelected, residualBarStyle, residualDomain } from "@/lib/compare-metrics";

describe("compare metrics", () => {
  it("marks higher residuals as better and leaves opening frequency neutral", () => {
    expect(isBestOfSelected([0.09, 0.12, 0.07], 1, "higher")).toBe(true);
    expect(isBestOfSelected([0.09, 0.12, 0.07], 0, "higher")).toBe(false);
    expect(isBestOfSelected([0.2, 0.4], 1, "neutral")).toBe(false);
    expect(isBestOfSelected([0.12, 0.08], 1, "lower")).toBe(true);
  });

  it("renders negative residuals on the left of a shared scale", () => {
    const domain = residualDomain([0.12, -0.06]);
    const negative = residualBarStyle(-0.06, domain);
    const positive = residualBarStyle(0.12, domain);
    expect(negative.side).toBe("neg");
    expect(positive.side).toBe("pos");
    expect(negative.left).not.toBe("50%");
    expect(positive.left).toBe("50%");
  });
});
