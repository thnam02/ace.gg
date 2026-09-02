import { formatCir, formatRate, formatRounds, formatSignedRate } from "@/lib/format";

export const SCOUTING_DISCLAIMER =
  "These stats describe playstyle and do not directly affect CIR.";

export const WHY_THIS_SCORE_NOTE =
  "CIR combines context-adjusted kill production and death avoidance with equal weight.";

export const METRIC_VERSION_TOOLTIP =
  "Scores use frozen role+tier expectations from the CIR v0.2 reference population.";

const ROLE_PLURALS: Record<string, string> = {
  duelist: "Duelists",
  sentinel: "Sentinels",
  controller: "Controllers",
  initiator: "Initiators",
  flex: "Flex players",
};

export type ExpectationDirection = "above" | "below" | "even" | "na";

export function percentileOrdinal(value: number): string {
  const n = Math.round(value);
  const remainder = n % 100;
  if (remainder >= 11 && remainder <= 13) {
    return `${n}th`;
  }
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

export function cirInterpretation(cir: number | null | undefined): string {
  if (cir == null) {
    return "CIR unavailable";
  }
  if (cir >= 99.95) {
    return "Top percentile of the 2026 reference population";
  }
  const ordinalSource = Math.min(99, Math.round(cir));
  return `Around the ${percentileOrdinal(ordinalSource)} percentile of the 2026 reference population`;
}

export function cirRankLine(
  rank: number | null | undefined,
  establishedCount: number | null | undefined,
  sampleStatus: string | null | undefined,
): string {
  if (rank != null && establishedCount != null && establishedCount > 0) {
    return "Established ranking";
  }
  if (rank != null) {
    return "Established ranking";
  }
  if (sampleStatus === "PROVISIONAL" || sampleStatus === "LOW_SAMPLE") {
    return "Not in established ranking";
  }
  return "Not in established ranking";
}

export function rankHeadline(
  rank: number | null | undefined,
  establishedCount: number | null | undefined,
): { rank: string; of: string | null } {
  if (rank != null && establishedCount != null && establishedCount > 0) {
    return { rank: `#${rank} / ${establishedCount}`, of: null };
  }
  if (rank != null) {
    return { rank: `#${rank}`, of: null };
  }
  return { rank: "Not ranked", of: null };
}

export function playerIdentityLine(
  teamName: string | null | undefined,
  role: string | null | undefined,
): string {
  const team = teamName?.trim() || null;
  const roleLabel = role?.trim() || null;
  if (team && roleLabel) {
    return `${team} · ${roleLabel}`;
  }
  if (team) {
    return team;
  }
  if (roleLabel) {
    return `Unattached · ${roleLabel}`;
  }
  return "Unattached";
}

export function pluralizeRole(role: string | null | undefined): string | null {
  if (role == null || role.trim() === "") {
    return null;
  }
  const trimmed = role.trim();
  return ROLE_PLURALS[trimmed.toLowerCase()] ?? `${trimmed}s`;
}

export function contextBenchmark(
  tier: string | null | undefined,
  role: string | null | undefined,
): string | null {
  const tierLabel = tier?.trim() || null;
  const roleLabel = pluralizeRole(role);
  if (tierLabel && roleLabel) {
    return `Compared with ${tierLabel} ${roleLabel}`;
  }
  if (roleLabel) {
    return `Compared with ${roleLabel}`;
  }
  if (tierLabel) {
    return `Compared with ${tierLabel} players`;
  }
  return null;
}

export function metricVersionLabel(version: string | null | undefined): string {
  const match = version?.match(/v(\d+\.\d+).*?(20\d{2})/i);
  if (match) {
    return `CIR v${match[1]} · ${match[2]} reference`;
  }
  if (version) {
    return `CIR ${version}`;
  }
  return "CIR v0.2 · 2026 reference";
}

export function reliabilityLine(
  reliability: string | null | undefined,
  rounds: number | null | undefined,
): string {
  const label = reliability ?? "N/A";
  const roundLabel = rounds == null ? "N/A" : formatRounds(rounds);
  return `${label} reliability · ${roundLabel} rounds`;
}

export function kprExpectation(residual: number | null | undefined): {
  text: string;
  direction: ExpectationDirection;
} {
  if (residual == null) {
    return { text: "N/A", direction: "na" };
  }
  if (residual === 0) {
    return { text: "In line with expected KPR", direction: "even" };
  }
  return {
    text: `${formatSignedRate(residual)} vs expected`,
    direction: residual > 0 ? "above" : "below",
  };
}

export function deathAvoidanceExpectation(residual: number | null | undefined): {
  text: string;
  direction: ExpectationDirection;
} {
  if (residual == null) {
    return { text: "N/A", direction: "na" };
  }
  if (residual === 0) {
    return { text: "In line with expected deaths/round", direction: "even" };
  }
  const magnitude = formatRate(Math.abs(residual));
  if (residual > 0) {
    return {
      text: `${magnitude} fewer deaths/round than expected`,
      direction: "above",
    };
  }
  return {
    text: `${magnitude} more deaths/round than expected`,
    direction: "below",
  };
}

export function expectationLabel(direction: ExpectationDirection): string | null {
  if (direction === "above") {
    return "Above expected";
  }
  if (direction === "below") {
    return "Below expected";
  }
  if (direction === "even") {
    return "In line with expected";
  }
  return null;
}

export function clampPercentile(cir: number): number {
  return Math.min(100, Math.max(0, cir));
}

export function kprResidualCopy(residual: number | null | undefined): string {
  if (residual == null) {
    return "N/A";
  }
  if (residual === 0) {
    return "In line with expected KPR";
  }
  return `${formatSignedRate(residual)} kills/round vs expected`;
}

export function percentileBarLabel(cir: number): string {
  return `CIR percentile: ${formatCir(clampPercentile(cir))} out of 100`;
}

export function formatClutchStat(
  rate: number | null | undefined,
  attempts?: number | null,
): string {
  if (rate == null) {
    return "N/A";
  }
  if (attempts != null && attempts <= 0) {
    return "N/A";
  }
  if (rate === 0 && (attempts == null || attempts <= 0)) {
    return "N/A";
  }
  return `${(rate * 100).toFixed(1)}%`;
}

export function openingFrequencyDisplay(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return `${Math.round(value * 100)}%`;
}

export function openingFrequencyHelper(value: number | null | undefined): string | null {
  if (value == null) {
    return null;
  }
  return `${Math.round(value * 100)}% of rounds involved in the opening duel`;
}

export function openingEfficiencyDisplay(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return `${Math.round(value * 100)}%`;
}

export function openingEfficiencyHelper(value: number | null | undefined): string | null {
  if (value == null) {
    return null;
  }
  return `Won ${Math.round(value * 100)}% of opening duels`;
}
