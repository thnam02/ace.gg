import type { HealthResponse } from "@valorant-scout/shared";

import { ActivityIcon } from "@/components/icons";

type StatusBadgeProps = {
  health: HealthResponse | null;
};

export function StatusBadge({ health }: StatusBadgeProps) {
  const label = health ? health.status : "offline";
  const tone =
    label === "ok"
      ? "border-success/30 bg-success/10 text-success"
      : label === "degraded"
        ? "border-warning/30 bg-warning/10 text-warning"
        : "border-border bg-surface-raised text-muted";

  const statusText =
    label === "ok" ? "API online" : label === "degraded" ? "API degraded" : "API offline";

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${tone}`}
      role="status"
      aria-label={statusText}
    >
      <ActivityIcon className="size-3.5" />
      {statusText}
    </span>
  );
}
