import { CirExplainer } from "@/components/home/cir-explainer";
import { HomeHero } from "@/components/home/home-hero";
import { LiveStatsStrip } from "@/components/home/live-stats-strip";
import { ScoutingTools } from "@/components/home/scouting-tools";
import { TopPlayers } from "@/components/home/top-players";
import { buildHomeLiveStats, homeFreshnessLabel } from "@/lib/home";
import type { CirMetricMetadata, CirPlayerDetail, CirRankingPlayer } from "@/lib/types";

export type HomePageViewProps = {
  topPlayers: CirRankingPlayer[];
  establishedCount: number | null;
  rankingsError: boolean;
  metadata: CirMetricMetadata | null;
  leader: CirRankingPlayer | null;
  leaderCir: CirPlayerDetail | null;
};

export function HomePageView({
  topPlayers,
  establishedCount,
  rankingsError,
  metadata,
  leader,
  leaderCir,
}: HomePageViewProps) {
  const stats = buildHomeLiveStats({
    establishedCount,
    season: metadata?.season,
    circuit: metadata?.circuit,
  });

  return (
    <div className="space-y-12 sm:space-y-16">
      <HomeHero leader={leader} leaderCir={leaderCir} />
      <LiveStatsStrip stats={stats} freshness={homeFreshnessLabel(metadata?.last_data_sync_at)} />
      <TopPlayers players={topPlayers} error={rankingsError} />
      <CirExplainer />
      <ScoutingTools />
    </div>
  );
}
