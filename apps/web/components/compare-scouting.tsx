"use client";

import { useState } from "react";

import { isBestOfSelected, type CompareDirection } from "@/lib/compare-metrics";
import {
  SCOUTING_DISCLAIMER,
  formatClutchStat,
  openingEfficiencyDisplay,
} from "@/lib/player-cir-copy";
import {
  formatAcs,
  formatAdr,
  formatHs,
  formatKd,
  formatPercent,
  formatRate,
} from "@/lib/format";
import type { PlayerCompareEntry } from "@/lib/types";

const TABS = ["Combat", "Opening", "Support", "Other"] as const;
type Tab = (typeof TABS)[number];

type ScoutingRow = {
  label: string;
  display: string[];
  numeric: Array<number | null>;
  direction: CompareDirection;
};

type CompareScoutingProps = {
  players: PlayerCompareEntry[];
  initialTab?: Tab;
};

export function CompareScouting({ players, initialTab = "Combat" }: CompareScoutingProps) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const rows = buildRows(players, tab);

  return (
    <section className="space-y-3 border-t border-white/10 pt-4">
      <div>
        <h2 className="text-sm font-medium uppercase tracking-wide">Additional scouting stats</h2>
        <p className="mt-1 text-sm text-muted-foreground">{SCOUTING_DISCLAIMER}</p>
      </div>
      <div role="tablist" aria-label="Scouting categories" className="flex flex-wrap gap-1">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={tab === item}
            onClick={() => setTab(item)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${
              tab === item ? "bg-accent text-on-accent" : "bg-muted text-muted-foreground"
            }`}
          >
            {item}
          </button>
        ))}
      </div>
      <div className="min-w-0 overflow-x-auto">
        <table className="w-full min-w-[280px] border-collapse text-sm">
          <caption className="sr-only">{tab} scouting comparison</caption>
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="py-1 pr-3 font-medium">
                {tab}
              </th>
              {players.map((entry) => (
                <th key={entry.player.id} scope="col" className="px-2 py-1 font-medium">
                  {entry.player.handle}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-white/10">
                <th
                  scope="row"
                  className="py-2 pr-3 text-left text-xs font-medium text-muted-foreground"
                >
                  {row.label}
                </th>
                {row.display.map((value, index) => (
                  <td
                    key={`${row.label}-${players[index]?.player.id ?? index}`}
                    className="px-2 py-2 font-mono tabular-nums"
                  >
                    {value}
                    {isBestOfSelected(row.numeric, index, row.direction) ? (
                      <span className="mt-0.5 block font-sans text-[10px] uppercase text-muted-foreground">
                        Best of selected
                      </span>
                    ) : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function buildRows(players: PlayerCompareEntry[], tab: Tab): ScoutingRow[] {
  if (tab === "Combat") {
    return [
      row("ACS", players.map((e) => e.stats.acs), formatAcs, "higher"),
      row("ADR", players.map((e) => e.stats.adr), formatAdr, "higher"),
      row("K/D", players.map((e) => e.stats.kd), formatKd, "higher"),
      row("HS%", players.map((e) => e.stats.hs_percent), formatHs, "higher"),
    ];
  }
  if (tab === "Opening") {
    return [
      row(
        "Opening frequency",
        players.map((e) => e.aggregate.derived.opening_frequency),
        formatRate,
        "neutral",
      ),
      row(
        "Opening efficiency",
        players.map((e) => e.aggregate.derived.opening_efficiency),
        openingEfficiencyDisplay,
        "higher",
      ),
      row("FK/R", players.map((e) => e.aggregate.derived.fkpr), formatRate, "higher"),
      row("FD/R", players.map((e) => e.aggregate.derived.fdpr), formatRate, "lower"),
    ];
  }
  if (tab === "Support") {
    return [
      row("Assists per round", players.map((e) => e.aggregate.derived.apr), formatRate, "neutral"),
      row("KAST", players.map((e) => e.aggregate.raw.weighted_kast), formatPercent, "higher"),
    ];
  }
  return [
    {
      label: "Clutch",
      display: players.map((e) =>
        formatClutchStat(e.aggregate.derived.raw_clutch_rate, e.aggregate.raw.clutch_attempts),
      ),
      numeric: players.map(() => null),
      direction: "neutral",
    },
    row(
      "Win rate",
      players.map((e) => e.stats.win_rate),
      (value) => (value == null ? "N/A" : `${(value * 100).toFixed(1)}%`),
      "higher",
    ),
  ];
}

function row(
  label: string,
  numeric: Array<number | null | undefined>,
  format: (value: number | null | undefined) => string,
  direction: CompareDirection,
): ScoutingRow {
  return {
    label,
    display: numeric.map((value) => format(value ?? null)),
    numeric: numeric.map((value) => value ?? null),
    direction,
  };
}
