from __future__ import annotations

from pydantic import BaseModel, Field


class EventSummary(BaseModel):
    id: str
    vlr_event_id: int
    name: str
    region: str | None = None
    canonical_region: str | None = None
    tier: str | None = None
    circuit: str | None = None
    stage: str | None = None
    status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    season_year: int | None = None


class EventListResponse(BaseModel):
    total: int
    events: list[EventSummary] = Field(default_factory=list)
