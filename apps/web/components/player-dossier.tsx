import Link from "next/link";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react/dist/ssr";

import { CirPercentileBar } from "@/components/cir-percentile-bar";
import {
  WHY_THIS_SCORE_NOTE,
  METRIC_VERSION_TOOLTIP,
  SCOUTING_DISCLAIMER,
  cirInterpretation,
  cirRankLine,
  contextBenchmark,
  deathAvoidanceExpectation,
  expectationLabel,
  formatClutchStat,
  kprExpectation,
  metricVersionLabel,
  openingEfficiencyDisplay,
  openingEfficiencyHelper,
  openingFrequencyHelper,
  rankHeadline,
} from "@/lib/player-cir-copy";
import {
  formatAcs,
  formatAdr,
  formatCir,
  formatHs,
  formatKd,
  formatPercent,
  formatRate,
  formatRounds,
  teamLabel,
} from "@/lib/format";
import type { CirPlayerDetail, PlayerDetailResponse } from "@/lib/types";

type PlayerDossierProps = {
  detail: PlayerDetailResponse;
  cir: CirPlayerDetail | null;
};

type ScoutingStat = {
  label: string;
  value: string;
  helper?: string | null;
  title?: string;
};

export function PlayerDossier({ detail, cir }: PlayerDossierProps) {
  const player = detail.player;
  const derived = detail.aggregate.derived;
  const cirValue = cir?.cir ?? null;
  const interpretation = cirInterpretation(cirValue);
  const benchmark = contextBenchmark(cir?.tier, cir?.role);
  const rankCopy = cirRankLine(cir?.rank, cir?.established_count, cir?.sample_status);
  const rankDisplay = rankHeadline(cir?.rank, cir?.established_count);
  const kprDelta = kprExpectation(cir?.kpr_residual);
  const deathDelta = deathAvoidanceExpectation(cir?.negative_dpr_residual);
  const versionLabel = metricVersionLabel(cir?.metric_version);
  const clutchValue = formatClutchStat(
    derived.raw_clutch_rate,
    detail.aggregate.raw.clutch_attempts,
  );

  const combat: ScoutingStat[] = [
    { label: "ACS", value: formatAcs(detail.stats.acs) },
    { label: "ADR", value: formatAdr(detail.stats.adr) },
    { label: "K/D", value: formatKd(detail.stats.kd) },
    { label: "HS%", value: formatHs(detail.stats.hs_percent) },
  ];
  const opening: ScoutingStat[] = [
    {
      label: "Opening frequency",
      value: formatRate(derived.opening_frequency),
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
      title: "First kills per round",
    },
    {
      label: "FD/R",
      value: formatRate(derived.fdpr),
      title: "First deaths per round",
    },
  ];
  const support: ScoutingStat[] = [
    { label: "APR", value: formatRate(derived.apr) },
    { label: "KAST", value: formatPercent(detail.aggregate.raw.weighted_kast) },
  ];
  const other: ScoutingStat[] = [
    { label: "Clutch", value: clutchValue },
    {
      label: "Win rate",
      value:
        detail.stats.win_rate == null
          ? "N/A"
          : `${(detail.stats.win_rate * 100).toFixed(1)}%`,
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Player dossier
          </p>
          <h1 className="mt-0.5 text-2xl font-semibold tracking-tight">{player.handle}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {teamLabel(player.team?.name ?? null)} · {cir?.role ?? "—"}
          </p>
        </div>
        <Link
          href={`/compare?ids=${encodeURIComponent(player.id)}`}
          aria-label={`Compare ${player.handle}`}
          className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-opacity duration-200 hover:opacity-90"
        >
          <ArrowsLeftRightIcon className="size-3.5" aria-hidden="true" />
          Compare player
        </Link>
      </header>

      <section
        aria-labelledby="cir-heading"
        className="grid gap-4 border-b border-white/10 pb-4 md:grid-cols-2 md:items-stretch"
      >
        <div className="min-w-0">
          <p id="cir-heading" className="text-[11px] uppercase tracking-wide text-muted-foreground">
            CIR
          </p>
          <p className="mt-1 font-mono text-5xl font-semibold tabular-nums leading-none text-accent">
            {formatCir(cirValue)}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">{interpretation}</p>
          {cirValue != null ? (
            <CirPercentileBar cir={cirValue} className="mt-3 max-w-md" caption="Percentile score" />
          ) : null}
          {benchmark ? (
            <p className="mt-2 text-sm text-foreground">{benchmark}</p>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col justify-between gap-3 md:border-l md:border-white/10 md:pl-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Rank</p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums leading-none">
              {rankDisplay.rank}
              {rankDisplay.of ? (
                <span className="ml-1 text-lg font-medium text-muted-foreground">
                  {rankDisplay.of}
                </span>
              ) : null}
            </p>
            {rankCopy ? <p className="mt-1 text-sm text-muted-foreground">{rankCopy}</p> : null}
          </div>
          <div className="space-y-1 text-sm">
            <p>
              <span className="text-muted-foreground">Reliability </span>
              <span className="font-medium">{cir?.reliability ?? "N/A"}</span>
            </p>
            <p className="text-muted-foreground">
              <span className="font-mono tabular-nums text-foreground">
                {cir ? formatRounds(cir.rounds) : "N/A"}
              </span>{" "}
              rounds
              {cir?.sample_status ? (
                <>
                  {" · "}
                  <span className="font-medium text-foreground">{cir.sample_status}</span>
                </>
              ) : null}
            </p>
            <p className="text-xs text-muted-foreground" title={METRIC_VERSION_TOOLTIP}>
              {versionLabel}
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="why-score-heading" className="space-y-2">
        <div>
          <h2 id="why-score-heading" className="text-sm font-medium uppercase tracking-wide">
            Why this score
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">{WHY_THIS_SCORE_NOTE}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <ExpectationCard
            title="Kill production"
            value={`${formatRate(cir?.kpr)} KPR`}
            expected={`Expected ${formatRate(cir?.expected_kpr)}`}
            delta={kprDelta.text}
            direction={kprDelta.direction}
          />
          <ExpectationCard
            title="Death avoidance"
            value={`${formatRate(cir?.dpr)} DPR`}
            expected={`Expected ${formatRate(cir?.expected_dpr)}`}
            delta={deathDelta.text}
            direction={deathDelta.direction}
          />
        </div>
      </section>

      <section aria-labelledby="scouting-heading" className="space-y-3 border-t border-white/10 pt-4">
        <div>
          <h2 id="scouting-heading" className="text-sm font-medium uppercase tracking-wide">
            Additional scouting stats
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{SCOUTING_DISCLAIMER}</p>
        </div>
        <ScoutingGroup title="Combat" stats={combat} />
        <ScoutingGroup title="Opening" stats={opening} />
        <ScoutingGroup title="Support" stats={support} />
        <ScoutingGroup title="Other" stats={other} />
      </section>
    </div>
  );
}

function ExpectationCard({
  title,
  value,
  expected,
  delta,
  direction,
}: {
  title: string;
  value: string;
  expected: string;
  delta: string;
  direction: ReturnType<typeof kprExpectation>["direction"];
}) {
  const qualifier = expectationLabel(direction);
  return (
    <article className="min-w-0 rounded-lg bg-muted/40 p-3">
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-sm text-muted-foreground">{expected}</p>
      <p className="mt-1 text-sm">
        {delta}
        {qualifier ? (
          <span className="mt-0.5 block text-xs text-muted-foreground">{qualifier}</span>
        ) : null}
      </p>
    </article>
  );
}

function ScoutingGroup({ title, stats }: { title: string; stats: ScoutingStat[] }) {
  return (
    <section aria-label={title}>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="grid grid-cols-2 gap-x-3 gap-y-3 md:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="min-w-0" {...(stat.title ? { title: stat.title } : {})}>
            <p
              className="text-[11px] uppercase tracking-wide text-muted-foreground"
              {...(stat.title ? { title: stat.title } : {})}
            >
              {stat.label}
            </p>
            <p className="mt-0.5 font-mono text-lg font-semibold tabular-nums">{stat.value}</p>
            {stat.helper ? (
              <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{stat.helper}</p>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
