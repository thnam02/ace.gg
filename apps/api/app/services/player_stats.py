from app.providers.base import PlayerDataProvider
from app.schemas.player import PlayerProfile


class PlayerStatsService:
    def __init__(self, provider: PlayerDataProvider) -> None:
        self._provider = provider

    def list_players(self) -> list[PlayerProfile]:
        return self._provider.list_players()

    def get_player(self, player_id: str) -> PlayerProfile | None:
        return self._provider.get_player(player_id)
