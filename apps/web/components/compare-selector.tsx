"use client";

import { useEffect, useState } from "react";
import { MagnifyingGlassIcon, PlusIcon, XIcon } from "@phosphor-icons/react";

import { fetchPlayerOptions } from "@/lib/api";
import { MAX_COMPARE_MESSAGE, MAX_COMPARE_PLAYERS } from "@/lib/compare";
import { formatCir, formatRounds, teamLabel } from "@/lib/format";
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
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const atLimit = selectedIds.length >= MAX_COMPARE_PLAYERS;

  useEffect(() => {
    const needle = query.trim();
    const handle = window.setTimeout(() => {
      setLoading(true);
      fetchPlayerOptions({ search: needle || undefined, limit: 25 })
        .then((payload) => {
          setResults(payload.players.filter((player) => !selectedIds.includes(player.id)));
          setError(null);
        })
        .catch(() => {
          setError("Could not search players.");
          setResults([]);
        })
        .finally(() => setLoading(false));
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, selectedIds]);

  return (
    <section className="space-y-2">
      <h1 className="text-lg font-semibold tracking-tight">Compare players</h1>
      <p className="text-sm text-muted-foreground">
        Search the full CIR player pool. Rankings stay established-only; compare includes
        provisional and low-sample players.
      </p>
      <div className="relative">
        <MagnifyingGlassIcon
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search player..."
          aria-label="Search player"
          disabled={atLimit}
          className="w-full rounded-lg border border-white/10 bg-muted/50 py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
        />
      </div>
      {atLimit ? (
        <p className="text-xs text-muted-foreground">{MAX_COMPARE_MESSAGE}</p>
      ) : null}
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p className="text-xs text-muted-foreground">Searching…</p> : null}
      {!atLimit && results.length > 0 ? (
        <ul className="max-h-56 overflow-auto rounded-lg bg-muted/40">
          {results.map((player) => (
            <li key={player.id}>
              <button
                type="button"
                onClick={() => {
                  const message = onAdd(player);
                  if (message == null) {
                    setQuery("");
                  }
                }}
                className="flex w-full items-start justify-between gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-muted"
              >
                <span>
                  <span className="block font-medium">{player.handle}</span>
                  <span className="block text-xs text-muted-foreground">
                    {teamLabel(player.team?.name ?? null)} · {player.role ?? "—"}
                  </span>
                </span>
                <span className="shrink-0 text-right font-mono text-xs text-muted-foreground">
                  CIR {formatCir(player.cir)}
                  <span className="mt-0.5 block">
                    {formatRounds(player.rounds)} rounds · {player.sample_status ?? "—"}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
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
