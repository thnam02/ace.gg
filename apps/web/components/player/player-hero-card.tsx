import Link from "next/link";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react/dist/ssr";

import { CirPercentileBar } from "@/components/cir-percentile-bar";
import { PlayerRoleMix } from "@/components/player/player-role-mix";
import { formatCir, formatRounds } from "@/lib/format";
import {
  EVENT_CIR_TOOLTIP,
  EVENT_SCOPE_NOTE,
  METRIC_VERSION_TOOLTIP,
  cirInterpretation,
  cirRankLine,
  contextBenchmark,
  eventRankHeadline,
  eventRankLine,
  metricVersionLabel,
  rankHeadline,
} from "@/lib/player-cir-copy";
import type { CirPlayerDetail, PlayerIdentity } from "@/lib/types";

type PlayerHeroCardProps = {
  player: PlayerIdentity;
  cir: CirPlayerDetail | null;
  eventId?: string | null;
};

export function PlayerHeroCard({ player, cir, eventId = null }: PlayerHeroCardProps) {
  const eventMode = eventId != null;
  const cirValue = cir?.cir ?? null;
  const eventLabel = cir?.scope?.label ?? cir?.note ?? null;
  const rankDisplay = eventMode
    ? eventRankHeadline(cir?.event_rank, cir?.event_player_count)
    : rankHeadline(cir?.rank, cir?.established_count);
  const rankCaption = eventMode
    ? eventRankLine(cir?.event_rank, cir?.event_player_count)
    : cirRankLine(cir?.rank, cir?.established_count, cir?.sample_status);
  const benchmark = contextBenchmark(cir?.tier, cir?.role);
  const versionLabel = metricVersionLabel(cir?.metric_version);
  const cirTooltip = eventMode ? EVENT_CIR_TOOLTIP : METRIC_VERSION_TOOLTIP;

  return (
    <article className="min-w-0 rounded-xl border border-white/10 bg-card p-4 sm:p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {eventMode ? "Event dossier" : "Player dossier"}
          </p>
          <h1 className="mt-1 text-balance text-2xl font-semibold tracking-tight">
            {player.handle}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {player.team?.name?.trim() || "Unattached"}
            {" · "}
            <PlayerRoleMix role={cir?.role} roles={cir?.roles} />
          </p>
          {eventMode && eventLabel ? (
            <p className="mt-2 text-sm font-medium text-foreground">{eventLabel}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start">
          {eventMode ? (
            <Link
              href={`/players/${encodeURIComponent(player.id)}`}
              className="inline-flex shrink-0 items-center rounded-md border border-white/10 bg-muted/60 px-2.5 py-1 text-xs font-semibold text-foreground transition-colors duration-200 hover:bg-muted"
            >
              View 2026 overall
            </Link>
          ) : null}
          <Link
            href={`/compare?ids=${encodeURIComponent(player.id)}`}
            aria-label={`Compare ${player.handle}`}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent transition-colors duration-200 hover:bg-accent/20"
          >
            <ArrowsLeftRightIcon className="size-3.5" aria-hidden="true" />
            Compare player
          </Link>
        </div>
      </header>

      <div className="mt-6 grid gap-6 md:grid-cols-5">
        <div className="min-w-0 md:col-span-3">
          <p id="cir-heading" className="text-[11px] uppercase tracking-wide text-muted-foreground">
            CIR
          </p>
          {cirValue == null ? (
            <p
              className="mt-1 font-mono text-3xl font-semibold tracking-tight text-muted-foreground"
              aria-labelledby="cir-heading"
            >
              CIR unavailable
            </p>
          ) : (
            <>
              <p
                className="mt-1 font-mono text-5xl font-semibold tabular-nums leading-none text-accent"
                aria-labelledby="cir-heading"
                aria-label={`CIR ${formatCir(cirValue)}`}
                title={cirTooltip}
              >
                {formatCir(cirValue)}
              </p>
              <p className="mt-3 text-sm text-muted-foreground" title={cirTooltip}>
                {eventMode ? EVENT_SCOPE_NOTE : cirInterpretation(cirValue)}
              </p>
              {!eventMode ? <CirPercentileBar cir={cirValue} className="mt-4 max-w-lg" /> : null}
            </>
          )}
          {benchmark ? <p className="mt-4 text-sm text-foreground">{benchmark}</p> : null}
        </div>

        <div className="flex min-w-0 flex-col justify-between gap-4 md:col-span-2">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {eventMode ? "Event rank" : "Rank"}
            </p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums leading-none">
              {rankDisplay.rank}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{rankCaption}</p>
          </div>
          <div className="space-y-1 text-sm">
            <p>
              <span className="font-medium">{cir?.reliability ?? "N/A"}</span>
              <span className="text-muted-foreground"> reliability</span>
            </p>
            <p className="text-muted-foreground">
              <span className="font-mono tabular-nums text-foreground">
                {cir ? formatRounds(cir.rounds) : "N/A"}
              </span>{" "}
              {eventMode ? "event rounds" : "rounds"}
              {cir?.sample_status ? (
                <>
                  {" · "}
                  <span className="font-medium text-foreground">{cir.sample_status}</span>
                </>
              ) : null}
            </p>
            <p className="text-xs text-muted-foreground" title={cirTooltip}>
              {eventMode ? EVENT_SCOPE_NOTE : versionLabel}
            </p>
          </div>
        </div>
      </div>
    </article>
  );
}
