import { formatCir } from "@/lib/format";
import { clampPercentile, percentileBarLabel } from "@/lib/player-cir-copy";

type CirPercentileBarProps = {
  cir: number;
  className?: string;
};

export function CirPercentileBar({ cir, className = "" }: CirPercentileBarProps) {
  const clamped = clampPercentile(cir);
  const label = percentileBarLabel(cir);
  const markerShift =
    clamped >= 100 ? "-translate-x-full" : clamped <= 0 ? "translate-x-0" : "-translate-x-1/2";

  return (
    <div className={className}>
      <div
        className="flex items-center gap-2"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Number(clamped.toFixed(1))}
        aria-valuetext={`${formatCir(clamped)} out of 100`}
      >
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
          0
        </span>
        <div className="relative h-2 min-w-0 flex-1 rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-accent/40"
            style={{ width: `${clamped}%` }}
          />
          <span
            className={`absolute top-1/2 size-2.5 -translate-y-1/2 rounded-full bg-accent ${markerShift}`}
            style={{ left: `${clamped}%` }}
            aria-hidden="true"
          />
        </div>
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
          100
        </span>
      </div>
      <p className="sr-only">{label}</p>
    </div>
  );
}
