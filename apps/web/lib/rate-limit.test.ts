import { describe, expect, it } from "vitest";

import {
  SlidingWindowRateLimiter,
  checkScoutApiRateLimit,
  clientIpFromHeaders,
  isCompareApiPath,
} from "@/lib/rate-limit";

describe("scout-api rate limit", () => {
  it("blocks after the window fills", () => {
    let now = 1_000;
    const limiter = new SlidingWindowRateLimiter(() => now);
    expect(limiter.hit("ip:all", 2).allowed).toBe(true);
    expect(limiter.hit("ip:all", 2).allowed).toBe(true);
    const blocked = limiter.hit("ip:all", 2);
    expect(blocked.allowed).toBe(false);
    expect(blocked.retryAfterSec).toBeGreaterThan(0);
    now += 60_000;
    expect(limiter.hit("ip:all", 2).allowed).toBe(true);
  });

  it("uses the visitor IP Vercel puts first in x-forwarded-for", () => {
    const headers = new Headers({ "x-forwarded-for": "203.0.113.9, 10.0.0.1" });
    expect(clientIpFromHeaders(headers)).toBe("203.0.113.9");
  });

  it("treats compare routes as the stricter bucket", () => {
    expect(isCompareApiPath(["players", "compare"])).toBe(true);
    expect(isCompareApiPath(["players", "compare", "cir"])).toBe(true);
    expect(isCompareApiPath(["players", "options"])).toBe(false);
  });

  it("applies the compare limit independently", () => {
    const limiter = new SlidingWindowRateLimiter();
    const headers = new Headers({ "x-forwarded-for": "203.0.113.9" });
    const previousCompare = process.env.RATE_LIMIT_COMPARE_PER_MINUTE;
    const previousGeneral = process.env.RATE_LIMIT_PER_MINUTE;
    process.env.RATE_LIMIT_COMPARE_PER_MINUTE = "1";
    process.env.RATE_LIMIT_PER_MINUTE = "50";
    try {
      const first = checkScoutApiRateLimit(headers, ["players", "compare"], limiter);
      const second = checkScoutApiRateLimit(headers, ["players", "compare"], limiter);
      const options = checkScoutApiRateLimit(headers, ["players", "options"], limiter);
      expect(first.allowed).toBe(true);
      expect(second.allowed).toBe(false);
      expect(options.allowed).toBe(true);
    } finally {
      if (previousCompare === undefined) {
        delete process.env.RATE_LIMIT_COMPARE_PER_MINUTE;
      } else {
        process.env.RATE_LIMIT_COMPARE_PER_MINUTE = previousCompare;
      }
      if (previousGeneral === undefined) {
        delete process.env.RATE_LIMIT_PER_MINUTE;
      } else {
        process.env.RATE_LIMIT_PER_MINUTE = previousGeneral;
      }
    }
  });
});
