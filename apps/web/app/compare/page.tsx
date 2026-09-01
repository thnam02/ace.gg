import type { Metadata } from "next";

import { AlertBanner } from "@/components/alert-banner";
import { CompareView } from "@/components/compare-view";
import { PlayerRoster } from "@/components/player-roster";
import { fetchComparison, fetchPlayers } from "@/lib/api";
import { parseCompareIds } from "@/lib/compare";

export const metadata: Metadata = {
  title: "Compare",
};

type ComparePageProps = {
  searchParams: Promise<{ ids?: string | string[] }>;
};

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const params = await searchParams;
  const ids = parseCompareIds(params.ids);

  let roster;
  try {
    roster = await fetchPlayers();
  } catch {
    return (
      <AlertBanner title="Could not load players for comparison.">
        Start the API on port 8000, then refresh this page.
      </AlertBanner>
    );
  }

  let comparison = null;
  let compareError: string | null = null;
  if (ids.length >= 2) {
    try {
      comparison = await fetchComparison(ids);
    } catch {
      compareError = "The comparison request failed. Check the selected IDs and try again.";
    }
  }

  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">Compare players</h1>
        <p className="text-sm text-muted-foreground">
          Select two or more players. The table is the source of truth; bars are a visual aid with
          labeled values.
        </p>
      </header>
      <PlayerRoster players={roster} initialSelected={ids} />
      {ids.length < 2 ? (
        <div className="glass-panel rounded-xl p-4">
          <p className="text-sm text-foreground">Two players are required to compare.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Tick names in the roster, then use Compare. You can also open a player dossier and
            start from there.
          </p>
        </div>
      ) : null}
      {compareError ? <AlertBanner title={compareError} /> : null}
      {comparison && comparison.players.length > 0 ? (
        <CompareView players={comparison.players} notes={comparison.notes} />
      ) : null}
      {comparison && comparison.players.length === 0 ? (
        <AlertBanner title="None of the selected IDs resolved to players.">
          {comparison.notes}
        </AlertBanner>
      ) : null}
    </div>
  );
}
