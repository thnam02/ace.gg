import { TableSkeleton } from "@/components/table-skeleton";

export default function Loading() {
  return (
    <div className="space-y-3" aria-busy="true">
      <div className="h-6 w-44 rounded bg-muted" />
      <TableSkeleton />
    </div>
  );
}
