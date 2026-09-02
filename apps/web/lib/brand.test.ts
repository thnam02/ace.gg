import { describe, expect, it } from "vitest";

import { BRAND } from "@/lib/brand";

describe("brand", () => {
  it("keeps the public product name in one place", () => {
    expect(BRAND.name).toBe("ACE.gg");
    expect(BRAND.logoSrc).toBe("/brand/ace-gg-lockup.png");
    expect(BRAND.description).toContain("CIR");
    expect(BRAND.description).not.toContain("VALORANT Scout");
  });
});
