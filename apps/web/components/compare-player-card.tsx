"use client";

import { XIcon } from "@phosphor-icons/react";

import { CirPercentileBar } from "@/components/cir-percentile-bar";
import { compareDensity } from "@/lib/compare";
import {
  contextBenchmark,
  deathAvoidanceExpectation,
  kprResidualCopy,
} from "@/lib/player-cir-copy";
import { formatCir, formatRate, formatRounds, teamLabel } from "@/lib/format";
import type { PlayerCompareEntry } from "@/lib/types";

type ComparePlayerCardProps = {
  entry: PlayerCompareEntry;
  count: number;
  onRemove: (id: string) => void;
};

export function ComparePlayerCard({ entry, count, onRemove }: ComparePlayerCardProps) {
  const density = compareDensity(count);
  const cir = entry.cir;
  const cirValue = cir?.cir ?? null;
  const benchmark = contextBenchmark(cir?.tier, cir?.role);
  const rankLabel =
    cir?.rank != null
      ? `#${cir.rank}`
      : cir?.sample_status && cir.sample_status !== "ESTABLISHED"
        ? "Unranked"
        : "Not in established ranking";
  const kprCopy = kprResidualCopy(cir?.kpr_residual);
  const deathCopy = deathAvoidanceExpectation(cir?.negative_dpr_residual).text;
  const cirSize =
    density === "rich" ? "text-5xl" : density === "compact" ? "text-3xl" : "text-2xl";

  return (
    <article className="flex h-full min-w-0 flex-col rounded-xl bg-muted/40 p-3">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold uppercase tracking-wide">
            {entry.player.handle}
          </h2>
          <p className="truncate text-xs text-muted-foreground">
            {teamLabel(entry.player.team?.name ?? null)} · {cir?.role ?? "—"}
          </p>
          {benchmark ? (
            <p className="mt-1 text-xs text-muted-foreground">{benchmark}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => onRemove(entry.player.id)}
          aria-label={`Remove ${entry.player.handle}`}
          className="rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground"
        >
          <XIcon className="size-3.5" aria-hidden="true" />
        </button>
      </header>

      <div className="mt-3">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">CIR</p>
        {cirValue == null ? (
          <p className="mt-1 text-lg font-semibold">CIR unavailable</p>
        ) : (
          <>
            <p className={`mt-1 font-mono font-semibold tabular-nums text-accent ${cirSize}`}>
              {formatCir(cirValue)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{rankLabel}</p>
            <CirPercentileBar cir={cirValue} className="mt-2" />
          </>
        )}
      </div>

      <p className="mt-3 text-xs">
        <span className="font-medium">{cir?.reliability ?? "N/A"}</span>
        <span className="text-muted-foreground"> reliability</span>
        <span className="mt-0.5 block text-muted-foreground">
          {cir ? formatRounds(cir.rounds) : "N/A"} rounds
          {cir?.sample_status ? ` · ${cir.sample_status}` : ""}
        </span>
      </p>

      <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">CIR drivers</p>
        <div>
          <p className="text-xs font-medium">Kill production</p>
          <p className="font-mono text-sm tabular-nums">{formatRate(cir?.kpr)} KPR</p>
          {density !== "dense" ? (
            <p className="text-xs text-muted-foreground">Expected {formatRate(cir?.expected_kpr)}</p>
          ) : null}
          <p className="text-xs">{kprCopy}</p>
        </div>
        <div>
          <p className="text-xs font-medium">Death avoidance</p>
          <p className="font-mono text-sm tabular-nums">{formatRate(cir?.dpr)} DPR</p>
          {density !== "dense" ? (
            <p className="text-xs text-muted-foreground">Expected {formatRate(cir?.expected_dpr)}</p>
          ) : null}
          <p className="text-xs">{deathCopy}</p>
        </div>
      </div>
    </article>
  );
}
