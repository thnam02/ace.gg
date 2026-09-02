"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react";

import { compareHref } from "@/lib/compare";
import { formatCir, formatRounds } from "@/lib/format";
import type { CirRankingPlayer } from "@/lib/types";

type CirRankingsProps = {
  players: CirRankingPlayer[];
  includeProvisional: boolean;
  tooltip: string;
  toggleHref?: { on: string; off: string };
  selectable?: boolean;
  initialSelected?: string[];
  title?: string;
};

export function CirRankings({
  players,
  includeProvisional,
  tooltip,
  toggleHref = { on: "/?include_provisional=1", off: "/" },
  selectable = true,
  initialSelected = [],
  title = "CIR rankings",
}: CirRankingsProps) {
  const router = useRouter();
  const [selected, setSelected] = useState<string[]>(initialSelected);
  const [query, setQuery] = useState("");
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return players;
    }
    return players.filter((player) => {
      const team = `${player.team?.tag ?? ""} ${player.team?.name ?? ""}`.toLowerCase();
      return (
        player.handle.toLowerCase().includes(needle) ||
        team.includes(needle) ||
        (player.role ?? "").toLowerCase().includes(needle)
      );
    });
  }, [players, query]);

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
    <section className="glass-panel overflow-hidden rounded-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
        <h2 className="text-sm font-medium text-foreground">{title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search handle or team"
            aria-label="Search CIR players"
            className="w-44 rounded-md border border-white/10 bg-muted/60 px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground"
          />
          <Link
            href={includeProvisional ? toggleHref.off : toggleHref.on}
            className="rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
          >
            {includeProvisional ? "Established only" : "Include provisional"}
          </Link>
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
        <table className="min-w-[720px] w-full border-collapse text-left text-sm">
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
                  colSpan={selectable ? 8 : 7}
                  className="px-3 py-6 text-center text-sm text-muted-foreground"
                >
                  No CIR players match this search.
                </td>
              </tr>
            ) : (
              filtered.map((player) => {
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
                      {player.team?.tag ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">{player.role ?? "—"}</td>
                    <td
                      className="px-3 py-1.5 text-right font-mono text-base font-semibold tabular-nums text-accent"
                      title={tooltip}
                    >
                      {formatCir(player.cir)}
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
    </section>
  );
}
