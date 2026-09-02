import Link from "next/link";
import type { Metadata } from "next";

import { AlertBanner } from "@/components/alert-banner";
import { CirRankings } from "@/components/cir-rankings";
import { fetchCirMetadata, fetchCirRankings } from "@/lib/api";
import { parseFlag } from "@/lib/compare";

export const metadata: Metadata = {
  title: "Rankings",
};

type RankingsPageProps = {
  searchParams: Promise<{ include_provisional?: string | string[] }>;
};

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;
  const includeProvisional = parseFlag(params.include_provisional);
  let rankings = null;
  let cirMetadata = null;
  try {
    [rankings, cirMetadata] = await Promise.all([
      fetchCirRankings({ includeProvisional }),
      fetchCirMetadata(),
    ]);
  } catch {
    return (
      <AlertBanner title="Could not load CIR rankings.">
        Return to the{" "}
        <Link href="/" className="underline underline-offset-2 hover:text-accent">
          home rankings
        </Link>
        .
      </AlertBanner>
    );
  }
  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">CIR rankings</h1>
        <p className="text-sm text-muted-foreground">
          Filter the current CIR pool by tier, region, and role. Sort by CIR or
          descriptive scouting metrics without changing published ranks.
        </p>
      </header>
      <CirRankings
        players={rankings.players}
        total={rankings.total}
        includeProvisional={includeProvisional}
        tooltip={cirMetadata?.tooltip ?? ""}
        toggleHref={{ on: "/rankings?include_provisional=1", off: "/rankings" }}
      />
    </div>
  );
}
