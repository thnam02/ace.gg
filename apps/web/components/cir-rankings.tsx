"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
  type FormEvent,
  type ReactNode,
} from "react";
import { ArrowsLeftRightIcon, CaretLeftIcon, CaretRightIcon, XIcon } from "@phosphor-icons/react";

import { PlayerRoleMix } from "@/components/player/player-role-mix";
import { compareHref } from "@/lib/compare";
import { formatCir, formatRate, formatRounds } from "@/lib/format";
import {
  DEFAULT_RANKING_FILTERS,
  RANKING_MIN_ROUNDS_LABELS,
  RANKING_MIN_ROUNDS_OPTIONS,
  RANKING_REGIONS,
  RANKING_ROLES,
  RANKING_SORT_KEYS,
  RANKING_SORT_LABELS,
  RANKING_SORT_ORDERS,
  RANKING_TIERS,
  applyRankingExplore,
  clearRankingExploreSession,
  defaultOrderForSort,
  rankingFiltersActive,
  rankingFiltersEqual,
  rankingHref,
  readRankingExploreSession,
  writeRankingExploreSession,
  type RankingExploreFilters,
  type RankingSortKey,
  type RankingSortOrder,
} from "@/lib/ranking-filters";
import {
  rankingPageBounds,
  rankingPageTokens,
} from "@/lib/ranking-pagination";
import type { CirRankingPlayer, EventSummary } from "@/lib/types";

type CirRankingsProps = {
  players: CirRankingPlayer[];
  total?: number;
  includeProvisional: boolean;
  tooltip: string;
  toggleHref?: { on: string; off: string };
  selectable?: boolean;
  initialSelected?: string[];
  title?: string;
  initialFilters?: RankingExploreFilters;
  events?: EventSummary[];
  eventName?: string | null;
  eventStatus?: string | null;
  eventScoped?: boolean;
};

const controlClass =
  "rounded-md border border-white/10 bg-muted/60 px-2 py-1 text-xs text-foreground";

