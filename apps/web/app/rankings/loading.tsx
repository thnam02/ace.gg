import { TableSkeleton } from "@/components/table-skeleton";

export default function Loading() {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      <div className="h-6 w-48 rounded bg-muted" />
      <div className="h-4 w-3/4 rounded bg-muted" />
      <TableSkeleton />
    </div>
  );
}
