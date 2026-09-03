import { describe, expect, it } from "vitest";

import { CLIENT_API_PREFIX, apiRequestUrl, resolveApiOrigin } from "@/lib/api-origin";

describe("resolveApiOrigin", () => {
  it("skips empty API_URL so the public origin is used", () => {
    expect(
      resolveApiOrigin({
        API_URL: "   ",
        NEXT_PUBLIC_API_URL: "https://acegg-production.up.railway.app/",
      }),
    ).toBe("https://acegg-production.up.railway.app");
  });

  it("prefers a real server API_URL", () => {
    expect(
      resolveApiOrigin({
        API_URL: "http://api:8000",
        NEXT_PUBLIC_API_URL: "https://example.invalid",
      }),
    ).toBe("http://api:8000");
  });

  it("falls back to local API when nothing is set", () => {
    expect(resolveApiOrigin({})).toBe("http://localhost:8000");
  });
});

describe("apiRequestUrl", () => {
  it("uses the same-origin proxy in the browser", () => {
    expect(apiRequestUrl("/players/compare?player_ids=a&player_ids=b", { client: true })).toBe(
      `${CLIENT_API_PREFIX}/players/compare?player_ids=a&player_ids=b`,
    );
  });

  it("calls the API origin on the server", () => {
    expect(
      apiRequestUrl("/health", {
        client: false,
        env: { API_URL: "https://acegg-production.up.railway.app" },
      }),
    ).toBe("https://acegg-production.up.railway.app/health");
  });
});
