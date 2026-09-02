import Link from "next/link";

import { formatCir, formatRounds } from "@/lib/format";
import type { CirRankingPlayer } from "@/lib/types";

type CirRankingsProps = {
  players: CirRankingPlayer[];
  includeProvisional: boolean;
  tooltip: string;
  toggleHref?: { on: string; off: string };
};

export function CirRankings({
  players,
  includeProvisional,
  tooltip,
  toggleHref = { on: "/?include_provisional=1", off: "/" },
}: CirRankingsProps) {
  if (players.length === 0) {
    return (
      <div className="glass-panel rounded-xl p-4">
        <p className="text-sm text-foreground">No established CIR rankings yet.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Train CIR v0.2 and generate snapshots, or include provisional players.
        </p>
      </div>
    );
  }

  return (
    <section className="glass-panel overflow-hidden rounded-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
        <h2 className="text-sm font-medium text-foreground">CIR rankings</h2>
        <Link
          href={includeProvisional ? toggleHref.off : toggleHref.on}
          className="rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
        >
          {includeProvisional ? "Established only" : "Include provisional"}
        </Link>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-[720px] w-full border-collapse text-left text-sm">
          <caption className="sr-only">CIR player rankings</caption>
          <thead className="bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Rank
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Player
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Team
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Role
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-medium text-right"
                title={tooltip}
              >
                CIR
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                Reliability
              </th>
              <th scope="col" className="px-3 py-2 font-medium text-right">
                Rounds
              </th>
            </tr>
          </thead>
          <tbody>
            {players.map((player) => (
              <tr
                key={player.player_id}
                className="border-t border-white/10 transition-colors duration-200 hover:bg-muted/50"
              >
                <td className="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">
                  {player.rank}
                </td>
                <td className="px-3 py-1.5">
                  <Link
                    href={`/players/${encodeURIComponent(player.player_id)}`}
                    className="font-medium text-foreground underline-offset-2 transition-colors duration-200 hover:text-accent hover:underline"
                  >
                    {player.handle}
                  </Link>
                </td>
                <td className="px-3 py-1.5 text-muted-foreground">
                  {player.team?.tag ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-muted-foreground">{player.role ?? "—"}</td>
                <td
                  className="px-3 py-1.5 text-right font-mono text-base font-semibold tabular-nums text-accent"
                  title={tooltip}
                >
                  {formatCir(player.cir)}
                </td>
                <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
                  {player.reliability ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                  {formatRounds(player.rounds)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
