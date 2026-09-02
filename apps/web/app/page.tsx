import type { Metadata } from "next";

import { HomePageView } from "@/components/home/home-page";
import { fetchCirMetadata, fetchCirRankings, fetchPlayerCir } from "@/lib/api";
import { HOME_METADATA_DESCRIPTION, HOME_METADATA_TITLE } from "@/lib/home";
import type { CirPlayerDetail } from "@/lib/types";

export const metadata: Metadata = {
  title: {
    absolute: HOME_METADATA_TITLE,
  },
  description: HOME_METADATA_DESCRIPTION,
};

export default async function HomePage() {
  const [rankingsResult, metadataResult] = await Promise.allSettled([
    fetchCirRankings({ limit: 6 }),
    fetchCirMetadata(),
  ]);

  const rankings = rankingsResult.status === "fulfilled" ? rankingsResult.value : null;
  const rankingsError = rankingsResult.status === "rejected";
  const metadata = metadataResult.status === "fulfilled" ? metadataResult.value : null;
  const topPlayers = rankings?.players ?? [];
  const leader = topPlayers[0] ?? null;
  let leaderCir: CirPlayerDetail | null = null;
  if (leader) {
    try {
      leaderCir = await fetchPlayerCir(leader.player_id);
    } catch {
      leaderCir = null;
    }
  }

  return (
    <HomePageView
      topPlayers={topPlayers}
      establishedCount={rankings?.total ?? null}
      rankingsError={rankingsError}
      metadata={metadata}
      leader={leader}
      leaderCir={leaderCir}
    />
  );
}
