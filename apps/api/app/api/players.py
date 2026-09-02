from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.player_api import (
    PlayerCompareResponse,
    PlayerDetailResponse,
    PlayerMapsResponse,
    PlayerMatchesResponse,
    PlayerStatsResponse,
    PlayerSummary,
    StatsQueryParams,
)
from app.services.player_query import PlayerNotFoundError, PlayerQueryService

router = APIRouter(prefix="/players", tags=["players"])


def get_player_query_service(db: Session = Depends(get_db)) -> PlayerQueryService:
    return PlayerQueryService(db)


def _stats_filters(
    event_id: UUID | None = Query(None),
    vlr_event_id: int | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    min_rounds: int | None = Query(None, ge=0),
) -> StatsQueryParams:
    return StatsQueryParams(
        event_id=event_id,
        vlr_event_id=vlr_event_id,
        start_date=start_date,
        end_date=end_date,
        min_rounds=min_rounds,
    )


@router.get("", response_model=list[PlayerSummary])
def list_players(
    filters: StatsQueryParams = Depends(_stats_filters),
    service: PlayerQueryService = Depends(get_player_query_service),
) -> list[PlayerSummary]:
    return service.list_players(filters)


@router.get("/compare", response_model=PlayerCompareResponse)
def compare_players(
    player_ids: list[str] = Query(..., min_length=2, description="Player IDs to compare"),
    filters: StatsQueryParams = Depends(_stats_filters),
    service: PlayerQueryService = Depends(get_player_query_service),
) -> PlayerCompareResponse:
    try:
        return service.compare_players(player_ids, filters)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None


@router.get("/{player_id}/stats", response_model=PlayerStatsResponse)
def get_player_stats(
    player_id: str,
    filters: StatsQueryParams = Depends(_stats_filters),
    service: PlayerQueryService = Depends(get_player_query_service),
) -> PlayerStatsResponse:
    try:
        return service.get_player_stats(player_id, filters)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None


@router.get("/{player_id}/matches", response_model=PlayerMatchesResponse)
def get_player_matches(
    player_id: str,
    filters: StatsQueryParams = Depends(_stats_filters),
    limit: int = Query(20, ge=1, le=100),
    service: PlayerQueryService = Depends(get_player_query_service),
) -> PlayerMatchesResponse:
    try:
        return service.get_player_matches(player_id, filters, limit=limit)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None


@router.get("/{player_id}/maps", response_model=PlayerMapsResponse)
def get_player_maps(
    player_id: str,
    filters: StatsQueryParams = Depends(_stats_filters),
    service: PlayerQueryService = Depends(get_player_query_service),
) -> PlayerMapsResponse:
    try:
        return service.get_player_maps(player_id, filters)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None


@router.get("/{player_id}", response_model=PlayerDetailResponse)
def get_player(
    player_id: str,
    filters: StatsQueryParams = Depends(_stats_filters),
    service: PlayerQueryService = Depends(get_player_query_service),
) -> PlayerDetailResponse:
    try:
        return service.get_player(player_id, filters)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None
