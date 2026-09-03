from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir.ranking_explore import (
    RANKING_REGIONS,
    canonicalize_ranking_region,
    event_ranking_region,
)
from app.models import Event
from app.schemas.event import EventListResponse, EventSummary


class EventQueryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_events(
        self,
        *,
        region: str | None = None,
        circuit: str | None = None,
        season_year: int | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> EventListResponse:
        rows = list(self._session.scalars(select(Event)).all())
        wanted_region = canonicalize_ranking_region(region) if region else None
        if region and wanted_region is None:
            raise ValueError(
                f"Unknown region '{region}'. Valid: {', '.join(RANKING_REGIONS)}"
            )

        filtered: list[EventSummary] = []
        for event in rows:
            canonical = event_ranking_region(region=event.region, name=event.name)
            if wanted_region and canonical != wanted_region:
                continue
            if circuit and (event.circuit or "").lower() != circuit.lower():
                continue
            if season_year is not None and event.season_year != season_year:
                continue
            if status and (event.status or "").lower() != status.lower():
                continue
            filtered.append(_to_summary(event, canonical))

        filtered.sort(
            key=lambda item: (
                item.start_date or "",
                item.name.lower(),
            ),
            reverse=True,
        )
        total = len(filtered)
        page = filtered[offset : offset + limit]
        return EventListResponse(total=total, events=page)


def _to_summary(event: Event, canonical_region: str | None) -> EventSummary:
    return EventSummary(
        id=str(event.id),
        vlr_event_id=event.vlr_event_id,
        name=event.name,
        region=event.region,
        canonical_region=canonical_region,
        tier=event.tier,
        circuit=event.circuit,
        stage=event.stage,
        status=event.status,
        start_date=event.start_date.isoformat() if event.start_date else None,
        end_date=event.end_date.isoformat() if event.end_date else None,
        season_year=event.season_year,
    )
