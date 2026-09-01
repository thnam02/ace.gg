"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react";

import {
  formatAcs,
  formatAdr,
  formatHs,
  formatKd,
  formatWinRate,
  teamLabel,
} from "@/lib/format";
import type { PlayerProfile } from "@/lib/types";

type PlayerRosterProps = {
  players: PlayerProfile[];
  initialSelected?: string[];
  compareHrefBase?: string;
};

export function PlayerRoster({
  players,
  initialSelected = [],
  compareHrefBase = "/compare",
}: PlayerRosterProps) {
  const router = useRouter();
  const [selected, setSelected] = useState<string[]>(initialSelected);
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  function openCompare() {
    const params = new URLSearchParams();
    for (const id of selected) {
      params.append("ids", id);
    }
    router.push(`${compareHrefBase}?${params.toString()}`);
  }

  if (players.length === 0) {
    return (
      <div className="glass-panel rounded-xl p-4">
        <p className="text-sm text-foreground">No players in the roster yet.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Confirm the API is running, then refresh this page.
        </p>
      </div>
    );
  }

  return (
    <section className="glass-panel overflow-hidden rounded-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
        <h2 className="text-sm font-medium text-foreground">Player roster</h2>
        <button
          type="button"
          onClick={openCompare}
          disabled={selected.length < 2}
          className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowsLeftRightIcon className="size-3.5" aria-hidden="true" />
          Compare {selected.length > 0 ? `(${selected.length})` : ""}
        </button>
      </div>
      {selected.length === 1 ? (
        <p className="border-b border-white/10 px-3 py-1.5 text-xs text-muted-foreground">
          Select one more player to compare.
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-[720px] w-full border-collapse text-left text-sm">
          <caption className="sr-only">Player stats roster</caption>
          <thead className="bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Select
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Player
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Team
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Region
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Rank
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                ACS
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                K/D
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                HS%
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                ADR
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                Win
              </th>
            </tr>
          </thead>
          <tbody>
            {players.map((player) => {
              const checked = selectedSet.has(player.id);
              const checkboxId = `select-${player.id}`;
              return (
                <tr
                  key={player.id}
                  className="border-t border-white/10 transition-colors duration-200 hover:bg-muted/50"
                >
                  <td className="px-3 py-1.5">
                    <input
                      id={checkboxId}
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(player.id)}
                      className="size-3.5 cursor-pointer accent-accent"
                      aria-label={`Select ${player.display_name} for comparison`}
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <Link
                      href={`/players/${encodeURIComponent(player.id)}`}
                      className="font-medium text-foreground underline-offset-2 transition-colors duration-200 hover:text-accent hover:underline"
                    >
                      {player.display_name}
                    </Link>
                    <p className="font-mono text-[11px] text-muted-foreground">{player.riot_id}</p>
                  </td>
                  <td className="px-3 py-1.5 text-muted-foreground">{teamLabel(player.team)}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{player.region}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{player.rank}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatAcs(player.stats.acs)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatKd(player.stats.kd)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatHs(player.stats.hs_percent)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatAdr(player.stats.adr)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatWinRate(player.stats.win_rate)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
