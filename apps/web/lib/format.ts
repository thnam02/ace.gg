import type { PlayerProfile } from "@/lib/types";

export function formatAcs(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return value.toFixed(1);
}

export function formatKd(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return value.toFixed(2);
}

export function formatHs(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return `${value.toFixed(1)}%`;
}

export function formatAdr(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return value.toFixed(1);
}

export function formatWinRate(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatSyncDate(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatCir(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  if (value >= 99.95) {
    return "100";
  }
  const nearest = Math.round(value);
  if (nearest !== 100 && Math.abs(value - nearest) < 0.05) {
    return String(nearest);
  }
  return value.toFixed(1);
}

export function formatCirOrUnavailable(value: number | null | undefined): string {
  if (value == null) {
    return "CIR unavailable";
  }
  return formatCir(value);
}

export function formatRate(value: number | null | undefined, digits = 2): string {
  if (value == null) {
    return "N/A";
  }
  return value.toFixed(digits);
}

export function formatSignedRate(value: number | null | undefined, digits = 2): string {
  if (value == null) {
    return "N/A";
  }
  const formatted = value.toFixed(digits);
  return value > 0 ? `+${formatted}` : formatted;
}

export function formatRounds(value: number): string {
  return value.toLocaleString("en-US");
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return `${value.toFixed(1)}%`;
}

export function formatClutch(value: number | null | undefined): string {
  if (value == null) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function teamLabel(team: string | null): string {
  return team ?? "Free agent";
}

export function rosterMetrics(players: PlayerProfile[]) {
  const count = players.length;
  if (count === 0) {
    return { count, avgAcs: 0, avgKd: 0, avgWinRate: 0 };
  }

  const withMaps = players.filter((player) => player.stats.matches > 0);
  const divisor = withMaps.length > 0 ? withMaps.length : count;

  return {
    count,
    avgAcs: withMaps.reduce((sum, player) => sum + player.stats.acs, 0) / divisor,
    avgKd: withMaps.reduce((sum, player) => sum + player.stats.kd, 0) / divisor,
    avgWinRate: withMaps.reduce((sum, player) => sum + player.stats.win_rate, 0) / divisor,
  };
}
