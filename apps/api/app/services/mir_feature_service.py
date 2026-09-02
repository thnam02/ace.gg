from __future__ import annotations

from dataclasses import dataclass, field

from app.metrics.cir_standardization import (
    StandardizationParams,
    fit_standardization,
    standardize_features,
)
from app.metrics.mir.mir_config import ALL_MODEL_FEATURES
from app.metrics.mir.mir_features import alias_context_features, opening_attempts
from app.metrics.mir.mir_residualization import (
    MirResidualizers,
    apply_mir_residualizers,
    fit_mir_residualizers,
)
from app.models import PlayerMapStats
from app.services.cir_training_service import _PlayerMapPrepared


@dataclass
class MirPlayerMap:
    stats: PlayerMapStats
    split: str
    raw_features: dict[str, float | None]
    standardized_features: dict[str, float] = field(default_factory=dict)
    role: str = "Unknown"
    tier: str = "Unknown"
    agent_name: str | None = None


class MirFeatureService:
    """Build unique MIR features from context-adjusted CIR player-maps. Train-only fits."""

    def transform(
        self,
        prepared_maps: list[_PlayerMapPrepared],
        *,
        feature_names: tuple[str, ...] = ALL_MODEL_FEATURES,
    ) -> tuple[list[MirPlayerMap], MirResidualizers, StandardizationParams]:
        aliased_rows: list[dict[str, float | None]] = []
        attempts: list[int] = []
        for row in prepared_maps:
            aliased_rows.append(alias_context_features(row.raw_features))
            attempts.append(opening_attempts(row.stats.first_kills, row.stats.first_deaths))

        train_rows = [
            features
            for features, prepared in zip(aliased_rows, prepared_maps, strict=True)
            if prepared.split == "train"
        ]
        train_attempts = [
            count
            for count, prepared in zip(attempts, prepared_maps, strict=True)
            if prepared.split == "train"
        ]
        residualizers = fit_mir_residualizers(train_rows, opening_attempts=train_attempts)

        unique_rows: list[dict[str, float | None]] = []
        for features, prepared, count in zip(aliased_rows, prepared_maps, attempts, strict=True):
            unique_rows.append(
                apply_mir_residualizers(features, residualizers, opening_attempts=count)
            )

        train_unique = [
            features
            for features, prepared in zip(unique_rows, prepared_maps, strict=True)
            if prepared.split == "train"
        ]
        standardization = fit_standardization(train_unique, feature_names=feature_names)
        maps: list[MirPlayerMap] = []
        for prepared, features in zip(prepared_maps, unique_rows, strict=True):
            role = prepared.stats.agent.role if prepared.stats.agent is not None else "Unknown"
            event = prepared.stats.match_map.match.event
            tier = (event.tier or "Unknown") if event is not None else "Unknown"
            agent_name = prepared.stats.agent.name if prepared.stats.agent is not None else None
            maps.append(
                MirPlayerMap(
                    stats=prepared.stats,
                    split=prepared.split,
                    raw_features=features,
                    standardized_features=standardize_features(
                        features,
                        standardization,
                        feature_names=feature_names,
                    ),
                    role=role,
                    tier=tier,
                    agent_name=agent_name,
                )
            )
        return maps, residualizers, standardization
