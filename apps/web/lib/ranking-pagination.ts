export const RANKING_PAGE_SIZE = 50;

export type RankingPageToken = number | "ellipsis";

export function rankingPageCount(
  itemCount: number,
  pageSize = RANKING_PAGE_SIZE,
): number {
  if (itemCount <= 0) {
    return 1;
  }
  return Math.ceil(itemCount / pageSize);
}

export function rankingPageBounds(
  itemCount: number,
  page: number,
  pageSize = RANKING_PAGE_SIZE,
) {
  const totalPages = rankingPageCount(itemCount, pageSize);
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  const end = Math.min(start + pageSize, itemCount);
  return {
    totalPages,
    safePage,
    start,
    end,
    from: itemCount === 0 ? 0 : start + 1,
    to: end,
  };
}

export function rankingPageTokens(
  current: number,
  totalPages: number,
): RankingPageToken[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set<number>([1, totalPages, current, current - 1, current + 1]);
  if (current <= 3) {
    pages.add(2);
    pages.add(3);
  }
  if (current >= totalPages - 2) {
    pages.add(totalPages - 1);
    pages.add(totalPages - 2);
  }

  const sorted = [...pages]
    .filter((value) => value >= 1 && value <= totalPages)
    .sort((left, right) => left - right);
  const tokens: RankingPageToken[] = [];
  for (const value of sorted) {
    const previous = tokens[tokens.length - 1];
    if (typeof previous === "number" && value - previous > 1) {
      tokens.push("ellipsis");
    }
    tokens.push(value);
  }
  return tokens;
}
