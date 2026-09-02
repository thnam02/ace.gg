"use client";

import { useState, type FormEvent } from "react";
import { MagnifyingGlassIcon, PlusIcon, XIcon } from "@phosphor-icons/react";

import { fetchPlayerOptions } from "@/lib/api";
import { MAX_COMPARE_MESSAGE, MAX_COMPARE_PLAYERS, pickCompareSearchMatch } from "@/lib/compare";
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const atLimit = selectedIds.length >= MAX_COMPARE_PLAYERS;

  async function addFromQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const needle = query.trim();
    if (!needle || atLimit || loading) {
      return;
    }
    setLoading(true);
    try {
      const payload = await fetchPlayerOptions({ search: needle, limit: 25 });
      const available = payload.players.filter((player) => !selectedIds.includes(player.id));
      const match = pickCompareSearchMatch(needle, available);
      if (match == null) {
        setError("No matching player. Type a more specific handle.");
        return;
      }
      const message = onAdd(match);
      if (message == null) {
        setQuery("");
        setError(null);
      }
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
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            if (error) {
              setError(null);
            }
          }}
          placeholder="Search player..."
          aria-label="Search player"
          disabled={atLimit}
          aria-busy={loading}
          className="w-full rounded-lg border border-white/10 bg-muted/50 py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
        />
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
