from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.cir_ranking import CirRankingResponse
from app.services.cir_ranking_service import CirRankingService

router = APIRouter(prefix="/rankings", tags=["rankings"])


def get_ranking_service(db: Session = Depends(get_db)) -> CirRankingService:
    return CirRankingService(db)


@router.get("/cir", response_model=CirRankingResponse)
def list_cir_rankings(
    role: str | None = Query(None),
    tier: str | None = Query(None),
    team: str | None = Query(None),
    region: str | None = Query(None),
    agent: str | None = Query(None),
    event: str | None = Query(None),
    min_rounds: int | None = Query(None, ge=0),
    include_provisional: bool = Query(False),
    include_low_sample: bool = Query(False),
    sample_status: str | None = Query(None),
    metric_version: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: CirRankingService = Depends(get_ranking_service),
) -> CirRankingResponse:
    try:
        return service.list_rankings(
            metric_version=metric_version,
            role=role,
            tier=tier,
            team=team,
            region=region,
            agent=agent,
            event=event,
            min_rounds=min_rounds,
            include_provisional=include_provisional,
            include_low_sample=include_low_sample,
            sample_status=sample_status,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
