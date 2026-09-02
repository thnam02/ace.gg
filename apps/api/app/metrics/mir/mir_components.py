from __future__ import annotations

from dataclasses import dataclass

from app.metrics.mir.mir_config import (
    COMBAT_FEATURES,
    OPENING_FEATURES,
    SUPPORT_FEATURES,
)
from app.schemas.mir import MirComponentBreakdown


@dataclass(frozen=True)
class MirComponentDefinition:
    name: str
    features: tuple[str, ...]
    enabled: bool


def mir_component_definitions(
    enabled_features: set[str],
) -> tuple[MirComponentDefinition, ...]:
    return (
        MirComponentDefinition(
            name="combat",
            features=COMBAT_FEATURES,
            enabled=any(name in enabled_features for name in COMBAT_FEATURES),
        ),
        MirComponentDefinition(
            name="support",
            features=SUPPORT_FEATURES,
            enabled=any(name in enabled_features for name in SUPPORT_FEATURES),
        ),
        MirComponentDefinition(
            name="opening",
            features=OPENING_FEATURES,
            enabled=any(name in enabled_features for name in OPENING_FEATURES),
        ),
        MirComponentDefinition(
            name="economy",
            features=(),
            enabled=False,
        ),
    )


def component_contribution(
    standardized_features: dict[str, float],
    coefficients: dict[str, float],
    feature_names: tuple[str, ...],
    *,
    enabled: bool,
) -> float:
    if not enabled:
        return 0.0
    total = 0.0
    for name in feature_names:
        total += coefficients.get(name, 0.0) * standardized_features.get(name, 0.0)
    return total


def breakdown_components(
    standardized_features: dict[str, float],
    coefficients: dict[str, float],
    definitions: tuple[MirComponentDefinition, ...],
    *,
    exposure_rounds: int,
) -> dict[str, MirComponentBreakdown]:
    rows: dict[str, MirComponentBreakdown] = {}
    for definition in definitions:
        raw = component_contribution(
            standardized_features,
            coefficients,
            definition.features,
            enabled=definition.enabled,
        )
        rows[definition.name] = MirComponentBreakdown(
            name=definition.name,
            raw_value=raw,
            standardized_value=raw,
            coefficient_contribution=raw,
            enabled=definition.enabled,
            exposure_rounds=exposure_rounds,
        )
    return rows
