import type { PlayerProfile } from "@/lib/types";

export function formatAcs(value: number): string {
  return value.toFixed(1);
}

export function formatKd(value: number): string {
  return value.toFixed(2);
}

export function formatHs(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatAdr(value: number): string {
  return value.toFixed(1);
}

export function formatWinRate(value: number): string {
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

  return {
    count,
    avgAcs: players.reduce((sum, player) => sum + player.stats.acs, 0) / count,
    avgKd: players.reduce((sum, player) => sum + player.stats.kd, 0) / count,
    avgWinRate: players.reduce((sum, player) => sum + player.stats.win_rate, 0) / count,
  };
}
