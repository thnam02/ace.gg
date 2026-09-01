import { AlertBanner } from "@/components/alert-banner";
import { MetricTiles } from "@/components/metric-tiles";
import { PlayerRoster } from "@/components/player-roster";
import { fetchPlayers } from "@/lib/api";
import { rosterMetrics } from "@/lib/format";
import type { PlayerProfile } from "@/lib/types";

export default async function HomePage() {
  let players: PlayerProfile[] = [];
  let loadError: string | null = null;

  try {
    players = await fetchPlayers();
  } catch {
    players = [];
    loadError = "Could not load the player roster from the API.";
  }

  const metrics = rosterMetrics(players);

  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">Operations dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Roster snapshot from the Scout API. Status in the header is health-check data, not live
          match telemetry.
        </p>
      </header>
      {loadError ? (
        <AlertBanner title={loadError}>
          Start the API on port 8000 and refresh. Until then, this console has no roster to display.
        </AlertBanner>
      ) : null}
      <MetricTiles
        count={metrics.count}
        avgAcs={metrics.avgAcs}
        avgKd={metrics.avgKd}
        avgWinRate={metrics.avgWinRate}
      />
      <PlayerRoster players={players} />
    </div>
  );
}
