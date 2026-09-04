import { CirDriverCard } from "@/components/player/cir-driver-card";
import { PlayerHeroCard } from "@/components/player/player-hero-card";
import { ScoutingStatsPanel } from "@/components/player/scouting-stats-panel";
import {
  WHY_THIS_SCORE_NOTE,
  deathAvoidanceExpectation,
  formatClutchStat,
  kprExpectation,
  openingEfficiencyDisplay,
  openingEfficiencyHelper,
  openingFrequencyDisplay,
  openingFrequencyHelper,
} from "@/lib/player-cir-copy";
import {
  formatAcs,
  formatAdr,
  formatHs,
  formatKd,
  formatPercent,
  formatRate,
  formatWinRate,
} from "@/lib/format";
import type { CirPlayerDetail, PlayerDetailResponse } from "@/lib/types";

type PlayerDossierProps = {
  detail: PlayerDetailResponse;
  cir: CirPlayerDetail | null;
  eventId?: string | null;
};

export function PlayerDossier({ detail, cir, eventId = null }: PlayerDossierProps) {
  const eventMode = eventId != null;
  const derived = detail.aggregate.derived;
  const kprDelta = kprExpectation(cir?.kpr_residual);
  const deathDelta = deathAvoidanceExpectation(cir?.negative_dpr_residual);

  const openingFrequency = eventMode
    ? (cir?.opening_frequency ?? derived.opening_frequency)
    : derived.opening_frequency;
  const openingEfficiency = eventMode
    ? (cir?.opening_efficiency ?? derived.opening_efficiency)
    : derived.opening_efficiency;
  const fkpr = eventMode ? (cir?.fk_per_round ?? derived.fkpr) : derived.fkpr;
  const fdpr = eventMode ? (cir?.fd_per_round ?? derived.fdpr) : derived.fdpr;
  const apr = eventMode ? (cir?.apr ?? derived.apr) : derived.apr;
  const kast = eventMode
    ? (cir?.kast ?? detail.aggregate.raw.weighted_kast)
    : detail.aggregate.raw.weighted_kast;
  const clutch = eventMode ? (cir?.clutch ?? derived.raw_clutch_rate) : derived.raw_clutch_rate;
  const acs = eventMode ? (cir?.acs ?? detail.stats.acs) : detail.stats.acs;
  const adr = eventMode ? (cir?.adr ?? detail.stats.adr) : detail.stats.adr;
  const kd = eventMode ? (cir?.kd ?? detail.stats.kd) : detail.stats.kd;
  const hs = eventMode ? (cir?.hs_pct ?? detail.stats.hs_percent) : detail.stats.hs_percent;
  const winRate = eventMode ? (cir?.win_rate ?? detail.stats.win_rate) : detail.stats.win_rate;

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-6">
      <PlayerHeroCard player={detail.player} cir={cir} eventId={eventId} />

      <section aria-labelledby="why-score-heading" className="space-y-3">
        <div>
          <h2 id="why-score-heading" className="text-sm font-medium uppercase tracking-wide">
            Why this score
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{WHY_THIS_SCORE_NOTE}</p>
        </div>
        <div className="grid grid-cols-1 items-stretch gap-3 md:grid-cols-2">
          <CirDriverCard
            title="Kill production"
            value={`${formatRate(cir?.kpr)} KPR`}
            expected={`Expected ${formatRate(cir?.expected_kpr)}`}
            delta={kprDelta.text}
            direction={kprDelta.direction}
          />
          <CirDriverCard
            title="Death avoidance"
            value={`${formatRate(cir?.dpr)} DPR`}
            expected={`Expected ${formatRate(cir?.expected_dpr)}`}
            delta={deathDelta.text}
            direction={deathDelta.direction}
          />
        </div>
      </section>

      <ScoutingStatsPanel
        combat={[
          { label: "ACS", value: formatAcs(acs) },
          { label: "ADR", value: formatAdr(adr) },
          { label: "K/D", value: formatKd(kd) },
          { label: "HS%", value: formatHs(hs) },
        ]}
        opening={[
          {
            label: "Opening frequency",
            value: openingFrequencyDisplay(openingFrequency),
            helper: openingFrequencyHelper(openingFrequency),
          },
          {
            label: "Opening efficiency",
            value: openingEfficiencyDisplay(openingEfficiency),
            helper: openingEfficiencyHelper(openingEfficiency),
          },
          {
            label: "FK/R",
            value: formatRate(fkpr),
            helper: "First kills per round",
            title: "First kills per round",
          },
          {
            label: "FD/R",
            value: formatRate(fdpr),
            helper: "First deaths per round",
            title: "First deaths per round",
          },
        ]}
        support={[
          {
            label: "APR",
            value: formatRate(apr),
            helper: "Assists per round",
          },
          { label: "KAST", value: formatPercent(kast) },
        ]}
        other={[
          {
            label: "Clutch",
            value: formatClutchStat(
              clutch,
              eventMode ? null : detail.aggregate.raw.clutch_attempts,
            ),
          },
          { label: "Win rate", value: formatWinRate(winRate) },
        ]}
      />
    </div>
  );
}
