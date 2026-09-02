"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { MagnifyingGlassIcon, PlusIcon, XIcon } from "@phosphor-icons/react";

import { fetchPlayerOptions } from "@/lib/api";
import { MAX_COMPARE_MESSAGE, MAX_COMPARE_PLAYERS, pickCompareSearchMatch } from "@/lib/compare";
import { formatCir } from "@/lib/format";
import type { PlayerOption } from "@/lib/types";

type CompareSelectorProps = {
  selectedIds: string[];
  selectedChips: PlayerOption[];
  onAdd: (player: PlayerOption) => string | null;
  onRemove: (id: string) => void;
};

export function CompareSelector({
  selectedIds,
  selectedChips,
  onAdd,
  onRemove,
}: CompareSelectorProps) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const atLimit = selectedIds.length >= MAX_COMPARE_PLAYERS;
  const needle = query.trim();
  const showResults = needle.length > 0 && !atLimit;

  useEffect(() => {
    if (!needle || atLimit) {
      return;
    }
    const timer = window.setTimeout(() => {
      setLoading(true);
      void fetchPlayerOptions({ search: needle, limit: 8 })
        .then((payload) => {
          setResults(payload.players.filter((player) => !selectedIds.includes(player.id)));
          setError(null);
        })
        .catch(() => {
          setError("Could not search players.");
          setResults([]);
        })
        .finally(() => {
          setLoading(false);
        });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [needle, selectedIds, atLimit]);

  function choose(player: PlayerOption) {
    const message = onAdd(player);
    if (message == null) {
      setQuery("");
      setResults([]);
      setError(null);
    } else {
      setError(message);
    }
  }

  async function addFromQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!needle || atLimit || loading) {
      return;
    }
    const match = pickCompareSearchMatch(needle, results) ?? results[0] ?? null;
    if (match != null) {
      choose(match);
      return;
    }
    setLoading(true);
    try {
      const payload = await fetchPlayerOptions({ search: needle, limit: 25 });
      const available = payload.players.filter((player) => !selectedIds.includes(player.id));
      const fetched = pickCompareSearchMatch(needle, available);
      if (fetched == null) {
        setError("No matching player. Type a more specific handle.");
        setResults(available);
        return;
      }
      choose(fetched);
    } catch {
      setError("Could not search players.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-2">
      <h1 className="text-lg font-semibold tracking-tight">Compare players</h1>
      <p className="text-sm text-muted-foreground">
        Search the full CIR player pool. Rankings stay established-only; compare includes
        provisional and low-sample players.
      </p>
      <form className="relative" onSubmit={addFromQuery}>
        <MagnifyingGlassIcon
          className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          value={query}
          onChange={(event) => {
            const value = event.target.value;
            setQuery(value);
            if (!value.trim()) {
              setResults([]);
            }
            if (error) {
              setError(null);
            }
          }}
          placeholder="Search player..."
          aria-label="Search player"
          aria-controls={listId}
          aria-expanded={showResults}
          aria-autocomplete="list"
          role="combobox"
          disabled={atLimit}
          aria-busy={loading}
          autoComplete="off"
          className="w-full rounded-lg border border-white/10 bg-muted/50 py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
        />
        {showResults ? (
          <CompareSearchResults
            id={listId}
            players={results}
            loading={loading}
            query={needle}
            onSelect={choose}
          />
        ) : null}
      </form>
      {atLimit ? (
        <p className="text-xs text-muted-foreground">{MAX_COMPARE_MESSAGE}</p>
      ) : null}
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Selected</span>
        {selectedChips.map((player) => (
          <span
            key={player.id}
            className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-xs"
          >
            {player.handle}
            <button
              type="button"
              onClick={() => onRemove(player.id)}
              aria-label={`Remove ${player.handle}`}
              className="rounded-full p-0.5 hover:bg-background"
            >
              <XIcon className="size-3" aria-hidden="true" />
            </button>
          </span>
        ))}
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <PlusIcon className="size-3" aria-hidden="true" />
          {selectedIds.length} / {MAX_COMPARE_PLAYERS} selected
        </span>
      </div>
    </section>
  );
}

export function CompareSearchResults({
  id,
  players,
  loading,
  query,
  onSelect,
}: {
  id: string;
  players: PlayerOption[];
  loading: boolean;
  query: string;
  onSelect: (player: PlayerOption) => void;
}) {
  return (
    <ul
      id={id}
      role="listbox"
      aria-label="Player matches"
      className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-white/10 bg-card py-1 shadow-lg"
    >
      {loading && players.length === 0 ? (
        <li className="px-3 py-2 text-sm text-muted-foreground">Searching…</li>
      ) : null}
      {!loading && players.length === 0 ? (
        <li className="px-3 py-2 text-sm text-muted-foreground">
          No players match “{query}”.
        </li>
      ) : null}
      {players.map((player) => {
        const team = player.team?.name?.trim() || "Unattached";
        const meta = [team, player.role].filter(Boolean).join(" · ");
        return (
          <li key={player.id} role="option" aria-selected={false}>
            <button
              type="button"
              onClick={() => onSelect(player)}
              className="flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left hover:bg-muted"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{player.handle}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{meta}</span>
              </span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-accent">
                {formatCir(player.cir)}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
