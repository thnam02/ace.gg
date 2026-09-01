export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="glass-panel overflow-hidden rounded-xl" aria-hidden="true">
      <div className="h-8 border-b border-white/10 bg-muted/40" />
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-9 border-b border-white/5 last:border-b-0 bg-transparent">
          <div className="mx-3 mt-3 h-3 w-2/3 rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}
