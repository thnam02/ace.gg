import { formatCir } from "@/lib/format";
import { clampPercentile, percentileBarLabel } from "@/lib/player-cir-copy";

type CirPercentileBarProps = {
  cir: number;
  className?: string;
  caption?: string;
};

export function CirPercentileBar({ cir, className = "", caption }: CirPercentileBarProps) {
  const clamped = clampPercentile(cir);
  const label = percentileBarLabel(cir);
  const markerShift =
    clamped >= 100 ? "-translate-x-full" : clamped <= 0 ? "translate-x-0" : "-translate-x-1/2";

  return (
    <div className={className}>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Number(clamped.toFixed(1))}
        aria-valuetext={`${formatCir(clamped)} out of 100`}
      >
        <div className="flex justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
          <span>0</span>
          {caption ? <span>{caption}</span> : null}
          <span>100</span>
        </div>
        <div className="relative mt-1 h-1.5 rounded-full bg-muted">
          <div className="h-full rounded-full bg-accent/80" style={{ width: `${clamped}%` }} />
          <span
            className={`absolute top-1/2 size-2 rounded-full bg-accent ${markerShift}`}
            style={{ left: `${clamped}%` }}
            aria-hidden="true"
          />
        </div>
      </div>
      <p className="sr-only">{label}</p>
    </div>
  );
}
