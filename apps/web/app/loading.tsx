export default function Loading() {
  return (
    <div className="space-y-12" aria-busy="true" aria-live="polite">
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="h-4 w-20 rounded bg-muted" />
          <div className="h-12 w-4/5 rounded bg-muted" />
          <div className="h-12 w-3/5 rounded bg-muted" />
          <div className="h-16 w-full max-w-xl rounded bg-muted" />
          <div className="flex gap-2">
            <div className="h-11 w-36 rounded-md bg-muted" />
            <div className="h-11 w-36 rounded-md bg-muted" />
          </div>
        </div>
        <div className="h-64 rounded-xl bg-muted" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="h-14 rounded bg-muted" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="h-44 rounded-xl bg-muted" />
        ))}
      </div>
    </div>
  );
}
