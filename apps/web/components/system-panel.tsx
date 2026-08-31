import { CompareIcon, ServerIcon, UsersIcon } from "@/components/icons";

type SystemPanelProps = {
  apiUrl: string;
  database: string;
  dataSource: string;
  error: string | null;
};

export function SystemPanel({ apiUrl, database, dataSource, error }: SystemPanelProps) {
  return (
    <section className="panel-raised p-5 sm:p-6" aria-labelledby="system-status-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2
            id="system-status-heading"
            className="font-[family-name:var(--font-barlow)] text-lg font-semibold tracking-tight"
          >
            System status
          </h2>
          <p className="mt-1 max-w-xl text-sm leading-6 text-muted">
            Live connection to the scout API and pro data provider.
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted">
          <ServerIcon className="size-3.5" />
          FastAPI backend
        </span>
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        <InfoCell label="API endpoint" value={apiUrl} mono />
        <InfoCell label="Database" value={database} />
        <InfoCell label="Data source" value={dataSource} />
      </dl>

      {error ? (
        <p
          className="mt-4 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-accent"
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}

type ComparePanelProps = {
  playerIds: string[];
};

export function ComparePanel({ playerIds }: ComparePanelProps) {
  if (playerIds.length < 2) {
    return null;
  }

  const compareUrl = `/compare?${playerIds.map((id) => `ids=${encodeURIComponent(id)}`).join("&")}`;

  return (
    <section className="panel border-accent/20 bg-accent-soft/40 p-5 sm:p-6" aria-labelledby="compare-heading">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2
            id="compare-heading"
            className="flex items-center gap-2 font-[family-name:var(--font-barlow)] text-lg font-semibold tracking-tight"
          >
            <CompareIcon className="size-5 text-accent" />
            Compare roster
          </h2>
          <p className="mt-1 text-sm text-muted">
            Side-by-side stats for {playerIds.length} pro players.
          </p>
        </div>
        <a
          href={compareUrl}
          className="focus-ring inline-flex cursor-pointer items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-background transition-opacity hover:opacity-90 motion-reduce:transition-none"
        >
          <UsersIcon className="size-4" />
          Open comparison
        </a>
      </div>
    </section>
  );
}

function InfoCell({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-black/20 px-4 py-3">
      <dt className="text-[11px] font-medium tracking-wide text-muted uppercase">{label}</dt>
      <dd className={`mt-1 text-sm break-all ${mono ? "font-[family-name:var(--font-mono)]" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
