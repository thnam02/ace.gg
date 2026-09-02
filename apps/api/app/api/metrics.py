from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.cir_ranking import CirMetricMetadata
from app.services.cir_ranking_service import CirRankingService

router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_ranking_service(db: Session = Depends(get_db)) -> CirRankingService:
    return CirRankingService(db)


@router.get("/cir", response_model=CirMetricMetadata)
def get_cir_metadata(
    metric_version: str | None = Query(None),
    service: CirRankingService = Depends(get_ranking_service),
) -> CirMetricMetadata:
    try:
        return service.metadata(metric_version=metric_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
