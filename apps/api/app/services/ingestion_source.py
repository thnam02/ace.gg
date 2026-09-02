from __future__ import annotations

from typing import Protocol

from app.schemas.ingestion import NormalizedEventPageData, NormalizedMatchData


class EventIngestionSource(Protocol):
    """Load canonical ingestion DTOs for event ingestion."""

    def load_event_page(self, event_id: int) -> NormalizedEventPageData: ...

    def load_match(self, match_id: int, event_id: int) -> NormalizedMatchData: ...
