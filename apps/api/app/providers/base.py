from typing import Protocol

from app.schemas.player import PlayerProfile


class PlayerDataProvider(Protocol):
    """Source of player profiles. Riot API will implement this later."""

    def list_players(self) -> list[PlayerProfile]: ...

    def get_player(self, player_id: str) -> PlayerProfile | None: ...
