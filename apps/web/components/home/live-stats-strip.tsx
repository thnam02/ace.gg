import { HOME_DATASET_NOTE, type HomeLiveStat } from "@/lib/home";

type LiveStatsStripProps = {
  stats: HomeLiveStat[];
  freshness: string;
};

export function LiveStatsStrip({ stats, freshness }: LiveStatsStripProps) {
  if (stats.length === 0) {
    return null;
  }

  return (
    <section aria-label="Platform snapshot" className="border-y border-white/10 py-5">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{stat.label}</dt>
            <dd className="mt-1 font-mono text-xl font-semibold tabular-nums tracking-tight">
              {stat.value}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-muted-foreground">
        {HOME_DATASET_NOTE} {freshness}.
      </p>
    </section>
  );
}
