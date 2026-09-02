import { isBestOfSelected, residualBarStyle, residualDomain } from "@/lib/compare-metrics";
import { formatSignedRate } from "@/lib/format";
import type { PlayerCompareEntry } from "@/lib/types";

type CompareDriversProps = {
  players: PlayerCompareEntry[];
};

export function CompareDrivers({ players }: CompareDriversProps) {
  const kprResiduals = players.map((entry) => entry.cir?.kpr_residual ?? null);
  const deathResiduals = players.map((entry) => entry.cir?.negative_dpr_residual ?? null);

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium uppercase tracking-wide">CIR driver comparison</h2>
      <p className="text-xs text-muted-foreground">
        Bars compare residuals vs each player&apos;s own role+tier expectation, not raw KPR/DPR.
      </p>
      <ResidualGroup title="Kill production vs expectation" players={players} values={kprResiduals} />
      <ResidualGroup
        title="Death avoidance vs expectation"
        players={players}
        values={deathResiduals}
      />
    </section>
  );
}

function ResidualGroup({
  title,
  players,
  values,
}: {
  title: string;
  players: PlayerCompareEntry[];
  values: Array<number | null>;
}) {
  const domain = residualDomain(values);
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h3>
      <div className="space-y-2">
        {players.map((entry, index) => {
          const value = values[index] ?? null;
          const bar = residualBarStyle(value, domain);
          const best = isBestOfSelected(values, index, "higher");
          return (
            <div key={entry.player.id} className="min-w-0">
              <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                <span className="truncate font-medium">{entry.player.handle}</span>
                <span className="font-mono tabular-nums">
                  {formatSignedRate(value)}
                  {best ? (
                    <span className="ml-2 font-sans text-[10px] uppercase text-muted-foreground">
                      Best of selected
                    </span>
                  ) : null}
                </span>
              </div>
              <div className="relative h-2 overflow-hidden rounded-full bg-muted">
                <span
                  className="absolute inset-y-0 w-px bg-white/40"
                  style={{ left: "50%" }}
                  aria-hidden="true"
                />
                <span
                  className={`absolute top-0 h-full rounded-full ${
                    bar.side === "neg" ? "bg-destructive/70" : "bg-accent/80"
                  }`}
                  style={{ left: bar.left, width: bar.width }}
                  aria-hidden="true"
                />
              </div>
              <p className="sr-only">
                {entry.player.handle}: {formatSignedRate(value)}
                {bar.side === "neg" ? " below expectation" : ""}
                {bar.side === "pos" ? " above expectation" : ""}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
