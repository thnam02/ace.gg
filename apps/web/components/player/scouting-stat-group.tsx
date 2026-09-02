export type ScoutingStat = {
  label: string;
  value: string;
  helper?: string | null;
  title?: string;
};

type ScoutingStatGroupProps = {
  title: string;
  stats: ScoutingStat[];
};

export function ScoutingStatGroup({ title, stats }: ScoutingStatGroupProps) {
  return (
    <section aria-label={title} className="mt-5 border-t border-white/10 pt-5">
      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 min-[400px]:grid-cols-2 md:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="min-w-0" {...(stat.title ? { title: stat.title } : {})}>
            <p
              className="text-[11px] uppercase tracking-wide text-muted-foreground"
              {...(stat.title ? { title: stat.title } : {})}
            >
              {stat.label}
            </p>
            <p className="mt-1 font-mono text-lg font-semibold tabular-nums">{stat.value}</p>
            {stat.helper ? (
              <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                {stat.helper}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
