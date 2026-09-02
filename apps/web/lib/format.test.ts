import { describe, expect, it } from "vitest";

import { formatCir } from "@/lib/format";

describe("formatCir", () => {
  it("keeps true 100 at 100 and does not round 99.x up", () => {
    expect(formatCir(100)).toBe("100");
    expect(formatCir(99.96)).toBe("100");
    expect(formatCir(99.8)).toBe("99.8");
    expect(formatCir(87.4)).toBe("87.4");
    expect(formatCir(48.6)).toBe("48.6");
    expect(formatCir(22.5)).toBe("22.5");
    expect(formatCir(90)).toBe("90");
  });
});
