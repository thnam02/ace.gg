from __future__ import annotations

from app.metrics.cir_scoring import apply_shrinkage, empirical_cdf, round_weighted_mean
from app.metrics.mir.mir_components import (
    MirComponentDefinition,
    breakdown_components,
    component_contribution,
)
from app.metrics.mir.mir_config import COMBAT_FEATURES, OPENING_FEATURES, SUPPORT_FEATURES
from app.schemas.mir import MirScore


def compute_raw_mir(
    standardized_features: dict[str, float],
    coefficients: dict[str, float],
    feature_names: tuple[str, ...],
) -> float:
    total = 0.0
    for name in feature_names:
        total += coefficients.get(name, 0.0) * standardized_features.get(name, 0.0)
    return total


def reliability_score(rounds: int, maps_played: int, *, shrinkage_k: float = 50.0) -> float:
    """Separate from MIR. Simple sample-size reliability, not a performance term."""
    if rounds <= 0:
        return 0.0
    round_score = 100.0 * rounds / (rounds + shrinkage_k)
    map_factor = min(1.0, maps_played / 8.0) if maps_played > 0 else 0.0
    return max(0.0, min(100.0, round_score * (0.7 + 0.3 * map_factor)))


def build_mir_score(
    *,
    raw_values: list[tuple[float, int]],
    combat_values: list[tuple[float, int]],
    support_values: list[tuple[float, int]],
    opening_values: list[tuple[float, int]],
    reference_mean: float,
    reference_population: list[float],
    shrinkage_k: float,
    enabled_components: list[str],
    metric_version: str,
    maps_played: int,
) -> MirScore:
    raw = round_weighted_mean(raw_values)
    rounds = sum(weight for _, weight in raw_values)
    if raw is None:
        return MirScore(
            rounds=rounds,
            maps=maps_played,
            enabled_components=enabled_components,
            metric_version=metric_version,
        )
    shrunk = apply_shrinkage(raw, rounds, reference_mean, shrinkage_k)
    percentile = empirical_cdf(shrunk, reference_population)
    return MirScore(
        overall_mir=percentile,
        raw_mir=raw,
        shrunk_mir=shrunk,
        percentile=percentile,
        combat_component=round_weighted_mean(combat_values),
        support_component=round_weighted_mean(support_values),
        opening_component=round_weighted_mean(opening_values),
        economy_component=None,
        rounds=rounds,
        maps=maps_played,
        reliability=reliability_score(rounds, maps_played, shrinkage_k=shrinkage_k),
        sample_weight=rounds / (rounds + shrinkage_k) if rounds > 0 else 0.0,
        enabled_components=enabled_components,
        metric_version=metric_version,
    )


def map_component_values(
    standardized_features: dict[str, float],
    coefficients: dict[str, float],
    definitions: tuple[MirComponentDefinition, ...],
    exposure_rounds: int,
) -> dict[str, float]:
    breakdown = breakdown_components(
        standardized_features,
        coefficients,
        definitions,
        exposure_rounds=exposure_rounds,
    )
    return {name: item.coefficient_contribution or 0.0 for name, item in breakdown.items()}


def default_component_feature_groups() -> dict[str, tuple[str, ...]]:
    return {
        "combat": COMBAT_FEATURES,
        "support": SUPPORT_FEATURES,
        "opening": OPENING_FEATURES,
        "economy": (),
    }


def enabled_component_names(feature_names: tuple[str, ...]) -> list[str]:
    names = set(feature_names)
    enabled = ["combat"]
    if any(item in names for item in SUPPORT_FEATURES):
        enabled.append("support")
    if any(item in names for item in OPENING_FEATURES):
        enabled.append("opening")
    return enabled


def contribution_for_group(
    standardized_features: dict[str, float],
    coefficients: dict[str, float],
    group: tuple[str, ...],
    enabled: bool,
) -> float:
    return component_contribution(
        standardized_features,
        coefficients,
        group,
        enabled=enabled,
    )
