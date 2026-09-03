const DEFAULT_WINDOW_MS = 60_000;
const DEFAULT_GENERAL_LIMIT = 90;
const DEFAULT_COMPARE_LIMIT = 20;

export type RateLimitResult = {
  allowed: boolean;
  retryAfterSec: number;
};

export class SlidingWindowRateLimiter {
  private readonly windows = new Map<string, number[]>();

  constructor(private readonly now: () => number = Date.now) {}

  hit(key: string, limit: number, windowMs: number = DEFAULT_WINDOW_MS): RateLimitResult {
    const now = this.now();
    const cutoff = now - windowMs;
    const hits = (this.windows.get(key) ?? []).filter((stamp) => stamp > cutoff);
    if (hits.length >= limit) {
      const retryAfterSec = Math.max(1, Math.ceil((hits[0]! + windowMs - now) / 1000));
      this.windows.set(key, hits);
      return { allowed: false, retryAfterSec };
    }
    hits.push(now);
    this.windows.set(key, hits);
    return { allowed: true, retryAfterSec: 0 };
  }

  clear(): void {
    this.windows.clear();
  }
}

const limiter = new SlidingWindowRateLimiter();

export function clientIpFromHeaders(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) {
      return first;
    }
  }
  return headers.get("x-real-ip")?.trim() || "unknown";
}

export function isCompareApiPath(pathSegments: string[]): boolean {
  return pathSegments[0] === "players" && pathSegments[1] === "compare";
}

function envLimit(name: string, fallback: number): number {
  const parsed = Number.parseInt(process.env[name] ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function checkScoutApiRateLimit(
  headers: Headers,
  pathSegments: string[],
  instance: SlidingWindowRateLimiter = limiter,
): RateLimitResult {
  const ip = clientIpFromHeaders(headers);
  const compare = isCompareApiPath(pathSegments);
  const limit = compare
    ? envLimit("RATE_LIMIT_COMPARE_PER_MINUTE", DEFAULT_COMPARE_LIMIT)
    : envLimit("RATE_LIMIT_PER_MINUTE", DEFAULT_GENERAL_LIMIT);
  const bucket = compare ? "compare" : "all";
  return instance.hit(`${ip}:${bucket}`, limit);
}

export function resetScoutApiRateLimiter(): void {
  limiter.clear();
}
