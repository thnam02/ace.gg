from app.schemas.player import PlayerProfile


class MetricEngine:
    """Placeholder for derived player metrics.

    Custom rating logic is intentionally not implemented in this scaffold.
    """

    def evaluate(self, player: PlayerProfile) -> None:
        del player
        raise NotImplementedError("Custom rating metric is not implemented yet.")