export function CirRankings({
  players,
  total,
  includeProvisional,
  tooltip,
  toggleHref = { on: "/rankings?include_provisional=1", off: "/rankings" },
  selectable = true,
  initialSelected = [],
  title = "CIR rankings",
  initialFilters = DEFAULT_RANKING_FILTERS,
  events = [],
  eventName = null,
  eventStatus = null,
  eventScoped = false,
}: CirRankingsProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const tableTopRef = useRef<HTMLElement>(null);
  const [selected, setSelected] = useState<string[]>(initialSelected);
  const [draft, setDraft] = useState<RankingExploreFilters>({
    ...initialFilters,
    query: "",
  });
  const [applied, setApplied] = useState<RankingExploreFilters>({
    ...initialFilters,
    query: "",
  });
  const [draftIncludeProvisional, setDraftIncludeProvisional] = useState(
    includeProvisional || eventScoped,
  );
  const [page, setPage] = useState(1);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- sync URL-driven filter props after navigation */
    setDraft({ ...initialFilters, query: draft.query });
    setApplied({ ...initialFilters, query: applied.query });
    setDraftIncludeProvisional(includeProvisional || eventScoped);
    /* eslint-enable react-hooks/set-state-in-effect */
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keep local search text
  }, [initialFilters, includeProvisional, eventScoped]);

  useEffect(() => {
    if (eventScoped) {
      return;
    }
    const stored = readRankingExploreSession();
    if (stored == null) {
      return;
    }
    // Restore after mount so SSR markup does not read sessionStorage.
    /* eslint-disable react-hooks/set-state-in-effect -- persist ranking explore across player pages */
    setDraft((current) => ({
      ...stored.filters,
      eventId: current.eventId,
      query: current.query,
    }));
    setApplied((current) => ({
      ...stored.filters,
      eventId: current.eventId,
      query: current.query,
    }));
    setDraftIncludeProvisional(stored.includeProvisional);
    setPage(stored.page);
    /* eslint-enable react-hooks/set-state-in-effect */
    if (stored.includeProvisional !== includeProvisional) {
      router.replace(stored.includeProvisional ? toggleHref.on : toggleHref.off, {
        scroll: false,
      });
    }
    // Restore once so player-profile navigation does not wipe applied filters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const filtered = useMemo(
    () => applyRankingExplore(players, applied),
    [applied, players],
  );
  const bounds = rankingPageBounds(filtered.length, page);
  const pagePlayers = filtered.slice(bounds.start, bounds.end);
  const pageTokens = rankingPageTokens(bounds.safePage, bounds.totalPages);
  const filtersActive = rankingFiltersActive(applied);
  const draftDirty =
    !rankingFiltersEqual(draft, applied) ||
    (!eventScoped && draftIncludeProvisional !== includeProvisional);
  const canReset =
    filtersActive ||
    (!eventScoped && includeProvisional) ||
    draftDirty ||
    rankingFiltersActive(draft);
  const columnCount = selectable ? (eventScoped ? 11 : 10) : eventScoped ? 10 : 9;
  const upcomingEmpty =
    eventScoped &&
    players.length === 0 &&
    (eventStatus ?? "").toUpperCase() === "UPCOMING";

  const activeChips = useMemo(() => {
    if (!eventScoped) {
      return [] as { key: string; label: string; clear: Partial<RankingExploreFilters> }[];
    }
    const chips: { key: string; label: string; clear: Partial<RankingExploreFilters> }[] = [];
    if (applied.tier) {
      chips.push({ key: "tier", label: applied.tier, clear: { tier: null } });
    }
    if (applied.region) {
      chips.push({ key: "region", label: applied.region, clear: { region: null } });
    }
    if (eventName || applied.eventId) {
      chips.push({
        key: "event",
        label: eventName ?? "Selected event",
        clear: { eventId: null, tier: null, region: null },
      });
    }
    return chips;
  }, [applied.eventId, applied.region, applied.tier, eventName, eventScoped]);

  function updateDraft(patch: Partial<RankingExploreFilters>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function navigateFilters(
    nextFilters: RankingExploreFilters,
    nextInclude: boolean,
  ) {
    const href = rankingHref(nextFilters, { includeProvisional: nextInclude });
    startTransition(() => {
      router.push(href, { scroll: false });
    });
  }

  function updateSearch(query: string) {
    const nextApplied = { ...applied, query };
    setDraft((current) => ({ ...current, query }));
    setApplied(nextApplied);
    setPage(1);
    if (!eventScoped) {
      persistSession(nextApplied, includeProvisional, 1);
    }
  }

  function persistSession(
    nextFilters: RankingExploreFilters,
    nextInclude: boolean,
    nextPage: number,
  ) {
    writeRankingExploreSession({
      filters: { ...nextFilters, eventId: null, query: nextFilters.query },
      includeProvisional: nextInclude,
      page: nextPage,
    });
  }

  function applyFilters(event?: FormEvent) {
    event?.preventDefault();
    if (!draftDirty) {
      return;
    }
    setApplied(draft);
    setPage(1);
    if (!eventScoped) {
      persistSession(draft, draftIncludeProvisional, 1);
    }
    navigateFilters(draft, eventScoped ? true : draftIncludeProvisional);
  }

  function resetFilters() {
    setDraft(DEFAULT_RANKING_FILTERS);
    setApplied(DEFAULT_RANKING_FILTERS);
    setDraftIncludeProvisional(false);
    setPage(1);
    clearRankingExploreSession();
    startTransition(() => {
      router.push("/rankings", { scroll: false });
    });
  }

  function clearChip(clear: Partial<RankingExploreFilters>) {
    const next = { ...applied, ...clear, query: applied.query };
    if (clear.eventId === null) {
      next.eventId = null;
      next.tier = clear.tier === null ? null : next.tier;
      next.region = clear.region === null ? null : next.region;
    }
    setDraft(next);
    setApplied(next);
    setPage(1);
    navigateFilters(next, next.eventId != null || includeProvisional);
  }

  function onEventChange(eventId: string) {
    if (!eventId) {
      const next = { ...draft, eventId: null };
      setDraft(next);
      setApplied(next);
      navigateFilters(next, draftIncludeProvisional);
      return;
    }
    const selectedEvent = events.find((item) => item.id === eventId);
    const next: RankingExploreFilters = {
      ...draft,
      eventId,
      tier: selectedEvent?.tier ?? draft.tier,
      region:
        selectedEvent?.canonical_region ??
        selectedEvent?.region ??
        draft.region,
      minRounds: null,
    };
    setDraft(next);
    setApplied(next);
    setPage(1);
    navigateFilters(next, true);
  }

  function onTierOrRegionChange(patch: Partial<RankingExploreFilters>) {
    const next = {
      ...draft,
      ...patch,
      // Changing tier/region clears event so SSR event options stay coherent.
      eventId: null as string | null,
    };
    setDraft(next);
    setApplied((current) => ({ ...next, query: current.query }));
    setPage(1);
    navigateFilters(next, draftIncludeProvisional);
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
    if (!eventScoped) {
      persistSession(applied, includeProvisional, next);
    }
    tableTopRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  function openCompare() {
    router.push(compareHref(selected));
  }

  function playerHref(playerId: string): string {
    const base = `/players/${encodeURIComponent(playerId)}`;
    if (applied.eventId) {
      return `${base}?event=${encodeURIComponent(applied.eventId)}`;
    }
    return base;
  }

  if (players.length === 0) {
    return (
      <section className="glass-panel overflow-hidden rounded-xl">
        <div className="border-b border-white/10 px-3 py-2">
          <h2 className="text-sm font-medium text-foreground">{title}</h2>
        </div>
        <FilterForm
          draft={draft}
          draftIncludeProvisional={draftIncludeProvisional}
          eventScoped={eventScoped}
          events={events}
          pending={pending}
          draftDirty={draftDirty}
          canReset={canReset}
          onUpdateDraft={updateDraft}
          onTierOrRegionChange={onTierOrRegionChange}
          onEventChange={onEventChange}
          onSearch={updateSearch}
          onToggleProvisional={() =>
            setDraftIncludeProvisional((current) => !current)
          }
          onApply={applyFilters}
          onReset={resetFilters}
        />
        {activeChips.length > 0 ? (
          <ActiveFilterChips chips={activeChips} onClear={clearChip} />
        ) : null}
        <div className="p-4">
          <p className="text-sm text-foreground">
            {upcomingEmpty
              ? "No completed maps yet."
              : eventScoped
                ? "No event CIR scores for this selection."
                : "No established CIR rankings yet."}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {upcomingEmpty
              ? "This event is upcoming. Rankings appear after maps are completed."
              : eventScoped
                ? "This event may lack complete maps, or all players are below the sample filter."
                : "Train CIR v0.2 and generate snapshots, or include provisional players."}
          </p>
        </div>
      </section>
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
      <FilterForm
        draft={draft}
        draftIncludeProvisional={draftIncludeProvisional}
        eventScoped={eventScoped}
        events={events}
        pending={pending}
        draftDirty={draftDirty}
        canReset={canReset}
        onUpdateDraft={updateDraft}
        onTierOrRegionChange={onTierOrRegionChange}
        onEventChange={onEventChange}
        onSearch={updateSearch}
        onToggleProvisional={() =>
          setDraftIncludeProvisional((current) => !current)
        }
        onApply={applyFilters}
        onReset={resetFilters}
      />
      {activeChips.length > 0 ? (
        <ActiveFilterChips chips={activeChips} onClear={clearChip} />
      ) : null}
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
              {eventScoped ? (
                <th scope="col" className="px-3 py-2 font-medium text-right">
                  Sample
                </th>
              ) : null}
              <th scope="col" className="px-3 py-2 font-medium text-right">
                {eventScoped ? "Event rounds" : "Rounds"}
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
                        href={playerHref(player.player_id)}
                        className="font-medium text-foreground underline-offset-2 transition-colors duration-200 hover:text-accent hover:underline"
                      >
                        {player.handle}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      <span>{player.team?.name ?? player.team?.tag ?? "—"}</span>
                      {player.region ? (
                        <span className="block text-[11px]">{player.region}</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-1.5">
                      <PlayerRoleMix role={player.role} roles={player.roles} />
                      {player.tier ? (
                        <span className="block text-[11px] text-muted-foreground">
                          {player.tier}
                        </span>
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
                    {eventScoped ? (
                      <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
                        {player.sample_status ?? "—"}
                      </td>
                    ) : null}
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

type FilterFormProps = {
  draft: RankingExploreFilters;
  draftIncludeProvisional: boolean;
  eventScoped: boolean;
  events: EventSummary[];
  pending: boolean;
  draftDirty: boolean;
  canReset: boolean;
  onUpdateDraft: (patch: Partial<RankingExploreFilters>) => void;
  onTierOrRegionChange: (patch: Partial<RankingExploreFilters>) => void;
  onEventChange: (eventId: string) => void;
  onSearch: (query: string) => void;
  onToggleProvisional: () => void;
  onApply: (event?: FormEvent) => void;
  onReset: () => void;
};

function FilterForm({
  draft,
  draftIncludeProvisional,
  eventScoped,
  events,
  pending,
  draftDirty,
  canReset,
  onUpdateDraft,
  onTierOrRegionChange,
  onEventChange,
  onSearch,
  onToggleProvisional,
  onApply,
  onReset,
}: FilterFormProps) {
  const visibleEvents = events.filter((item) => {
    const status = (item.status ?? "").toUpperCase();
    return status === "COMPLETED" || status === "ONGOING" || status === "UPCOMING" || !status;
  });

  return (
    <form
      className="flex flex-wrap items-end gap-2 border-b border-white/10 px-3 py-2"
      onSubmit={onApply}
    >
      <FilterField label="Search" htmlFor="ranking-search">
        <input
          id="ranking-search"
          type="search"
          value={draft.query}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Handle or team"
          className={`${controlClass} w-44 placeholder:text-muted-foreground`}
        />
      </FilterField>
      <FilterField label="Tier" htmlFor="ranking-tier">
        <select
          id="ranking-tier"
          value={draft.tier ?? ""}
          disabled={pending}
          onChange={(event) =>
            onTierOrRegionChange({ tier: event.target.value || null })
          }
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
          value={draft.region ?? ""}
          disabled={pending}
          onChange={(event) =>
            onTierOrRegionChange({ region: event.target.value || null })
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
      <FilterField label="Event" htmlFor="ranking-event">
        <select
          id="ranking-event"
          value={draft.eventId ?? ""}
          disabled={pending}
          onChange={(event) => onEventChange(event.target.value)}
          className={`${controlClass} min-w-[12rem] max-w-[18rem]`}
        >
          <option value="">All events (2026)</option>
          {visibleEvents.map((item) => {
            const status = (item.status ?? "").toUpperCase();
            const upcoming = status === "UPCOMING";
            return (
              <option key={item.id} value={item.id} disabled={upcoming}>
                {item.name}
                {item.tier ? ` · ${item.tier}` : ""}
                {upcoming ? " · No completed maps yet." : ""}
              </option>
            );
          })}
        </select>
      </FilterField>
      <FilterField label="Role" htmlFor="ranking-role">
        <select
          id="ranking-role"
          value={draft.role ?? ""}
          onChange={(event) => onUpdateDraft({ role: event.target.value || null })}
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
          value={draft.sort}
          onChange={(event) => {
            const sort = event.target.value as RankingSortKey;
            onUpdateDraft({ sort, order: defaultOrderForSort(sort) });
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
          value={draft.order}
          onChange={(event) =>
            onUpdateDraft({ order: event.target.value as RankingSortOrder })
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
      <FilterField label="Minimum rounds" htmlFor="ranking-min-rounds">
        <select
          id="ranking-min-rounds"
          value={draft.minRounds ?? ""}
          onChange={(event) => {
            const raw = event.target.value;
            onUpdateDraft({ minRounds: raw ? Number(raw) : null });
          }}
          className={controlClass}
        >
          {RANKING_MIN_ROUNDS_OPTIONS.map((value) => (
            <option key={value ?? "all"} value={value ?? ""}>
              {value == null
                ? RANKING_MIN_ROUNDS_LABELS.all
                : RANKING_MIN_ROUNDS_LABELS[String(value)]}
            </option>
          ))}
        </select>
      </FilterField>
      {!eventScoped ? (
        <div className="grid gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Include provisional
          </span>
          <button
            type="button"
            onClick={onToggleProvisional}
            className={`${controlClass} inline-flex items-center text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground`}
          >
            {draftIncludeProvisional ? "On" : "Off"}
          </button>
        </div>
      ) : null}
      <div className="grid gap-1">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Apply
        </span>
        <button
          type="submit"
          disabled={!draftDirty || pending}
          className="rounded-md bg-accent px-2 py-1 text-xs font-semibold text-on-accent transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Apply
        </button>
      </div>
      <div className="grid gap-1">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Reset
        </span>
        <button
          type="button"
          onClick={onReset}
          disabled={!canReset || pending}
          className={`${controlClass} text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-muted/60`}
        >
          Reset
        </button>
      </div>
    </form>
  );
}

type ActiveFilterChipsProps = {
  chips: { key: string; label: string; clear: Partial<RankingExploreFilters> }[];
  onClear: (clear: Partial<RankingExploreFilters>) => void;
};

function ActiveFilterChips({ chips, onClear }: ActiveFilterChipsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-white/10 px-3 py-2">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
        Active
      </span>
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          onClick={() => onClear(chip.clear)}
          className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-muted/60 px-2 py-0.5 text-xs text-foreground transition-colors hover:bg-muted"
        >
          {chip.label}
          <XIcon className="size-3" aria-hidden="true" />
          <span className="sr-only">Remove {chip.label} filter</span>
        </button>
      ))}
    </div>
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
