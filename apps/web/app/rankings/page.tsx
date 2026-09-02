import Link from "next/link";

import { AlertBanner } from "@/components/alert-banner";
import { CirRankings } from "@/components/cir-rankings";
import { fetchCirMetadata, fetchCirRankings } from "@/lib/api";

type RankingsPageProps = {
  searchParams: Promise<{ include_provisional?: string | string[] }>;
};

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;
  const raw = params.include_provisional;
  const includeProvisional = Array.isArray(raw)
    ? raw.includes("1") || raw.includes("true")
    : raw === "1" || raw === "true";
  let rankings = null;
  let metadata = null;
  try {
    [rankings, metadata] = await Promise.all([
      fetchCirRankings({ includeProvisional, limit: 100 }),
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
    <CirRankings
      players={rankings.players}
      includeProvisional={includeProvisional}
      tooltip={metadata?.tooltip ?? ""}
      toggleHref={{ on: "/rankings?include_provisional=1", off: "/rankings" }}
    />
  );
}
