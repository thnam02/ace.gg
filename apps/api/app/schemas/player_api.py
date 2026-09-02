from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.stats import MapStatsDerived, MapStatsRaw, PlayerStatsAggregate


class TeamRef(BaseModel):
    id: str
    vlr_team_id: int
    name: str
    tag: str
    region: str | None = None


class PlayerIdentity(BaseModel):
    id: str
    vlr_player_id: int
    handle: str
    real_name: str | None = None
    country: str | None = None
    team: TeamRef | None = None


class PlayerDashboardStats(BaseModel):
    matches: int = 0
    maps_played: int = 0
    rounds: int = 0
    acs: float | None = None
    kd: float | None = None
    hs_percent: float | None = None
    adr: float | None = None
    win_rate: float | None = None


class PlayerSummary(BaseModel):
    id: str
    vlr_player_id: int
    handle: str
    real_name: str | None = None
    country: str | None = None
    team: TeamRef | None = None
    stats: PlayerDashboardStats


class PlayerDetailResponse(BaseModel):
    player: PlayerIdentity
    stats: PlayerDashboardStats
    aggregate: PlayerStatsAggregate


class PlayerStatsResponse(BaseModel):
    player_id: str
    aggregate: PlayerStatsAggregate


class MatchMapPerformance(BaseModel):
    match_id: str
    vlr_match_id: int
    match_map_id: str
    map_name: str
    map_number: int
    played_at: str | None = None
    event_name: str | None = None
    opponent_team: str | None = None
    won: bool | None = None
    agent_name: str | None = None
    raw: MapStatsRaw
    derived: MapStatsDerived


class PlayerMatchesResponse(BaseModel):
    player_id: str
    performances: list[MatchMapPerformance] = Field(default_factory=list)


class MapAggregatePerformance(BaseModel):
    map_name: str
    maps_played: int
    rounds: int
    raw: MapStatsRaw
    derived: MapStatsDerived


class PlayerMapsResponse(BaseModel):
    player_id: str
    maps: list[MapAggregatePerformance] = Field(default_factory=list)


class PlayerCompareEntry(BaseModel):
    player: PlayerIdentity
    stats: PlayerDashboardStats
    aggregate: PlayerStatsAggregate


class PlayerCompareResponse(BaseModel):
    players: list[PlayerCompareEntry] = Field(default_factory=list)
    notes: str = ""


class StatsQueryParams(BaseModel):
    event_id: UUID | None = None
    vlr_event_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_rounds: int | None = None
