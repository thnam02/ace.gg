"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { MagnifyingGlassIcon } from "@phosphor-icons/react";

import { fetchPlayerOptions } from "@/lib/api";
import { playerSearchCirLabel, sampleStatusLabel } from "@/lib/home";
import { playerIdentityLine } from "@/lib/player-cir-copy";
import type { PlayerOption } from "@/lib/types";

export function PlayerSearch() {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerOption[]>([]);
  const [resultsFor, setResultsFor] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needle = query.trim();
  const showResults = needle.length > 0;
  const matchesNeedle = resultsFor === needle;

  useEffect(() => {
    if (!needle) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      void fetchPlayerOptions({ search: needle, limit: 8 })
        .then((payload) => {
          if (cancelled) {
            return;
          }
          setResults(payload.players);
          setResultsFor(needle);
          setError(null);
        })
        .catch(() => {
          if (cancelled) {
            return;
          }
          setError("Could not search players.");
          setResults([]);
          setResultsFor(needle);
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [needle]);

  return (
    <div id="player-search" className="relative">
      <label htmlFor="home-player-search" className="sr-only">
        Search player or team
      </label>
      <MagnifyingGlassIcon
        className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
        aria-hidden="true"
      />
      <input
        id="home-player-search"
        type="search"
        value={query}
        onChange={(event) => {
          const value = event.target.value;
          setQuery(value);
          if (!value.trim()) {
            setResults([]);
            setResultsFor("");
            setError(null);
          }
        }}
        placeholder="Search player or team..."
        aria-label="Search player or team"
        aria-controls={listId}
        aria-expanded={showResults}
        aria-autocomplete="list"
        role="combobox"
        autoComplete="off"
        aria-busy={loading}
        className="w-full rounded-lg border border-white/10 bg-muted/40 py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground"
      />
      {showResults ? (
        <HomeSearchResults
          id={listId}
          players={matchesNeedle ? results : []}
          loading={loading || !matchesNeedle}
          error={matchesNeedle ? error : null}
        />
      ) : null}
    </div>
  );
}

export function HomeSearchResults({
  id,
  players,
  loading,
  error,
}: {
  id: string;
  players: PlayerOption[];
  loading: boolean;
  error: string | null;
}) {
  return (
    <ul
      id={id}
      role="listbox"
      aria-label="Player matches"
      className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-white/10 bg-card py-1 shadow-lg"
    >
      {error ? (
        <li className="px-3 py-2 text-sm text-destructive" role="alert">
          {error}
        </li>
      ) : null}
      {loading && players.length === 0 && !error ? (
        <li className="px-3 py-2 text-sm text-muted-foreground">Searching…</li>
      ) : null}
      {!loading && !error && players.length === 0 ? (
        <li className="px-3 py-2 text-sm text-muted-foreground">No players found.</li>
      ) : null}
      {players.map((player) => {
        const identity = playerIdentityLine(player.team?.name, player.role);
        const status = sampleStatusLabel(player.sample_status);
        return (
          <li key={player.id} role="option" aria-selected={false}>
            <Link
              href={`/players/${player.id}`}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-muted"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{player.handle}</span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {identity}
                  {status ? ` · ${status}` : ""}
                </span>
              </span>
              <span
                className={`shrink-0 font-mono text-xs tabular-nums ${
                  player.cir == null ? "text-muted-foreground" : "text-accent"
                }`}
              >
                {playerSearchCirLabel(player.cir)}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
