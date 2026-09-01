from datetime import date, datetime

from pydantic import BaseModel, Field


class NormalizedTeam(BaseModel):
    vlr_team_id: int
    name: str
    tag: str
    country: str | None = None
    region: str | None = None


class NormalizedPlayer(BaseModel):
    vlr_player_id: int
    handle: str
    real_name: str | None = None
    country: str | None = None


class NormalizedAgent(BaseModel):
    name: str
    role: str


class NormalizedEvent(BaseModel):
    vlr_event_id: int
    name: str
    region: str | None = None
    tier: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    season_year: int | None = None


class NormalizedPlayerMapStats(BaseModel):
    player: NormalizedPlayer
    team_vlr_id: int
    agent: NormalizedAgent
    rounds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    first_kills: int = 0
    first_deaths: int = 0
    adr: float | None = None
    kast_pct: float | None = None
    acs: float | None = None
    vlr_rating: float | None = None
    headshot_pct: float | None = None
    clutch_wins: int | None = None
    clutch_attempts: int | None = None
    max_kills: int | None = None


class NormalizedMatchMap(BaseModel):
    map_number: int
    map_name: str
    team_a_score: int | None = None
    team_b_score: int | None = None
    winner_vlr_team_id: int | None = None
    rounds_played: int | None = None
    player_stats: list[NormalizedPlayerMapStats] = Field(default_factory=list)


class NormalizedMatchData(BaseModel):
    vlr_match_id: int
    event: NormalizedEvent
    team_a: NormalizedTeam
    team_b: NormalizedTeam
    winner_vlr_team_id: int | None = None
    played_at: datetime | None = None
    best_of: int | None = None
    status: str | None = None
    maps: list[NormalizedMatchMap] = Field(default_factory=list)
