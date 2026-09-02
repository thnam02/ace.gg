import { AlertBanner } from "@/components/alert-banner";
import { CirRankings } from "@/components/cir-rankings";
import { fetchCirMetadata, fetchCirRankings } from "@/lib/api";
import { parseFlag } from "@/lib/compare";
import { formatSyncDate } from "@/lib/format";

type HomePageProps = {
  searchParams: Promise<{ include_provisional?: string | string[] }>;
};

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const includeProvisional = parseFlag(params.include_provisional);

  let loadError: string | null = null;
  let rankings = null;
  let metadata = null;
  try {
    [rankings, metadata] = await Promise.all([
      fetchCirRankings({ includeProvisional }),
      fetchCirMetadata(),
    ]);
  } catch {
    loadError = "Could not load CIR rankings from the API.";
  }

  const tooltip =
    metadata?.tooltip ??
    "CIR 90 means the player's validated combat performance ranks around the 90th percentile of the reference population.";

  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">CIR rankings</h1>
        <p className="text-sm text-muted-foreground">
          {metadata?.description ??
            "CIR measures context-adjusted combat performance by combining kill production and death avoidance."}
        </p>
        {formatSyncDate(metadata?.last_data_sync_at) ? (
          <p className="text-xs text-muted-foreground">
            Updated daily · Last sync {formatSyncDate(metadata?.last_data_sync_at)}
          </p>
        ) : null}
      </header>
      {loadError ? (
        <AlertBanner title={loadError}>
          Start the API on port 8000, train CIR v0.2, then refresh.
        </AlertBanner>
      ) : null}
      {rankings ? (
        <>
          <section aria-label="CIR summary" className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            <article className="glass-panel rounded-xl p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {includeProvisional ? "Listed players" : "Established players"}
              </p>
              <p className="mt-1 font-mono text-xl font-semibold tabular-nums">{rankings.total}</p>
            </article>
            <article className="glass-panel rounded-xl p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Metric</p>
              <p className="mt-1 font-mono text-xl font-semibold tabular-nums">CIR</p>
            </article>
            <article className="glass-panel rounded-xl p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Version</p>
              <p className="mt-1 font-mono text-sm font-semibold">{rankings.metric_version}</p>
            </article>
            <article className="glass-panel rounded-xl p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Scale</p>
              <p className="mt-1 font-mono text-xl font-semibold tabular-nums">0–100</p>
            </article>
          </section>
          <CirRankings
            players={rankings.players}
            total={rankings.total}
            includeProvisional={includeProvisional}
            tooltip={tooltip}
          />
        </>
      ) : null}
    </div>
  );
}
