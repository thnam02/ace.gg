export const CLIENT_API_PREFIX = "/scout-api";

type EnvMap = Record<string, string | undefined>;

function firstUrl(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed.replace(/\/$/, "") : undefined;
}

export function resolveApiOrigin(env: EnvMap = process.env): string {
  return firstUrl(env.API_URL) ?? firstUrl(env.NEXT_PUBLIC_API_URL) ?? "http://localhost:8000";
}

export function apiRequestUrl(
  path: string,
  options?: { client?: boolean; env?: EnvMap },
): string {
  const client = options?.client ?? typeof window !== "undefined";
  if (client) {
    return `${CLIENT_API_PREFIX}${path}`;
  }
  return `${resolveApiOrigin(options?.env)}${path}`;
}
