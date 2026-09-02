import { formatCir, formatRounds, formatSignedRate, formatSyncDate } from "@/lib/format";
import { percentileOrdinal } from "@/lib/player-cir-copy";
import type { CirRankingPlayer } from "@/lib/types";

export const HOME_BRAND = "ACE.gg";

export const HOME_HEADLINE_LEAD = "VALORANT player analytics";
export const HOME_HEADLINE_EMPHASIS = "beyond the scoreboard.";

export const HOME_SUPPORT =
  "Compare professional players using CIR, role-adjusted performance, and scouting data from competitive VCT and Challengers matches.";

export const HOME_CIR_NAME = "Contextual Impact Rating";

export const HOME_CIR_SHORT =
  "CIR compares a player's kill production and death avoidance against expectations for comparable roles and competitive tiers, then expresses the result as a percentile.";

export const HOME_BEYOND_KD =
  "Raw stats favor different playstyles and roles. CIR compares players against role- and tier-specific expectations before producing a percentile score.";

export const HOME_DATASET_NOTE =
  "Tracking VCT and Challengers competition. Current rankings use the 2026 CIR reference.";

export const HOME_FOOTER_BLURB = "VALORANT analytics and scouting powered by CIR.";

export const HOME_RIOT_DISCLAIMER =
  "ACE.gg is an independent analytics project and is not affiliated with Riot Games.";

export const HOME_METADATA_TITLE = "ACE.gg — VALORANT Player Analytics";

export const HOME_METADATA_DESCRIPTION =
  "Professional VALORANT player rankings, comparisons and scouting analytics powered by CIR.";

export const CIR_STEPS = [
  {
    title: "Compare to expectation",
    body: "Players are evaluated against players in comparable roles and tiers.",
    chip: "Role + Tier",
  },
  {
    title: "Measure combat performance",
    body: "Kill production and death avoidance are measured relative to that expectation.",
    chip: "Kill production + Death avoidance",
  },
  {
    title: "Convert to percentile",
    body: "Performance is sample-adjusted and expressed on a 0–100 percentile scale.",
    chip: "CIR percentile",
  },
] as const;

export type HomeLiveStat = {
  value: string;
  label: string;
};

export function buildHomeLiveStats(input: {
  establishedCount?: number | null;
  season?: number | null;
  circuit?: string | null;
}): HomeLiveStat[] {
  const items: HomeLiveStat[] = [];
  if (input.establishedCount != null) {
    items.push({
      value: formatRounds(input.establishedCount),
      label: "Established players",
    });
  }
  if (input.season != null) {
    const circuit = input.circuit?.trim();
    items.push({
      value: String(input.season),
      label: circuit ? `${circuit} season` : "Current season",
    });
  }
  items.push({ value: "T1 + T2", label: "Competitive tiers" });
  items.push({ value: "Daily", label: "Data updates" });
  return items;
}

export function homeFreshnessLabel(lastDataSyncAt: string | null | undefined): string {
  const sync = formatSyncDate(lastDataSyncAt);
  return sync ? `Updated ${sync}` : "Updated daily";
}

export function compactPercentile(cir: number): string {
  if (cir >= 99.95) {
    return "Top percentile";
  }
  return `${percentileOrdinal(Math.min(99, Math.round(cir)))} percentile`;
}

export function compactResidual(residual: number | null | undefined): string | null {
  if (residual == null) {
    return null;
  }
  return `${formatSignedRate(residual)} vs expected`;
}

export function reliabilityRoundsLine(
  reliability: string | null | undefined,
  rounds: number,
): string {
  const label = reliability?.trim();
  if (label) {
    return `${label} · ${formatRounds(rounds)} rounds`;
  }
  return `${formatRounds(rounds)} rounds`;
}

export function playerSearchCirLabel(cir: number | null | undefined): string {
  if (cir == null) {
    return "CIR unavailable";
  }
  return `CIR ${formatCir(cir)}`;
}

export function sampleStatusLabel(status: string | null | undefined): string | null {
  if (!status?.trim()) {
    return null;
  }
  const value = status.trim();
  if (value === "ESTABLISHED") {
    return "Established";
  }
  if (value === "PROVISIONAL") {
    return "Provisional";
  }
  if (value === "LOW") {
    return "Low sample";
  }
  return value;
}

export function topPlayersPreview(players: CirRankingPlayer[]): CirRankingPlayer[] {
  return players.slice(0, 6);
}
