export type PlayerDashboardStats = {
  matches: number;
  maps_played: number;
  rounds: number;
  acs: number | null;
  kd: number | null;
  hs_percent: number | null;
  adr: number | null;
  win_rate: number | null;
};

export type TeamRef = {
  id: string;
  vlr_team_id: number;
  name: string;
  tag: string;
  region: string | null;
};

export type PlayerSummary = {
  id: string;
  vlr_player_id: number;
  handle: string;
  real_name: string | null;
  country: string | null;
  team: TeamRef | null;
  stats: PlayerDashboardStats;
};

export type MapStatsRaw = {
  rounds: number;
  kills: number;
  deaths: number;
  assists: number;
  first_kills: number;
  first_deaths: number;
  adr?: number | null;
  kast_pct?: number | null;
  clutch_wins?: number | null;
  clutch_attempts?: number | null;
  acs?: number | null;
};

export type MapStatsDerived = {
  kpr: number | null;
  dpr: number | null;
  apr: number | null;
  fkpr: number | null;
  fdpr: number | null;
  opening_frequency: number | null;
  opening_efficiency: number | null;
  raw_clutch_rate: number | null;
};

export type PlayerStatsAggregate = {
  raw: {
    rounds: number;
    maps_played: number;
    kills: number;
    deaths: number;
    assists: number;
    first_kills: number;
    first_deaths: number;
    weighted_adr: number | null;
    weighted_kast: number | null;
    weighted_acs: number | null;
  };
  derived: MapStatsDerived;
  maps: unknown[];
};

export type PlayerIdentity = {
  id: string;
  vlr_player_id: number;
  handle: string;
  real_name: string | null;
  country: string | null;
  team: TeamRef | null;
};

export type PlayerDetailResponse = {
  player: PlayerIdentity;
  stats: PlayerDashboardStats;
  aggregate: PlayerStatsAggregate;
};

export type PlayerCompareEntry = {
  player: PlayerIdentity;
  stats: PlayerDashboardStats;
  aggregate: PlayerStatsAggregate;
};

export type PlayerComparison = {
  players: PlayerProfile[];
  notes: string;
};

/** Roster/compare view model derived from API summaries. */
export type PlayerProfile = {
  id: string;
  display_name: string;
  riot_id: string;
  team: string | null;
  region: string;
  rank: string;
  stats: {
    matches: number;
    acs: number;
    kd: number;
    hs_percent: number;
    adr: number;
    win_rate: number;
  };
};

export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  database: "connected" | "disconnected";
};
