from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.player_api import TeamRef


class RoleMix(BaseModel):
    role: str
    rounds: int = 0
    share: float = 0.0
    is_main: bool = False


class CirReliability(BaseModel):
    label: str
    pct: float | None = None


class CirRankingPlayer(BaseModel):
    rank: int
    player_id: str
    handle: str
    team: TeamRef | None = None
    role: str | None = None
    roles: list[RoleMix] = Field(default_factory=list)
    tier: str | None = None
    region: str | None = None
    primary_agent: str | None = None
    cir: float | None = None
    reliability: str | None = None
    reliability_pct: float | None = None
    rounds: int = 0
    maps: int = 0
    kpr: float | None = None
    dpr: float | None = None
    sample_status: str | None = None
    metric_version: str
    metric_version_id: str


class CirRankingResponse(BaseModel):
    metric_name: str
    metric_version: str
    metric_version_id: str
    total: int
    limit: int
    offset: int
    players: list[CirRankingPlayer] = Field(default_factory=list)
    scope: str = "season"
    event_id: str | None = None
    vlr_event_id: int | None = None
    event_name: str | None = None
    event_region: str | None = None
    note: str | None = None


class PlayerOption(BaseModel):
    id: str
    handle: str
    real_name: str | None = None
    team: TeamRef | None = None
    role: str | None = None
    tier: str | None = None
    cir: float | None = None
    rounds: int = 0
    sample_status: str | None = None
    reliability: str | None = None


class PlayerOptionsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    players: list[PlayerOption] = Field(default_factory=list)


class CirPlayerDetail(BaseModel):
    player_id: str
    handle: str
    team: TeamRef | None = None
    role: str | None = None
    roles: list[RoleMix] = Field(default_factory=list)
    tier: str | None = None
    rank: int | None = None
    established_count: int = 0
    cir: float | None = None
    raw_cir: float | None = None
    shrunk_raw_cir: float | None = None
    reliability: str | None = None
    reliability_pct: float | None = None
    sample_status: str | None = None
    rounds: int = 0
    maps: int = 0
    events: int = 0
    combat_factor: float | None = None
    kpr: float | None = None
    dpr: float | None = None
    expected_kpr: float | None = None
    expected_dpr: float | None = None
    kpr_residual: float | None = None
    negative_dpr_residual: float | None = None
    sample_weight: float | None = None
    metric_version: str
    metric_version_id: str
    reference_period_start: str | None = None
    reference_period_end: str | None = None
    interpretation: str | None = None


class CirCompareEntry(BaseModel):
    player_id: str
    handle: str
    team: TeamRef | None = None
    role: str | None = None
    cir: float | None = None
    rank: int | None = None
    reliability: str | None = None
    rounds: int = 0
    maps: int = 0
    kpr: float | None = None
    expected_kpr: float | None = None
    kpr_residual: float | None = None
    dpr: float | None = None
    expected_dpr: float | None = None
    negative_dpr_residual: float | None = None
    combat_factor: float | None = None
    sample_status: str | None = None
    metric_version: str | None = None


class CirCompareResponse(BaseModel):
    players: list[CirCompareEntry] = Field(default_factory=list)
    notes: str = ""


class CirMetricMetadata(BaseModel):
    name: str
    version: str
    status: str
    description: str
    tooltip: str
    interpretation: str
    features: list[str]
    context: str
    scale: str
    established_sample: int
    provisional_sample: str
    low_sample: str
    shrinkage_k: float
    reference_period_start: str | None = None
    reference_period_end: str | None = None
    last_data_sync_at: str | None = None
    latest_match_played_at: str | None = None
    season: int | None = None
    circuit: str | None = None
