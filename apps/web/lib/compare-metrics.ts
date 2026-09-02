export type CompareDirection = "higher" | "lower" | "neutral";

export function isBestOfSelected(
  values: Array<number | null | undefined>,
  index: number,
  direction: CompareDirection,
): boolean {
  if (direction === "neutral") {
    return false;
  }
  const value = values[index];
  if (value == null) {
    return false;
  }
  const numeric = values.filter((item): item is number => item != null);
  if (numeric.length < 2) {
    return false;
  }
  const best = direction === "higher" ? Math.max(...numeric) : Math.min(...numeric);
  return value === best;
}

export function residualDomain(values: Array<number | null | undefined>): number {
  const numeric = values.filter((item): item is number => item != null);
  if (numeric.length === 0) {
    return 0;
  }
  return Math.max(...numeric.map((value) => Math.abs(value)), 0.01);
}

export function residualBarStyle(
  value: number | null | undefined,
  domain: number,
): { width: string; left: string; side: "neg" | "pos" | "zero" } {
  if (value == null || domain <= 0 || value === 0) {
    return { width: "0%", left: "50%", side: "zero" };
  }
  const ratio = Math.min(Math.abs(value) / domain, 1);
  const widthPct = ratio * 50;
  if (value < 0) {
    return {
      width: `${widthPct}%`,
      left: `${50 - widthPct}%`,
      side: "neg",
    };
  }
  return { width: `${widthPct}%`, left: "50%", side: "pos" };
}
