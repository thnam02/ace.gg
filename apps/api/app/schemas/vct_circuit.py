from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EventStatus(StrEnum):
    UPCOMING = "UPCOMING"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"


class CircuitName(StrEnum):
    VCT = "VCT"


class VctRegion(StrEnum):
    AMERICAS = "Americas"
    EMEA = "EMEA"
    PACIFIC = "Pacific"
    CHINA = "China"
    INTL = "INTL"


class VctStage(StrEnum):
    KICKOFF = "Kickoff"
    MASTERS = "Masters"
    STAGE_1 = "Stage 1"
    STAGE_2 = "Stage 2"
    CHAMPIONS = "Champions"


class VctSyncJobStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class VctReconcileState(StrEnum):
    MISSING = "missing"
    INCOMPLETE = "present_but_incomplete"
    COMPLETE = "already_complete"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"


class VctDiscoveredEvent(BaseModel):
    vlr_event_id: int
    name: str
    status: EventStatus
    region: str
    stage: str | None = None
    tier: str = "T1"
    circuit: str = CircuitName.VCT.value
    season_year: int = 2026
    start_date: date | None = None
    end_date: date | None = None
    slug: str | None = None
    source_status: str | None = None


class VctEventSyncResult(BaseModel):
    vlr_event_id: int
    name: str
    status: str
    region: str | None = None
    stage: str | None = None
    reconcile_state: str
    action: str
    existed_before: bool = False
    matches_discovered: int = 0
    matches_ingested: int = 0
    matches_skipped: int = 0
    matches_failed: int = 0
    maps_added: int = 0
    player_map_stats_added: int = 0
    maps_complete: int = 0
    maps_incomplete: int = 0
    unresolved_players: int = 0
    errors: list[str] = Field(default_factory=list)


class VctSyncReport(BaseModel):
    circuit: str = CircuitName.VCT.value
    season_year: int = 2026
    job_status: VctSyncJobStatus = VctSyncJobStatus.SUCCESS
    dry_run: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    events_discovered: int = 0
    completed_events: int = 0
    ongoing_events: int = 0
    upcoming_events: int = 0
    events_added: int = 0
    events_updated: int = 0
    matches_added: int = 0
    matches_updated: int = 0
    maps_added: int = 0
    player_map_stats_added: int = 0
    identity_resolution_failures: int = 0
    incomplete_maps: int = 0
    players_affected: int = 0
    cir_snapshots_refreshed: int = 0
    cir_versions_refreshed: list[str] = Field(default_factory=list)
    elo_rebuilt: bool = False
    v02_parameters_frozen: bool = True
    retrained_cir: bool = False
    errors: list[str] = Field(default_factory=list)
    events: list[VctEventSyncResult] = Field(default_factory=list)
