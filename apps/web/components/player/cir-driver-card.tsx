import {
  expectationLabel,
  type ExpectationDirection,
} from "@/lib/player-cir-copy";

type CirDriverCardProps = {
  title: string;
  value: string;
  expected: string;
  delta: string;
  direction: ExpectationDirection;
};

export function CirDriverCard({
  title,
  value,
  expected,
  delta,
  direction,
}: CirDriverCardProps) {
  const qualifier = expectationLabel(direction);
  const tone =
    direction === "above"
      ? "text-accent"
      : direction === "below"
        ? "text-amber-200/90"
        : "text-muted-foreground";

  return (
    <article className="flex h-full min-w-0 flex-col rounded-xl border border-white/10 bg-muted/40 p-4 sm:p-5">
      <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <p className="mt-3 font-mono text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-sm text-muted-foreground">{expected}</p>
      <p className={`mt-3 text-sm ${tone}`}>{delta}</p>
      {qualifier ? <p className={`mt-0.5 text-xs ${tone}`}>{qualifier}</p> : null}
    </article>
  );
}
