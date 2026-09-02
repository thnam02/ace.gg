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
    clutch_wins?: number | null;
    clutch_attempts?: number | null;
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

export type CirCompareBlock = {
  cir: number | null;
  rank: number | null;
  role?: string | null;
  tier?: string | null;
  reliability: string | null;
  rounds: number;
  maps: number;
  kpr: number | null;
  expected_kpr: number | null;
  kpr_residual: number | null;
  dpr: number | null;
  expected_dpr: number | null;
  negative_dpr_residual: number | null;
  combat_factor: number | null;
  sample_status: string | null;
  metric_version: string | null;
};

export type PlayerCompareEntry = {
  player: PlayerIdentity;
  stats: PlayerDashboardStats;
  aggregate: PlayerStatsAggregate;
  cir: CirCompareBlock | null;
};

export type PlayerComparison = {
  players: PlayerCompareEntry[];
  notes: string;
};

export type PlayerOption = {
  id: string;
  handle: string;
  real_name: string | null;
  team: TeamRef | null;
  role: string | null;
  tier: string | null;
  cir: number | null;
  rounds: number;
  sample_status: string | null;
  reliability: string | null;
};

export type PlayerOptionsResponse = {
  total: number;
  limit: number;
  offset: number;
  players: PlayerOption[];
};

export type CirRankingPlayer = {
  rank: number;
  player_id: string;
  handle: string;
  team: TeamRef | null;
  role: string | null;
  primary_agent: string | null;
  cir: number | null;
  reliability: string | null;
  rounds: number;
  maps: number;
  kpr: number | null;
  dpr: number | null;
  sample_status: string | null;
  metric_version: string;
};

export type CirRankingResponse = {
  metric_name: string;
  metric_version: string;
  total: number;
  limit: number;
  offset: number;
  players: CirRankingPlayer[];
};

export type CirPlayerDetail = {
  player_id: string;
  handle: string;
  team: TeamRef | null;
  role: string | null;
  tier?: string | null;
  rank?: number | null;
  established_count?: number;
  cir: number | null;
  raw_cir: number | null;
  reliability: string | null;
  reliability_pct: number | null;
  sample_status: string | null;
  rounds: number;
  maps: number;
  combat_factor: number | null;
  kpr: number | null;
  dpr: number | null;
  expected_kpr: number | null;
  expected_dpr: number | null;
  kpr_residual: number | null;
  negative_dpr_residual: number | null;
  metric_version: string;
  reference_period_start: string | null;
  reference_period_end: string | null;
  interpretation: string | null;
};

export type CirMetricMetadata = {
  name: string;
  version: string;
  status: string;
  description: string;
  tooltip: string;
  interpretation: string;
  features: string[];
  context: string;
  scale: string;
  established_sample: number;
  last_data_sync_at?: string | null;
  latest_match_played_at?: string | null;
  season?: number | null;
  circuit?: string | null;
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
