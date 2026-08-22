from app.schemas.player import PlayerProfile, PlayerStats


class MockPlayerDataProvider:
    """In-memory player data used until a live provider is wired up."""

    def __init__(self) -> None:
        self._players: dict[str, PlayerProfile] = {
            player.id: player
            for player in (
                PlayerProfile(
                    id="tenz",
                    display_name="TenZ",
                    riot_id="TenZ#SEN",
                    team="Sentinels",
                    region="NA",
                    rank="Radiant",
                    stats=PlayerStats(
                        matches=48,
                        acs=246.8,
                        kd=1.28,
                        hs_percent=27.4,
                        adr=161.2,
                        win_rate=0.61,
                    ),
                ),
                PlayerProfile(
                    id="aspas",
                    display_name="aspas",
                    riot_id="aspas#LEV",
                    team="LOUD",
                    region="BR",
                    rank="Radiant",
                    stats=PlayerStats(
                        matches=52,
                        acs=251.3,
                        kd=1.34,
                        hs_percent=31.1,
                        adr=168.4,
                        win_rate=0.64,
                    ),
                ),
                PlayerProfile(
                    id="something",
                    display_name="Something",
                    riot_id="Something#PRX",
                    team="Paper Rex",
                    region="AP",
                    rank="Radiant",
                    stats=PlayerStats(
                        matches=44,
                        acs=238.1,
                        kd=1.19,
                        hs_percent=24.8,
                        adr=154.7,
                        win_rate=0.58,
                    ),
                ),
            )
        }

    def list_players(self) -> list[PlayerProfile]:
        return list(self._players.values())

    def get_player(self, player_id: str) -> PlayerProfile | None:
        return self._players.get(player_id)
