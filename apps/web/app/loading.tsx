import { TableSkeleton } from "@/components/table-skeleton";

export default function Loading() {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      <div className="h-6 w-48 rounded bg-muted" />
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="glass-panel h-16 rounded-xl" />
        ))}
      </div>
      <TableSkeleton />
    </div>
  );
}
