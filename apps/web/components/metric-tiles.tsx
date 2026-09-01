import {
  ChartBarIcon,
  CrosshairIcon,
  PercentIcon,
  UsersIcon,
} from "@phosphor-icons/react/dist/ssr";

import { formatAcs, formatKd, formatWinRate } from "@/lib/format";

type MetricTilesProps = {
  count: number;
  avgAcs: number;
  avgKd: number;
  avgWinRate: number;
};

export function MetricTiles({ count, avgAcs, avgKd, avgWinRate }: MetricTilesProps) {
  const tiles = [
    {
      label: "Roster size",
      value: String(count),
      icon: UsersIcon,
    },
    {
      label: "Avg ACS",
      value: count ? formatAcs(avgAcs) : "—",
      icon: ChartBarIcon,
    },
    {
      label: "Avg K/D",
      value: count ? formatKd(avgKd) : "—",
      icon: CrosshairIcon,
    },
    {
      label: "Avg win rate",
      value: count ? formatWinRate(avgWinRate) : "—",
      icon: PercentIcon,
    },
  ];

  return (
    <section aria-label="Roster metrics" className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {tiles.map((tile) => (
        <article key={tile.label} className="glass-panel rounded-xl p-3">
          <p className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tile.icon className="size-3.5" aria-hidden="true" />
            {tile.label}
          </p>
          <p className="mt-1 font-mono text-xl font-semibold tabular-nums text-foreground">
            {tile.value}
          </p>
        </article>
      ))}
    </section>
  );
}
