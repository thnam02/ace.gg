import Link from "next/link";

import { PlayerCard } from "@/components/player-card";
import { SiteHeader } from "@/components/site-header";
import type { HealthResponse, PlayerComparison, PlayerProfile } from "@valorant-scout/shared";

import { comparePlayers, getHealth, getPlayers } from "@/lib/api";

type ComparePageProps = {
  searchParams: Promise<{ ids?: string | string[] }>;
};

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const params = await searchParams;
  const rawIds = params.ids;
  const ids = (Array.isArray(rawIds) ? rawIds : rawIds ? [rawIds] : []).filter(Boolean);

  let health: HealthResponse | null = null;
  let comparison: PlayerComparison | null = null;
  let allPlayers: PlayerProfile[] = [];
  let error: string | null = null;

  try {
    [health, allPlayers] = await Promise.all([getHealth(), getPlayers()]);

    if (ids.length >= 2) {
      comparison = await comparePlayers(ids);
    }
  } catch {
    error = "Could not load comparison data. Ensure the API is running.";
  }

  const players = comparison?.players ?? [];
  const defaultCompareUrl =
    allPlayers.length >= 2
      ? `/compare?${allPlayers
          .slice(0, 2)
          .map((player) => `ids=${encodeURIComponent(player.id)}`)
          .join("&")}`
      : null;

  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader health={health} playerCount={allPlayers.length} />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6 sm:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-[family-name:var(--font-barlow)] text-2xl font-semibold tracking-tight sm:text-3xl">
              Player comparison
            </h1>
            <p className="mt-1 text-sm text-muted">
              Side-by-side pro stats. Pass player IDs via{" "}
              <code className="rounded bg-surface-raised px-1.5 py-0.5 font-[family-name:var(--font-mono)] text-xs">
                ?ids=9&amp;ids=11426
              </code>
            </p>
          </div>
          <Link
            href="/"
            className="focus-ring cursor-pointer rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium transition-colors hover:border-accent/40 motion-reduce:transition-none"
          >
            Back to roster
          </Link>
        </div>

        {error ? (
          <p className="rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-accent" role="alert">
            {error}
          </p>
        ) : null}

        {ids.length < 2 && !error ? (
          <div className="panel px-6 py-12 text-center">
            <p className="font-[family-name:var(--font-barlow)] text-lg font-semibold">
              Select at least two players
            </p>
            <p className="mt-2 text-sm text-muted">
              Add player IDs to the URL, or compare your default roster.
            </p>
            {defaultCompareUrl ? (
              <Link
                href={defaultCompareUrl}
                className="focus-ring mt-5 inline-flex cursor-pointer rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-background transition-opacity hover:opacity-90"
              >
                Compare default roster
              </Link>
            ) : null}
          </div>
        ) : null}

        {players.length > 0 ? (
          <>
            {comparison?.notes ? (
              <p className="rounded-xl border border-border bg-surface px-4 py-3 text-sm text-muted">
                {comparison.notes}
              </p>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {players.map((player) => (
                <PlayerCard key={player.id} player={player} />
              ))}
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
