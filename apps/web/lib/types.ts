export type PlayerStats = {
  matches: number;
  acs: number;
  kd: number;
  hs_percent: number;
  adr: number;
  win_rate: number;
};

export type PlayerProfile = {
  id: string;
  display_name: string;
  riot_id: string;
  team: string | null;
  region: string;
  rank: string;
  stats: PlayerStats;
};

export type PlayerComparison = {
  players: PlayerProfile[];
  notes: string;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  database: "connected" | "disconnected";
};
