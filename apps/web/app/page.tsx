import type { HealthResponse, PlayerProfile } from "@valorant-scout/shared";

import { getApiUrl, getHealth, getPlayers } from "@/lib/api";

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default async function Home() {
  const apiUrl = getApiUrl();
  let health: HealthResponse | null = null;
  let players: PlayerProfile[] = [];
  let error: string | null = null;

  try {
    [health, players] = await Promise.all([getHealth(), getPlayers()]);
  } catch {
    error = `Could not reach the API at ${apiUrl}. Start the FastAPI server and refresh.`;
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-white/10">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-xs font-semibold tracking-[0.24em] text-accent uppercase">
              VALORANT Scout
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              Player stats and comparison
            </h1>
          </div>
          <StatusBadge health={health} />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-10">
        <section className="rounded-2xl border border-white/10 bg-panel p-6">
          <h2 className="text-lg font-medium">Scaffold status</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/70">
            This first pass uses mock player data only. Riot API integration and
            the custom rating metric are intentionally not implemented yet.
          </p>
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
            <InfoCard label="API" value={apiUrl} />
            <InfoCard label="Database" value={health?.database ?? "unknown"} />
            <InfoCard label="Data source" value="mock provider" />
          </dl>
          {error ? (
            <p className="mt-4 rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">
              {error}
            </p>
          ) : null}
        </section>

        <section>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="text-lg font-medium">Mock players</h2>
              <p className="mt-1 text-sm text-white/60">
                Sample profiles served by <code className="font-mono">GET /players</code>
              </p>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {players.map((player) => (
              <article
                key={player.id}
                className="rounded-2xl border border-white/10 bg-panel p-5"
              >
                <p className="text-xs tracking-[0.16em] text-accent uppercase">
                  {player.rank} · {player.region}
                </p>
                <h3 className="mt-2 text-xl font-semibold">{player.display_name}</h3>
                <p className="font-mono text-sm text-white/55">{player.riot_id}</p>
                <p className="mt-1 text-sm text-white/70">{player.team ?? "Free agent"}</p>
                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <Stat label="ACS" value={player.stats.acs.toFixed(1)} />
                  <Stat label="K/D" value={player.stats.kd.toFixed(2)} />
                  <Stat label="HS%" value={player.stats.hs_percent.toFixed(1)} />
                  <Stat label="Win rate" value={formatPercent(player.stats.win_rate)} />
                </dl>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function StatusBadge({ health }: { health: HealthResponse | null }) {
  const label = health ? health.status : "offline";
  const tone =
    label === "ok"
      ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
      : label === "degraded"
        ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
        : "border-white/15 bg-white/5 text-white/70";

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${tone}`}>
      API {label}
    </span>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-black/25 px-4 py-3">
      <dt className="text-xs tracking-wide text-white/45 uppercase">{label}</dt>
      <dd className="mt-1 font-mono text-sm break-all">{value}</dd>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-white/45">{label}</dt>
      <dd className="font-mono text-base">{value}</dd>
    </div>
  );
}
