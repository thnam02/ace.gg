from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.cir_ranking import CirCompareResponse, CirPlayerDetail, PlayerOptionsResponse
from app.schemas.player_api import (
    PlayerCompareResponse,
    PlayerDetailResponse,
    PlayerMapsResponse,
    PlayerMatchesResponse,
    PlayerStatsResponse,
    PlayerSummary,
    StatsQueryParams,
)
from app.services.cir_ranking_service import CirRankingService
from app.services.player_query import PlayerNotFoundError, PlayerQueryService

router = APIRouter(prefix="/players", tags=["players"])

_MIN_COMPARE_PLAYERS = 2
_MAX_COMPARE_PLAYERS = 4


def _require_compare_ids(player_ids: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for raw in player_ids:
        for part in raw.split(","):
            player_id = part.strip()
            if player_id and player_id not in seen:
                seen.add(player_id)
                expanded.append(player_id)
    if not _MIN_COMPARE_PLAYERS <= len(expanded) <= _MAX_COMPARE_PLAYERS:
        raise HTTPException(
            status_code=422,
            detail=f"Compare requires {_MIN_COMPARE_PLAYERS}–{_MAX_COMPARE_PLAYERS} player IDs.",
        )
    return expanded


def get_player_query_service(db: Session = Depends(get_db)) -> PlayerQueryService:
    return PlayerQueryService(db)


def get_ranking_service(db: Session = Depends(get_db)) -> CirRankingService:
    return CirRankingService(db)


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


@router.get("/options", response_model=PlayerOptionsResponse)
def list_player_options(
    search: str | None = Query(None),
    team: str | None = Query(None),
    role: str | None = Query(None),
    tier: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ranking: CirRankingService = Depends(get_ranking_service),
) -> PlayerOptionsResponse:
    try:
        return ranking.list_options(
            search=search,
            team=team,
            role=role,
            tier=tier,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/compare", response_model=PlayerCompareResponse)
def compare_players(
    player_ids: list[str] = Query(
        ...,
        min_length=1,
        max_length=4,
        description="Player IDs to compare",
    ),
    filters: StatsQueryParams = Depends(_stats_filters),
    service: PlayerQueryService = Depends(get_player_query_service),
    ranking: CirRankingService = Depends(get_ranking_service),
) -> PlayerCompareResponse:
    player_ids = _require_compare_ids(player_ids)
    try:
        payload = service.compare_players(player_ids, filters)
        try:
            version = ranking.resolve_metric_version()
        except ValueError:
            return payload
        for entry in payload.players:
            entry.cir = ranking.compare_block(UUID(entry.player.id), version=version)
        payload.notes = (
            f"{payload.notes} CIR inputs are context-adjusted combat only; "
            "ACS/ADR/KAST/opening remain descriptive scouting stats."
        )
        return payload
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None


@router.get("/compare/cir", response_model=CirCompareResponse)
def compare_players_cir(
    player_ids: list[str] = Query(
        ...,
        min_length=1,
        max_length=4,
        description="Player IDs to compare",
    ),
    metric_version: str | None = Query(None),
    service: CirRankingService = Depends(get_ranking_service),
) -> CirCompareResponse:
    player_ids = _require_compare_ids(player_ids)
    try:
        return service.compare(player_ids, metric_version=metric_version)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{player_id}/cir", response_model=CirPlayerDetail)
def get_player_cir(
    player_id: str,
    metric_version: str | None = Query(None),
    service: CirRankingService = Depends(get_ranking_service),
) -> CirPlayerDetail:
    try:
        return service.player_cir(player_id, metric_version=metric_version)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
