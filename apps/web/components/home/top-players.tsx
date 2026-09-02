import Link from "next/link";

import { TopPlayerCard } from "@/components/home/top-player-card";
import { topPlayersPreview } from "@/lib/home";
import type { CirRankingPlayer } from "@/lib/types";

type TopPlayersProps = {
  players: CirRankingPlayer[];
  error: boolean;
};

export function TopPlayers({ players, error }: TopPlayersProps) {
  const preview = topPlayersPreview(players);

  return (
    <section aria-labelledby="top-players-heading" className="space-y-4">
      <div>
        <h2
          id="top-players-heading"
          className="font-sans text-2xl font-semibold tracking-tight sm:text-[28px]"
        >
          Top CIR Players
        </h2>
        <p className="mt-1 text-sm text-muted-foreground sm:text-base">
          Highest-rated established players in the current 2026 reference.
        </p>
      </div>
      {error ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">Unable to load current rankings.</p>
          <Link
            href="/rankings"
            className="inline-flex min-h-10 items-center rounded-md border border-white/15 px-3 py-2 text-sm font-semibold transition-colors duration-200 hover:bg-muted"
          >
            Open rankings
          </Link>
        </div>
      ) : preview.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No established player rankings are available yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {preview.map((player) => (
            <TopPlayerCard key={player.player_id} player={player} />
          ))}
        </div>
      )}
      {error ? null : (
        <p>
          <Link
            href="/rankings"
            className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
          >
            View all rankings →
          </Link>
        </p>
      )}
    </section>
  );
}
