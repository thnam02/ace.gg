from __future__ import annotations

from uuid import UUID

from app.metrics.adr_regression import AdrRegressionModel
from app.metrics.bayesian_clutch import ClutchPrior, compute_bayesian_clutch
from app.metrics.derived import compute_derived
from app.metrics.stats_engine import player_map_stats_to_raw
from app.models import PlayerMapStats
from app.schemas.features import CIRFeatures, MapCIRFeatures, PlayerCIRFeatures
from app.schemas.stats import MapStatsDerived, MapStatsFeatures, MapStatsRaw, PlayerStatsAggregate


class FeatureEngine:
    """CIR-ready features built on StatsEngine outputs."""

    def __init__(
        self,
        adr_model: AdrRegressionModel,
        clutch_prior: ClutchPrior,
    ) -> None:
        self._adr_model = adr_model
        self._clutch_prior = clutch_prior

    def from_raw(
        self,
        raw: MapStatsRaw,
        *,
        derived: MapStatsDerived | None = None,
        match_map_id: UUID | None = None,
    ) -> CIRFeatures:
        resolved_derived = derived or compute_derived(raw)
        return self._build_features(raw, resolved_derived)

    def from_map_features(self, features: MapStatsFeatures) -> MapCIRFeatures:
        return MapCIRFeatures(
            match_map_id=str(features.match_map_id) if features.match_map_id else None,
            features=self._build_features(features.raw, features.derived),
        )

    def from_player_map_stats(self, stats: PlayerMapStats) -> CIRFeatures:
        raw = player_map_stats_to_raw(stats)
        derived = compute_derived(raw)
        return self._build_features(raw, derived)

    def from_aggregate(self, aggregate: PlayerStatsAggregate) -> CIRFeatures:
        raw = MapStatsRaw(
            rounds=aggregate.raw.rounds,
            kills=aggregate.raw.kills,
            deaths=aggregate.raw.deaths,
            assists=aggregate.raw.assists,
            first_kills=aggregate.raw.first_kills,
            first_deaths=aggregate.raw.first_deaths,
            adr=aggregate.raw.weighted_adr,
            kast_pct=aggregate.raw.weighted_kast,
            clutch_wins=aggregate.raw.clutch_wins,
            clutch_attempts=aggregate.raw.clutch_attempts,
        )
        return self._build_features(raw, aggregate.derived)

    def build_player_features(
        self,
        player_id: UUID,
        aggregate: PlayerStatsAggregate,
    ) -> PlayerCIRFeatures:
        map_features = [self.from_map_features(feature) for feature in aggregate.maps]
        return PlayerCIRFeatures(
            player_id=str(player_id),
            aggregate=self.from_aggregate(aggregate),
            maps=map_features,
        )

    def _build_features(self, raw: MapStatsRaw, derived: MapStatsDerived) -> CIRFeatures:
        expected_adr, residual_adr = self._adr_model.expected_and_residual(raw.adr, derived.kpr)
        clutch = compute_bayesian_clutch(
            raw.clutch_wins,
            raw.clutch_attempts,
            self._clutch_prior,
        )
        return CIRFeatures(
            kpr=derived.kpr,
            dpr=derived.dpr,
            apr=derived.apr,
            fkpr=derived.fkpr,
            fdpr=derived.fdpr,
            opening_frequency=derived.opening_frequency,
            opening_efficiency=derived.opening_efficiency,
            adr=raw.adr,
            expected_adr=expected_adr,
            residual_adr=residual_adr,
            kast=raw.kast_pct,
            raw_clutch_rate=clutch.raw_clutch_rate,
            bayesian_clutch_rate=clutch.bayesian_clutch_rate,
            clutch_attempts=clutch.clutch_attempts,
            clutch_effective_sample_size=clutch.effective_sample_size,
        )

