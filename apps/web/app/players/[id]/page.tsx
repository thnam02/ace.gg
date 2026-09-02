import Link from "next/link";
import type { Metadata } from "next";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react/dist/ssr";

import { AlertBanner } from "@/components/alert-banner";
import { fetchCirMetadata, fetchPlayerCir, fetchPlayerDetail } from "@/lib/api";
import {
  formatAcs,
  formatAdr,
  formatCir,
  formatClutch,
  formatHs,
  formatKd,
  formatPercent,
  formatRate,
  formatRounds,
  formatSignedRate,
  teamLabel,
} from "@/lib/format";

type PlayerPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PlayerPageProps): Promise<Metadata> {
  const { id } = await params;
  const player = await fetchPlayerDetail(id).catch(() => null);
  return {
    title: player?.player.handle ?? "Player not found",
  };
}

export default async function PlayerPage({ params }: PlayerPageProps) {
  const { id } = await params;
  let detail;
  let cir;
  let metadata;
  try {
    [detail, cir, metadata] = await Promise.all([
      fetchPlayerDetail(id),
      fetchPlayerCir(id),
      fetchCirMetadata(),
    ]);
  } catch {
    return (
      <AlertBanner title="Could not load this player.">
        The API did not respond. Return to the{" "}
        <Link href="/" className="underline underline-offset-2 hover:text-accent">
          rankings
        </Link>
        .
      </AlertBanner>
    );
  }

  if (detail == null) {
    return (
      <AlertBanner title={`No player matches “${id}”.`}>
        Check the ID, or go back to the{" "}
        <Link href="/" className="underline underline-offset-2 hover:text-accent">
          rankings
        </Link>
        .
      </AlertBanner>
    );
  }

  const player = detail.player;
  const derived = detail.aggregate.derived;
  const kprDelta = cir?.kpr_residual ?? null;
  const deathAvoidance = cir?.negative_dpr_residual ?? null;
  const cirValue = cir?.cir ?? null;
  const interpretation =
    cirValue == null
      ? "CIR is not available for this player yet."
      : `${formatCir(cirValue)}+ percentile interpretation: ${metadata?.tooltip ?? ""}`;

  const combat = [
    { label: "ACS", value: formatAcs(detail.stats.acs) },
    { label: "ADR", value: formatAdr(detail.stats.adr) },
    { label: "K/D", value: formatKd(detail.stats.kd) },
    { label: "HS%", value: formatHs(detail.stats.hs_percent) },
  ];
  const opening = [
    { label: "Opening frequency", value: formatRate(derived.opening_frequency) },
    { label: "Opening efficiency", value: formatRate(derived.opening_efficiency) },
    { label: "FK/R", value: formatRate(derived.fkpr) },
    { label: "FD/R", value: formatRate(derived.fdpr) },
  ];
  const support = [
    { label: "APR", value: formatRate(derived.apr) },
    { label: "KAST", value: formatPercent(detail.aggregate.raw.weighted_kast) },
  ];
  const other = [
    { label: "Clutch", value: formatClutch(derived.raw_clutch_rate) },
    { label: "Win rate", value: detail.stats.win_rate == null ? "N/A" : `${(detail.stats.win_rate * 100).toFixed(1)}%` },
  ];

  return (
    <div className="space-y-3">
      <header className="glass-panel rounded-xl p-3">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Player dossier</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{player.handle}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {teamLabel(player.team?.name ?? null)} · {cir?.role ?? "—"}
            </p>
          </div>
          <Link
            href={`/compare?ids=${encodeURIComponent(player.id)}`}
            className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-opacity duration-200 hover:opacity-90"
          >
            <ArrowsLeftRightIcon className="size-3.5" aria-hidden="true" />
            Compare from here
          </Link>
        </div>
      </header>

      <section className="glass-panel rounded-xl p-4" aria-label="CIR">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">CIR</p>
        <p className="mt-1 font-mono text-4xl font-semibold tabular-nums text-accent">
          {formatCir(cirValue)}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">{interpretation}</p>
        <p className="mt-2 text-sm">
          Reliability: <span className="font-medium">{cir?.reliability ?? "N/A"}</span>
          {" · "}
          Rounds: <span className="font-mono">{cir ? formatRounds(cir.rounds) : "N/A"}</span>
        </p>
      </section>

      <section className="grid gap-2 md:grid-cols-2" aria-label="Combat performance">
        <article className="glass-panel rounded-xl p-3">
          <h2 className="text-sm font-medium">Kill production</h2>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">
            {formatRate(cir?.kpr)} KPR
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Expected {formatRate(cir?.expected_kpr)} · {formatSignedRate(kprDelta)} vs expected
          </p>
        </article>
        <article className="glass-panel rounded-xl p-3">
          <h2 className="text-sm font-medium">Death avoidance</h2>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">
            {formatRate(cir?.dpr)} DPR
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Expected {formatRate(cir?.expected_dpr)} ·{" "}
            {deathAvoidance == null
              ? "N/A"
              : `${formatRate(Math.abs(deathAvoidance))} ${
                  deathAvoidance >= 0 ? "fewer" : "more"
                } deaths/round than expected`}
          </p>
        </article>
      </section>

      <ScoutingGroup title="Combat" stats={combat} />
      <ScoutingGroup title="Opening" stats={opening} />
      <ScoutingGroup title="Support" stats={support} />
      <ScoutingGroup title="Other" stats={other} />
    </div>
  );
}

function ScoutingGroup({
  title,
  stats,
}: {
  title: string;
  stats: { label: string; value: string }[];
}) {
  return (
    <section aria-label={title}>
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {stats.map((stat) => (
          <article key={stat.label} className="glass-panel rounded-xl p-3">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{stat.label}</p>
            <p className="mt-1 font-mono text-lg font-semibold tabular-nums">{stat.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
