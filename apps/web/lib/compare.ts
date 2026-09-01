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
