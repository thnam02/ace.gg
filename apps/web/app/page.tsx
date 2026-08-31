import { PlayerCard } from "@/components/player-card";
import { SiteHeader } from "@/components/site-header";
import { ComparePanel, SystemPanel } from "@/components/system-panel";
import type { HealthResponse, PlayerProfile } from "@valorant-scout/shared";

import { getApiUrl, getHealth, getPlayers } from "@/lib/api";

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

  const playerIds = players.map((player) => player.id);
  const dataSource = error ? "unavailable" : "vlr.gg via vlrggapi";

  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader health={health} playerCount={players.length} />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6 sm:py-10">
        <SystemPanel
          apiUrl={apiUrl}
          database={health?.database ?? "unknown"}
          dataSource={dataSource}
          error={error}
        />

        <ComparePanel playerIds={playerIds} />

        <section aria-labelledby="roster-heading">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2
                id="roster-heading"
                className="font-[family-name:var(--font-barlow)] text-xl font-semibold tracking-tight sm:text-2xl"
              >
                Pro roster
              </h2>
              <p className="mt-1 text-sm text-muted">
                Player profiles from{" "}
                <code className="rounded bg-surface-raised px-1.5 py-0.5 font-[family-name:var(--font-mono)] text-xs">
                  GET /players
                </code>
              </p>
            </div>
            {!error && players.length > 0 ? (
              <p className="text-xs text-muted">
                Click a VLR profile link to view full match history on vlr.gg
              </p>
            ) : null}
          </div>

          {players.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {players.map((player) => (
                <PlayerCard key={player.id} player={player} />
              ))}
            </div>
          ) : (
            <EmptyRoster error={error} />
          )}
        </section>
      </main>

      <footer className="mt-auto border-t border-border py-6">
        <p className="mx-auto max-w-6xl px-4 text-center text-xs text-muted sm:px-6">
          VALORANT Scout — pro esports analytics. Not affiliated with Riot Games or vlr.gg.
        </p>
      </footer>
    </div>
  );
}

function EmptyRoster({ error }: { error: string | null }) {
  return (
    <div className="panel flex flex-col items-center justify-center px-6 py-16 text-center">
      <p className="font-[family-name:var(--font-barlow)] text-lg font-semibold">
        {error ? "No data available" : "No players loaded"}
      </p>
      <p className="mt-2 max-w-md text-sm text-muted">
        {error
          ? "Start the API and a self-hosted vlrggapi instance, then set DATA_PROVIDER=vlr in your .env."
          : "Configure VLR_DEFAULT_PLAYERS in your API .env to populate the roster."}
      </p>
    </div>
  );
}
