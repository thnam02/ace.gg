"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowsLeftRightIcon, CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react";

import { compareHref } from "@/lib/compare";
import { formatCir, formatRate, formatRounds } from "@/lib/format";
import {
  DEFAULT_RANKING_FILTERS,
  RANKING_REGIONS,
  RANKING_ROLES,
  RANKING_SORT_KEYS,
  RANKING_SORT_LABELS,
  RANKING_SORT_ORDERS,
  RANKING_TIERS,
  applyRankingExplore,
  defaultOrderForSort,
  rankingFiltersActive,
  type RankingExploreFilters,
  type RankingSortKey,
  type RankingSortOrder,
} from "@/lib/ranking-filters";
import {
  rankingPageBounds,
  rankingPageTokens,
} from "@/lib/ranking-pagination";
import type { CirRankingPlayer } from "@/lib/types";

type CirRankingsProps = {
  players: CirRankingPlayer[];
  total?: number;
  includeProvisional: boolean;
  tooltip: string;
  toggleHref?: { on: string; off: string };
  selectable?: boolean;
  initialSelected?: string[];
  title?: string;
};

const controlClass =
  "rounded-md border border-white/10 bg-muted/60 px-2 py-1 text-xs text-foreground";

export function CirRankings({
  players,
  total,
  includeProvisional,
  tooltip,
  toggleHref = { on: "/?include_provisional=1", off: "/" },
  selectable = true,
  initialSelected = [],
  title = "CIR rankings",
}: CirRankingsProps) {
  const router = useRouter();
  const tableTopRef = useRef<HTMLElement>(null);
  const [selected, setSelected] = useState<string[]>(initialSelected);
  const [filters, setFilters] = useState<RankingExploreFilters>(DEFAULT_RANKING_FILTERS);
  const [page, setPage] = useState(1);
  const [pageScope, setPageScope] = useState(includeProvisional);
  if (includeProvisional !== pageScope) {
    setPageScope(includeProvisional);
    setPage(1);
  }
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const filtered = useMemo(
    () => applyRankingExplore(players, filters),
    [filters, players],
  );
  const bounds = rankingPageBounds(filtered.length, page);
  const pagePlayers = filtered.slice(bounds.start, bounds.end);
  const pageTokens = rankingPageTokens(bounds.safePage, bounds.totalPages);
  const filtersActive = rankingFiltersActive(filters);
  const canReset = filtersActive || includeProvisional;
  const columnCount = selectable ? 10 : 9;

  function updateFilters(patch: Partial<RankingExploreFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
    setPage(1);
  }

  function resetFilters() {
    setFilters(DEFAULT_RANKING_FILTERS);
    setPage(1);
    if (includeProvisional) {
      router.replace(toggleHref.off, { scroll: false });
    }
  }

  function toggle(id: string) {
    setSelected((current) => {
      if (current.includes(id)) {
        return current.filter((value) => value !== id);
      }
      if (current.length >= 4) {
        return current;
      }
      return [...current, id];
    });
  }

  function goToPage(next: number) {
    setPage(next);
    tableTopRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  function openCompare() {
    router.push(compareHref(selected));
  }

  if (players.length === 0) {
    return (
      <div className="glass-panel rounded-xl p-4">
        <p className="text-sm text-foreground">No established CIR rankings yet.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Train CIR v0.2 and generate snapshots, or include provisional players.
        </p>
      </div>
    );
  }

  return (
    <section ref={tableTopRef} className="glass-panel overflow-hidden rounded-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
        <h2 className="text-sm font-medium text-foreground">
          {title}
          <span className="ml-2 font-sans text-xs font-normal text-muted-foreground">
            {filtersActive
              ? `${filtered.length} of ${players.length}`
              : total != null && total > players.length
                ? `${players.length} of ${total}`
                : `${players.length} players`}
          </span>
        </h2>
        {selectable ? (
          <button
            type="button"
            onClick={openCompare}
            disabled={selected.length < 2}
            className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowsLeftRightIcon className="size-3.5" aria-hidden="true" />
            Compare {selected.length > 0 ? `(${selected.length})` : ""}
          </button>
        ) : null}
      </div>
      <div className="flex flex-wrap items-end gap-2 border-b border-white/10 px-3 py-2">
        <FilterField label="Search" htmlFor="ranking-search">
          <input
            id="ranking-search"
            type="search"
            value={filters.query}
            onChange={(event) => updateFilters({ query: event.target.value })}
            placeholder="Handle or team"
            className={`${controlClass} w-44 placeholder:text-muted-foreground`}
          />
        </FilterField>
        <FilterField label="Tier" htmlFor="ranking-tier">
          <select
            id="ranking-tier"
            value={filters.tier ?? ""}
            onChange={(event) => updateFilters({ tier: event.target.value || null })}
            className={controlClass}
          >
            <option value="">All</option>
            {RANKING_TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Region" htmlFor="ranking-region">
          <select
            id="ranking-region"
            value={filters.region ?? ""}
            onChange={(event) =>
              updateFilters({ region: event.target.value || null })
            }
            className={controlClass}
          >
            <option value="">All</option>
            {RANKING_REGIONS.map((region) => (
              <option key={region} value={region}>
                {region}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Role" htmlFor="ranking-role">
          <select
            id="ranking-role"
            value={filters.role ?? ""}
            onChange={(event) => updateFilters({ role: event.target.value || null })}
            className={controlClass}
          >
            <option value="">All</option>
            {RANKING_ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Sort by" htmlFor="ranking-sort">
          <select
            id="ranking-sort"
            value={filters.sort}
            onChange={(event) => {
              const sort = event.target.value as RankingSortKey;
              updateFilters({ sort, order: defaultOrderForSort(sort) });
            }}
            className={controlClass}
          >
            {RANKING_SORT_KEYS.map((key) => (
              <option key={key} value={key}>
                {RANKING_SORT_LABELS[key]}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Order" htmlFor="ranking-order">
          <select
            id="ranking-order"
            value={filters.order}
            onChange={(event) =>
              updateFilters({ order: event.target.value as RankingSortOrder })
            }
            className={controlClass}
          >
            {RANKING_SORT_ORDERS.map((order) => (
              <option key={order} value={order}>
                {order === "desc" ? "High to low" : "Low to high"}
              </option>
            ))}
          </select>
        </FilterField>
        <div className="grid gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Include provisional
          </span>
          <Link
            href={includeProvisional ? toggleHref.off : toggleHref.on}
            className={`${controlClass} inline-flex items-center text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground`}
          >
            {includeProvisional ? "On" : "Off"}
          </Link>
        </div>
        <div className="grid gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Reset
          </span>
          <button
            type="button"
            onClick={resetFilters}
            disabled={!canReset}
            className={`${controlClass} text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-muted/60`}
          >
            Reset
          </button>
        </div>
      </div>
      {selectable && selected.length === 1 ? (
        <p className="border-b border-white/10 px-3 py-1.5 text-xs text-muted-foreground">
          Select one more player to compare.
        </p>
      ) : null}
      {selectable && selected.length >= 4 ? (
        <p className="border-b border-white/10 px-3 py-1.5 text-xs text-muted-foreground">
          You can compare up to 4 players at once.
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-[880px] w-full border-collapse text-left text-sm">
          <caption className="sr-only">CIR player rankings</caption>
          <thead className="bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              {selectable ? (
                <th scope="col" className="px-3 py-2 font-medium">
                  Select
                </th>
              ) : null}
              <th scope="col" className="px-3 py-2 font-medium">
                Rank
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Player
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Team
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Role
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-medium text-right"
                title={tooltip}
              >
                CIR
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                KPR
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                DPR
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                Reliability
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                Rounds
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={columnCount}
                  className="px-3 py-6 text-center text-sm text-muted-foreground"
                >
                  No CIR players match these filters. Reset to see the full ranking
                  pool.
                </td>
              </tr>
            ) : (
              pagePlayers.map((player) => {
                const checked = selectedSet.has(player.player_id);
                const checkboxId = `select-${player.player_id}`;
                return (
                  <tr
                    key={player.player_id}
                    className="border-t border-white/10 transition-colors duration-200 hover:bg-muted/50"
                  >
                    {selectable ? (
                      <td className="px-3 py-1.5">
                        <input
                          id={checkboxId}
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggle(player.player_id)}
                          disabled={selected.length >= 4 && !checked}
                          className="size-3.5 cursor-pointer accent-accent disabled:cursor-not-allowed"
                          aria-label={`Select ${player.handle} for comparison`}
                        />
                      </td>
                    ) : null}
                    <td className="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">
                      {player.rank}
                    </td>
                    <td className="px-3 py-1.5">
                      <Link
                        href={`/players/${encodeURIComponent(player.player_id)}`}
                        className="font-medium text-foreground underline-offset-2 transition-colors duration-200 hover:text-accent hover:underline"
                      >
                        {player.handle}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      <span>{player.team?.tag ?? "—"}</span>
                      {player.region ? (
                        <span className="block text-[11px]">{player.region}</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      <span>{player.role ?? "—"}</span>
                      {player.tier ? (
                        <span className="block text-[11px]">{player.tier}</span>
                      ) : null}
                    </td>
                    <td
                      className="px-3 py-1.5 text-right font-mono text-base font-semibold tabular-nums text-accent"
                      title={tooltip}
                    >
                      {formatCir(player.cir)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                      {formatRate(player.kpr)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                      {formatRate(player.dpr)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
                      {player.reliability ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                      {formatRounds(player.rounds)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {filtered.length > 0 ? (
        <nav
          aria-label="Rankings pages"
          className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-3 py-2"
        >
          <p className="text-xs text-muted-foreground">
            Showing {bounds.from}–{bounds.to} of {filtered.length}
            {bounds.totalPages > 1 ? ` · page ${bounds.safePage} of ${bounds.totalPages}` : ""}
          </p>
          {bounds.totalPages > 1 ? (
            <div className="flex flex-wrap items-center gap-1">
              <PaginationButton
                label="Previous page"
                disabled={bounds.safePage <= 1}
                onClick={() => goToPage(bounds.safePage - 1)}
              >
                <CaretLeftIcon className="size-3.5" aria-hidden="true" />
              </PaginationButton>
              {pageTokens.map((token, index) =>
                token === "ellipsis" ? (
                  <span
                    key={`ellipsis-${index}`}
                    className="px-1 text-xs text-muted-foreground"
                    aria-hidden="true"
                  >
                    …
                  </span>
                ) : (
                  <PaginationButton
                    key={token}
                    current={token === bounds.safePage}
                    label={`Page ${token}`}
                    onClick={() => goToPage(token)}
                  >
                    {token}
                  </PaginationButton>
                ),
              )}
              <PaginationButton
                label="Next page"
                disabled={bounds.safePage >= bounds.totalPages}
                onClick={() => goToPage(bounds.safePage + 1)}
              >
                <CaretRightIcon className="size-3.5" aria-hidden="true" />
              </PaginationButton>
            </div>
          ) : null}
        </nav>
      ) : null}
    </section>
  );
}

type FilterFieldProps = {
  label: string;
  htmlFor: string;
  children: ReactNode;
};

function FilterField({ label, htmlFor, children }: FilterFieldProps) {
  return (
    <label htmlFor={htmlFor} className="grid gap-1">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      {children}
    </label>
  );
}

type PaginationButtonProps = {
  children: ReactNode;
  current?: boolean;
  disabled?: boolean;
  label: string;
  onClick: () => void;
};

function PaginationButton({
  children,
  current = false,
  disabled = false,
  label,
  onClick,
}: PaginationButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-current={current ? "page" : undefined}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex min-h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs tabular-nums transition-colors duration-200 ${
        current
          ? "bg-accent font-semibold text-on-accent"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      } disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-muted-foreground`}
    >
      {children}
    </button>
  );
}
