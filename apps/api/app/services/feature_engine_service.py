from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.metrics.adr_regression import AdrRegressionModel, train_adr_regression
from app.metrics.bayesian_clutch import ClutchPrior, estimate_clutch_prior
from app.metrics.derived import safe_ratio
from app.metrics.feature_engine import FeatureEngine
from app.metrics.stats_engine import player_map_stats_to_raw
from app.models import PlayerMapStats
from app.schemas.features import CIRFeatures, PlayerCIRFeatures
from app.schemas.stats import PlayerStatsScope
from app.services.stats_engine_service import StatsEngineService


class FeatureEngineService:
    """Train reference models and compute CIR-ready player features."""

    def __init__(
        self,
        session: Session,
        *,
        stats_service: StatsEngineService | None = None,
    ) -> None:
        self._session = session
        self._stats_service = stats_service or StatsEngineService(session)

    def for_player(
        self,
        player_id: UUID,
        *,
        event_id: UUID | None = None,
        vlr_event_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rounds: int | None = None,
    ) -> PlayerCIRFeatures:
        aggregate = self._stats_service.for_player(
            player_id,
            event_id=event_id,
            vlr_event_id=vlr_event_id,
            start_date=start_date,
            end_date=end_date,
            min_rounds=min_rounds,
        )
        engine = self._build_feature_engine()
        return engine.build_player_features(player_id, aggregate)

    def for_scope(self, scope: PlayerStatsScope) -> PlayerCIRFeatures:
        return self.for_player(
            scope.player_id,
            event_id=scope.event_id,
            vlr_event_id=scope.vlr_event_id,
            start_date=scope.start_date,
            end_date=scope.end_date,
        )

    def for_player_map_stats(self, stats: PlayerMapStats) -> CIRFeatures:
        engine = self._build_feature_engine()
        return engine.from_player_map_stats(stats)

    def train_adr_model(self) -> AdrRegressionModel:
        return train_adr_regression(self._adr_observations())

    def estimate_clutch_prior(self) -> ClutchPrior:
        return estimate_clutch_prior(self._clutch_observations())

    def _build_feature_engine(self) -> FeatureEngine:
        return FeatureEngine(
            adr_model=self.train_adr_model(),
            clutch_prior=self.estimate_clutch_prior(),
        )

    def _reference_rows(self) -> list[PlayerMapStats]:
        return self._stats_service.load_player_map_stats(None)

    def _adr_observations(self) -> list[tuple[float, float]]:
        observations: list[tuple[float, float]] = []
        for row in self._reference_rows():
            raw = player_map_stats_to_raw(row)
            if raw.rounds <= 0 or raw.adr is None:
                continue
            kpr = safe_ratio(raw.kills, raw.rounds)
            if kpr is None:
                continue
            observations.append((kpr, raw.adr))
        return observations

    def _clutch_observations(self) -> list[tuple[int, int]]:
        observations: list[tuple[int, int]] = []
        for row in self._reference_rows():
            raw = player_map_stats_to_raw(row)
            if raw.clutch_attempts is None or raw.clutch_attempts <= 0:
                continue
            observations.append((raw.clutch_wins or 0, raw.clutch_attempts))
        return observations
