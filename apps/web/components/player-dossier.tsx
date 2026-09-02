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
};

export function PlayerDossier({ detail, cir }: PlayerDossierProps) {
  const derived = detail.aggregate.derived;
  const kprDelta = kprExpectation(cir?.kpr_residual);
  const deathDelta = deathAvoidanceExpectation(cir?.negative_dpr_residual);

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-6">
      <PlayerHeroCard player={detail.player} cir={cir} />

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
          { label: "ACS", value: formatAcs(detail.stats.acs) },
          { label: "ADR", value: formatAdr(detail.stats.adr) },
          { label: "K/D", value: formatKd(detail.stats.kd) },
          { label: "HS%", value: formatHs(detail.stats.hs_percent) },
        ]}
        opening={[
          {
            label: "Opening frequency",
            value: openingFrequencyDisplay(derived.opening_frequency),
            helper: openingFrequencyHelper(derived.opening_frequency),
          },
          {
            label: "Opening efficiency",
            value: openingEfficiencyDisplay(derived.opening_efficiency),
            helper: openingEfficiencyHelper(derived.opening_efficiency),
          },
          {
            label: "FK/R",
            value: formatRate(derived.fkpr),
            helper: "First kills per round",
            title: "First kills per round",
          },
          {
            label: "FD/R",
            value: formatRate(derived.fdpr),
            helper: "First deaths per round",
            title: "First deaths per round",
          },
        ]}
        support={[
          {
            label: "APR",
            value: formatRate(derived.apr),
            helper: "Assists per round",
          },
          { label: "KAST", value: formatPercent(detail.aggregate.raw.weighted_kast) },
        ]}
        other={[
          {
            label: "Clutch",
            value: formatClutchStat(
              derived.raw_clutch_rate,
              detail.aggregate.raw.clutch_attempts,
            ),
          },
          { label: "Win rate", value: formatWinRate(detail.stats.win_rate) },
        ]}
      />
    </div>
  );
}
