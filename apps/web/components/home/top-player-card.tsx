import Link from "next/link";

import { formatCir } from "@/lib/format";
import { reliabilityRoundsLine } from "@/lib/home";
import { playerIdentityLine } from "@/lib/player-cir-copy";
import type { CirRankingPlayer } from "@/lib/types";

type TopPlayerCardProps = {
  player: CirRankingPlayer;
};

export function TopPlayerCard({ player }: TopPlayerCardProps) {
  const identity = playerIdentityLine(player.team?.name, player.role);
  const href = `/players/${player.player_id}`;

  return (
    <article>
      <Link
        href={href}
        aria-label={`View ${player.handle} profile`}
        className="block h-full rounded-xl border border-white/10 bg-card p-4 transition-colors duration-200 hover:border-white/20 hover:bg-muted/20"
      >
        <p className="font-mono text-xs tabular-nums text-muted-foreground">#{player.rank}</p>
        <h3 className="mt-2 font-sans text-lg font-semibold tracking-tight">{player.handle}</h3>
        <p className="mt-1 truncate text-sm text-muted-foreground">{identity}</p>
        <p className="mt-5 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
          CIR
        </p>
        {player.cir == null ? (
          <p className="mt-1 font-mono text-3xl font-semibold text-muted-foreground">
            CIR unavailable
          </p>
        ) : (
          <p
            className="mt-1 font-mono text-3xl font-semibold tabular-nums leading-none text-accent"
            aria-label={`CIR ${formatCir(player.cir)}`}
          >
            {formatCir(player.cir)}
          </p>
        )}
        <p className="mt-4 font-mono text-xs text-muted-foreground">
          {reliabilityRoundsLine(player.reliability, player.rounds)}
        </p>
        <p className="mt-4 text-sm font-medium">View profile →</p>
      </Link>
    </article>
  );
}
