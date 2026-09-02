from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class MapStatsRaw(BaseModel):
    rounds: int
    kills: int
    deaths: int
    assists: int
    first_kills: int
    first_deaths: int
    adr: float | None = None
    kast_pct: float | None = None
    clutch_wins: int | None = None
    clutch_attempts: int | None = None
    acs: float | None = None


class MapStatsDerived(BaseModel):
    kpr: float | None = None
    dpr: float | None = None
    apr: float | None = None
    fkpr: float | None = None
    fdpr: float | None = None
    opening_frequency: float | None = None
    opening_efficiency: float | None = None
    raw_clutch_rate: float | None = None


class MapStatsFeatures(BaseModel):
    raw: MapStatsRaw
    derived: MapStatsDerived
    match_map_id: UUID | None = None


class AggregateStatsRaw(BaseModel):
    rounds: int
    maps_played: int
    kills: int
    deaths: int
    assists: int
    first_kills: int
    first_deaths: int
    weighted_adr: float | None = None
    weighted_kast: float | None = None
    weighted_acs: float | None = None
    clutch_wins: int | None = None
    clutch_attempts: int | None = None


class PlayerStatsAggregate(BaseModel):
    raw: AggregateStatsRaw
    derived: MapStatsDerived
    maps: list[MapStatsFeatures] = Field(default_factory=list)


class PlayerStatsScope(BaseModel):
    player_id: UUID
    event_id: UUID | None = None
    vlr_event_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
