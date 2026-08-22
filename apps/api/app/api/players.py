from fastapi import APIRouter, HTTPException, Query

from app.providers.mock import MockPlayerDataProvider
from app.schemas.player import PlayerComparison, PlayerProfile
from app.services.player_comparison import PlayerComparisonService
from app.services.player_stats import PlayerStatsService

router = APIRouter(prefix="/players", tags=["players"])

_provider = MockPlayerDataProvider()
_stats_service = PlayerStatsService(_provider)
_comparison_service = PlayerComparisonService(_provider)


@router.get("", response_model=list[PlayerProfile])
def list_players() -> list[PlayerProfile]:
    return _stats_service.list_players()


@router.get("/compare", response_model=PlayerComparison)
def compare_players(
    ids: list[str] = Query(..., min_length=2, description="Player IDs to compare"),
) -> PlayerComparison:
    return _comparison_service.compare(ids)


@router.get("/{player_id}", response_model=PlayerProfile)
def get_player(player_id: str) -> PlayerProfile:
    player = _stats_service.get_player(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return player
