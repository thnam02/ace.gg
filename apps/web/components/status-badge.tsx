import type { HealthResponse } from "@/lib/types";

type StatusBadgeProps = {
  health: HealthResponse | null;
  show?: boolean;
};

export function StatusBadge({ health, show }: StatusBadgeProps) {
  const visible = show ?? process.env.NODE_ENV !== "production";
  if (!visible) {
    return null;
  }

  if (health == null) {
    return (
      <p
        className="inline-flex items-center gap-1 text-[10px] text-muted-foreground"
        role="status"
        aria-label="API unreachable"
      >
        <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
        API
      </p>
    );
  }

  const healthy = health.status === "ok" && health.database === "connected";
  const label = healthy
    ? "API ok · database connected"
    : `API ${health.status} · database ${health.database}`;

  return (
    <p
      className="inline-flex items-center gap-1 text-[10px] text-muted-foreground"
      role="status"
      aria-label={label}
      title={label}
    >
      <span
        className={`size-1.5 rounded-full ${healthy ? "bg-accent" : "bg-destructive"}`}
        aria-hidden="true"
      />
      API
    </p>
  );
}
