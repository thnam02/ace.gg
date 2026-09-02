export const MIN_COMPARE_PLAYERS = 2;
export const MAX_COMPARE_PLAYERS = 4;
export const MAX_COMPARE_MESSAGE = "You can compare up to 4 players at once.";

export function parseFlag(raw: string | string[] | undefined): boolean {
  if (raw == null) {
    return false;
  }
  const values = Array.isArray(raw) ? raw : [raw];
  return values.some((value) => value === "1" || value === "true");
}

export function parseCompareIds(raw: string | string[] | undefined): string[] {
  if (raw == null) {
    return [];
  }
  const values = Array.isArray(raw) ? raw : [raw];
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const value of values) {
    for (const part of value.split(",")) {
      const id = part.trim();
      if (id && !seen.has(id)) {
        seen.add(id);
        ids.push(id);
      }
    }
  }
  return ids;
}

export function compareHref(ids: string[]): string {
  const params = new URLSearchParams();
  for (const id of ids.slice(0, MAX_COMPARE_PLAYERS)) {
    params.append("ids", id);
  }
  const query = params.toString();
  return query ? `/compare?${query}` : "/compare";
}

export function addCompareId(
  ids: string[],
  id: string,
): { ids: string[]; error: string | null } {
  if (ids.includes(id)) {
    return { ids, error: null };
  }
  if (ids.length >= MAX_COMPARE_PLAYERS) {
    return { ids, error: MAX_COMPARE_MESSAGE };
  }
  return { ids: [...ids, id], error: null };
}

export function removeCompareId(ids: string[], id: string): string[] {
  return ids.filter((value) => value !== id);
}

export function compareEmptyMessage(count: number): string {
  if (count <= 0) {
    return "Select 2–4 players to compare.";
  }
  if (count === 1) {
    return "Add at least one more player.";
  }
  return "";
}

export function compareCardGridClass(count: number): string {
  if (count <= 1) {
    return "grid grid-cols-1 gap-3";
  }
  if (count === 2) {
    return "grid grid-cols-1 gap-3 md:grid-cols-2";
  }
  if (count === 3) {
    return "grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3";
  }
  return "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4";
}

export function compareDensity(count: number): "rich" | "compact" | "dense" {
  if (count <= 2) {
    return "rich";
  }
  if (count === 3) {
    return "compact";
  }
  return "dense";
}

export function pickCompareSearchMatch<T extends { handle: string }>(
  query: string,
  players: T[],
): T | null {
  const needle = query.trim().toLowerCase();
  if (!needle || players.length === 0) {
    return null;
  }
  const exact = players.filter((player) => player.handle.toLowerCase() === needle);
  if (exact.length === 1) {
    return exact[0];
  }
  const prefix = players.filter((player) => player.handle.toLowerCase().startsWith(needle));
  if (prefix.length === 1) {
    return prefix[0];
  }
  const contains = players.filter((player) => player.handle.toLowerCase().includes(needle));
  if (contains.length === 1) {
    return contains[0];
  }
  return null;
}
