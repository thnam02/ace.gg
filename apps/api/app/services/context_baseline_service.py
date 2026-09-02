from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.metrics.context_baselines import (
    BaselineThresholds,
    ContextObservation,
    adjust_context_observation,
    build_baseline_registry,
    filter_reference_observations,
)
from app.metrics.feature_engine import FeatureEngine
from app.models import PlayerMapStats
from app.schemas.context_features import (
    ContextAdjustedFeatures,
    MapContextFeatures,
    PlayerContextFeatures,
)
from app.schemas.stats import PlayerStatsScope
from app.services.feature_engine_service import FeatureEngineService
from app.services.stats_engine_service import StatsEngineService


class ContextBaselineService:
    """Estimate context baselines and produce context-adjusted CIR features."""

    def __init__(
        self,
        session: Session,
        *,
        stats_service: StatsEngineService | None = None,
        feature_service: FeatureEngineService | None = None,
        thresholds: BaselineThresholds | None = None,
    ) -> None:
        self._session = session
        self._stats_service = stats_service or StatsEngineService(session)
        self._feature_service = feature_service or FeatureEngineService(
            session,
            stats_service=self._stats_service,
        )
        self._thresholds = thresholds or BaselineThresholds()

    def for_player(
        self,
        player_id: UUID,
        *,
        event_id: UUID | None = None,
        vlr_event_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rounds: int | None = None,
        reference_end: datetime | None = None,
    ) -> PlayerContextFeatures:
        rows = self._stats_service.load_player_map_stats(
            player_id,
            event_id=event_id,
            vlr_event_id=vlr_event_id,
            start_date=start_date,
            end_date=end_date,
            min_rounds=min_rounds,
        )
        all_observations = self.load_observations(reference_end=reference_end)
        feature_engine = self._feature_service._build_feature_engine()

        map_features = [
            MapContextFeatures(
                match_map_id=str(row.match_map_id),
                features=self.adjust_player_map_stats(
                    row,
                    all_observations=all_observations,
                    feature_engine=feature_engine,
                ),
            )
            for row in rows
        ]

        return PlayerContextFeatures(player_id=str(player_id), maps=map_features)

    def for_scope(self, scope: PlayerStatsScope) -> PlayerContextFeatures:
        return self.for_player(
            scope.player_id,
            event_id=scope.event_id,
            vlr_event_id=scope.vlr_event_id,
            start_date=scope.start_date,
            end_date=scope.end_date,
        )

    def for_player_map_stats(
        self,
        stats: PlayerMapStats,
        *,
        reference_end: datetime | None = None,
    ) -> MapContextFeatures:
        all_observations = self.load_observations(reference_end=reference_end)
        feature_engine = self._feature_service._build_feature_engine()
        return MapContextFeatures(
            match_map_id=str(stats.match_map_id),
            features=self.adjust_player_map_stats(
                stats,
                all_observations=all_observations,
                feature_engine=feature_engine,
            ),
        )

    def adjust_player_map_stats(
        self,
        stats: PlayerMapStats,
        *,
        all_observations: list[ContextObservation],
        feature_engine: FeatureEngine | None = None,
    ) -> ContextAdjustedFeatures:
        observation = observation_from_player_map_stats(stats)
        reference = filter_reference_observations(all_observations, observation)
        registry = build_baseline_registry(reference)
        engine = feature_engine or self._feature_service._build_feature_engine()
        residual_adr = engine.from_player_map_stats(stats).residual_adr
        return adjust_context_observation(
            observation,
            residual_adr=residual_adr,
            registry=registry,
            thresholds=self._thresholds,
        )

    def load_observations(
        self,
        *,
        reference_end: datetime | None = None,
    ) -> list[ContextObservation]:
        rows = self._stats_service.load_player_map_stats(None)
        observations = [observation_from_player_map_stats(row) for row in rows]
        if reference_end is None:
            return observations
        return [
            observation
            for observation in observations
            if observation.played_at is None or observation.played_at < reference_end
        ]


def observation_from_player_map_stats(stats: PlayerMapStats) -> ContextObservation:
    agent = stats.agent
    match_map = stats.match_map
    match = match_map.match
    event = match.event
    return ContextObservation(
        observation_id=stats.id,
        role=agent.role,
        agent_name=agent.name,
        map_name=match_map.map_name,
        tier=event.tier,
        played_at=match.played_at,
        rounds=stats.rounds,
        kills=stats.kills,
        deaths=stats.deaths,
        assists=stats.assists,
        first_kills=stats.first_kills,
        first_deaths=stats.first_deaths,
        kast_pct=stats.kast_pct,
        clutch_wins=stats.clutch_wins,
        clutch_attempts=stats.clutch_attempts,
    )
