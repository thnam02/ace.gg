from app.providers.base import PlayerDataProvider
from app.schemas.player import PlayerComparison, PlayerProfile


class PlayerComparisonService:
    def __init__(self, provider: PlayerDataProvider) -> None:
        self._provider = provider

    def compare(self, player_ids: list[str]) -> PlayerComparison:
        players: list[PlayerProfile] = []
        missing: list[str] = []

        for player_id in player_ids:
            player = self._provider.get_player(player_id)
            if player is None:
                missing.append(player_id)
            else:
                players.append(player)

        notes = "Side-by-side pro stats. Custom rating is not implemented yet."
        if missing:
            notes = f"{notes} Missing players: {', '.join(missing)}."

        return PlayerComparison(players=players, notes=notes)
