import { ScoutingStatGroup, type ScoutingStat } from "@/components/player/scouting-stat-group";
import { SCOUTING_DISCLAIMER } from "@/lib/player-cir-copy";

export type { ScoutingStat };

type ScoutingStatsPanelProps = {
  combat: ScoutingStat[];
  opening: ScoutingStat[];
  support: ScoutingStat[];
  other: ScoutingStat[];
};

export function ScoutingStatsPanel({
  combat,
  opening,
  support,
  other,
}: ScoutingStatsPanelProps) {
  return (
    <section
      aria-labelledby="scouting-heading"
      className="rounded-xl border border-white/10 bg-card p-4 sm:p-6"
    >
      <h2 id="scouting-heading" className="text-sm font-medium uppercase tracking-wide">
        Additional scouting stats
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{SCOUTING_DISCLAIMER}</p>
      <ScoutingStatGroup title="Combat" stats={combat} />
      <ScoutingStatGroup title="Opening" stats={opening} />
      <ScoutingStatGroup title="Support" stats={support} />
      <ScoutingStatGroup title="Other" stats={other} />
    </section>
  );
}
