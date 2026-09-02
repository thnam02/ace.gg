import Link from "next/link";

import { PlayerSearch } from "@/components/home/player-search";
import { formatCir } from "@/lib/format";
import {
  HOME_BRAND,
  HOME_HEADLINE_EMPHASIS,
  HOME_HEADLINE_LEAD,
  HOME_SUPPORT,
  compactPercentile,
  compactResidual,
} from "@/lib/home";
import { playerIdentityLine } from "@/lib/player-cir-copy";
import type { CirPlayerDetail, CirRankingPlayer } from "@/lib/types";

type HomeHeroProps = {
  leader: CirRankingPlayer | null;
  leaderCir: CirPlayerDetail | null;
};

export function HomeHero({ leader, leaderCir }: HomeHeroProps) {
  return (
    <section className="grid items-center gap-8 lg:grid-cols-2">
      <div className="min-w-0">
        <p className="font-sans text-sm font-medium tracking-wide text-muted-foreground">
          {HOME_BRAND}
        </p>
        <h1 className="mt-2 max-w-xl font-sans text-[36px] font-semibold leading-[1.1] tracking-tight text-balance sm:text-[44px] lg:text-[56px]">
          {HOME_HEADLINE_LEAD}{" "}
          <span className="block">{HOME_HEADLINE_EMPHASIS}</span>
        </h1>
        <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
          {HOME_SUPPORT}
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link
            href="/rankings"
            className="inline-flex min-h-11 items-center justify-center rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent transition-colors duration-200 hover:bg-accent/90"
          >
            Explore rankings
          </Link>
          <Link
            href="/compare"
            className="inline-flex min-h-11 items-center justify-center rounded-md border border-white/15 px-4 py-2.5 text-sm font-semibold text-foreground transition-colors duration-200 hover:bg-muted"
          >
            Compare players
          </Link>
        </div>
        <div className="mt-5 max-w-xl">
          <PlayerSearch />
        </div>
      </div>
      <HomeHeroPreview leader={leader} leaderCir={leaderCir} />
    </section>
  );
}

export function HomeHeroPreview({ leader, leaderCir }: HomeHeroProps) {
  if (leader == null) {
    return (
      <aside
        aria-label="CIR preview"
        className="rounded-xl border border-white/10 border-l-accent bg-card p-5 sm:p-6"
      >
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">CIR</p>
        <p className="mt-2 font-sans text-xl font-semibold tracking-tight">
          Contextual Impact Rating
        </p>
        <p className="mt-3 font-mono text-4xl font-semibold tabular-nums text-accent">0–100</p>
        <p className="mt-2 text-sm text-muted-foreground">Percentile score</p>
        <p className="mt-4 text-sm text-muted-foreground">
          Role- and tier-adjusted combat performance. Rankings unavailable right now.
        </p>
      </aside>
    );
  }

  const cirValue = leaderCir?.cir ?? leader.cir;
  const identity = playerIdentityLine(leader.team?.name, leader.role);
  const killDelta = compactResidual(leaderCir?.kpr_residual);
  const deathDelta = compactResidual(leaderCir?.negative_dpr_residual);
  const reliability = leaderCir?.reliability ?? leader.reliability;

  return (
    <aside aria-label={`${leader.handle} CIR preview`}>
      <Link
        href={`/players/${leader.player_id}`}
        className="block rounded-xl border border-white/10 border-l-accent bg-card p-5 transition-colors duration-200 hover:border-white/20 hover:bg-muted/20 sm:p-6"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
              Player
            </p>
            <p className="mt-1 truncate font-sans text-xl font-semibold tracking-tight">
              {leader.handle}
            </p>
            <p className="mt-1 truncate text-sm text-muted-foreground">{identity}</p>
          </div>
          <p className="shrink-0 font-mono text-sm tabular-nums text-muted-foreground">
            #{leader.rank}
          </p>
        </div>
        <p className="mt-5 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
          CIR
        </p>
        {cirValue == null ? (
          <p className="mt-1 font-mono text-3xl font-semibold text-muted-foreground">
            CIR unavailable
          </p>
        ) : (
          <>
            <p
              className="mt-1 font-mono text-5xl font-semibold tabular-nums leading-none text-accent"
              aria-label={`CIR ${formatCir(cirValue)}`}
            >
              {formatCir(cirValue)}
            </p>
            <p className="mt-3 text-sm text-muted-foreground">{compactPercentile(cirValue)}</p>
          </>
        )}
        {reliability ? (
          <p className="mt-1 font-mono text-xs uppercase tracking-wide text-muted-foreground">
            {reliability} reliability
          </p>
        ) : null}
        {killDelta || deathDelta ? (
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
            {killDelta ? (
              <div>
                <dt className="text-muted-foreground">Kill production</dt>
                <dd className="mt-0.5 font-mono tabular-nums">{killDelta}</dd>
              </div>
            ) : null}
            {deathDelta ? (
              <div>
                <dt className="text-muted-foreground">Death avoidance</dt>
                <dd className="mt-0.5 font-mono tabular-nums">{deathDelta}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </Link>
    </aside>
  );
}
