from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.event import EventListResponse
from app.services.event_query_service import EventQueryService

router = APIRouter(prefix="/events", tags=["events"])


def get_event_query_service(db: Session = Depends(get_db)) -> EventQueryService:
    return EventQueryService(db)


@router.get("", response_model=EventListResponse)
def list_events(
    region: str | None = Query(None),
    tier: str | None = Query(None),
    circuit: str | None = Query(None),
    year: int | None = Query(None),
    season_year: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: EventQueryService = Depends(get_event_query_service),
) -> EventListResponse:
    try:
        return service.list_events(
            region=region,
            tier=tier,
            circuit=circuit,
            season_year=year if year is not None else season_year,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
