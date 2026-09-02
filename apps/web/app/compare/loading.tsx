export default function Loading() {
  return (
    <div className="space-y-3" aria-busy="true">
      <div className="h-6 w-44 rounded bg-muted" />
      <div className="h-10 rounded-lg bg-muted" />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="h-64 rounded-xl bg-muted" />
        <div className="h-64 rounded-xl bg-muted" />
      </div>
    </div>
  );
}
