import type { HealthResponse } from "@/lib/types";

type StatusBadgeProps = {
  health: HealthResponse | null;
};

export function StatusBadge({ health }: StatusBadgeProps) {
  if (health == null) {
    return (
      <p
        className="inline-flex items-center gap-1.5 rounded-md border border-white/20 bg-muted px-2 py-1 text-xs text-muted-foreground"
        role="status"
      >
        <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
        API unreachable
      </p>
    );
  }

  const healthy = health.status === "ok" && health.database === "connected";
  const label = healthy
    ? "API ok · database connected"
    : `API ${health.status} · database ${health.database}`;

  return (
    <p
      className="inline-flex items-center gap-1.5 rounded-md border border-white/20 bg-muted px-2 py-1 text-xs text-foreground"
      role="status"
    >
      <span
        className={`size-1.5 rounded-full ${healthy ? "bg-accent" : "bg-destructive"}`}
        aria-hidden="true"
      />
      {label}
    </p>
  );
}
