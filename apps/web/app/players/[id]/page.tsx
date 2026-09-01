import Link from "next/link";
import type { Metadata } from "next";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react/dist/ssr";

import { AlertBanner } from "@/components/alert-banner";
import { fetchPlayer } from "@/lib/api";
import {
  formatAcs,
  formatAdr,
  formatHs,
  formatKd,
  formatWinRate,
  teamLabel,
} from "@/lib/format";

type PlayerPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PlayerPageProps): Promise<Metadata> {
  const { id } = await params;
  const player = await fetchPlayer(id).catch(() => null);
  return {
    title: player?.display_name ?? "Player not found",
  };
}

export default async function PlayerPage({ params }: PlayerPageProps) {
  const { id } = await params;
  let player;
  try {
    player = await fetchPlayer(id);
  } catch {
    return (
      <AlertBanner title="Could not load this player.">
        The API did not respond. Return to the{" "}
        <Link href="/" className="underline underline-offset-2 hover:text-accent">
          roster
        </Link>
        .
      </AlertBanner>
    );
  }

  if (player == null) {
    return (
      <AlertBanner title={`No player matches “${id}”.`}>
        Check the ID, or go back to the{" "}
        <Link href="/" className="underline underline-offset-2 hover:text-accent">
          roster
        </Link>
        .
      </AlertBanner>
    );
  }

  const stats = [
    { label: "Matches", value: String(player.stats.matches) },
    { label: "ACS", value: formatAcs(player.stats.acs) },
    { label: "K/D", value: formatKd(player.stats.kd) },
    { label: "HS%", value: formatHs(player.stats.hs_percent) },
    { label: "ADR", value: formatAdr(player.stats.adr) },
    { label: "Win rate", value: formatWinRate(player.stats.win_rate) },
  ];

  return (
    <div className="space-y-3">
      <header className="glass-panel rounded-xl p-3">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Player dossier</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{player.display_name}</h1>
            <p className="font-mono text-sm text-muted-foreground">{player.riot_id}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {teamLabel(player.team)} · {player.region} · {player.rank}
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
      <section aria-label="Player stats" className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {stats.map((stat) => (
          <article key={stat.label} className="glass-panel rounded-xl p-3">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{stat.label}</p>
            <p className="mt-1 font-mono text-xl font-semibold tabular-nums">{stat.value}</p>
          </article>
        ))}
      </section>
    </div>
  );
}
