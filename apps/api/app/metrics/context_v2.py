from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.metrics.context_baselines import ContextExposure, ContextObservation
from app.metrics.derived import safe_ratio
from app.schemas.context_features import ContextAdjustedFeatures

RATE_FEATURE_NAMES: tuple[str, ...] = (
    "kpr",
    "dpr",
    "apr",
    "kast",
    "opening_frequency",
    "opening_efficiency",
    "clutch",
)


class ContextV2Level(StrEnum):
    NONE = "none"
    ROLE = "role"
    AGENT = "agent"
    ROLE_TIER = "role_tier"
    AGENT_TIER = "agent_tier"
    ROLE_MAP_TIER = "role_map_tier"
    AGENT_MAP_TIER = "agent_map_tier"
    TIER = "tier"
    GLOBAL = "global"


PARENT_LEVEL: dict[ContextV2Level, ContextV2Level | None] = {
    ContextV2Level.AGENT_MAP_TIER: ContextV2Level.AGENT_TIER,
    ContextV2Level.AGENT_TIER: ContextV2Level.ROLE_TIER,
    ContextV2Level.ROLE_MAP_TIER: ContextV2Level.ROLE_TIER,
    ContextV2Level.ROLE_TIER: ContextV2Level.TIER,
    ContextV2Level.AGENT: ContextV2Level.ROLE,
    ContextV2Level.ROLE: ContextV2Level.GLOBAL,
    ContextV2Level.TIER: ContextV2Level.GLOBAL,
    ContextV2Level.GLOBAL: None,
    ContextV2Level.NONE: None,
}


@dataclass(frozen=True)
class FeatureContextRule:
    feature: str
    level: ContextV2Level


@dataclass
class ContextV2Registry:
    agent_map_tier: dict[tuple[str, str, str | None], ContextExposure] = field(default_factory=dict)
    agent_tier: dict[tuple[str, str | None], ContextExposure] = field(default_factory=dict)
    role_map_tier: dict[tuple[str, str, str | None], ContextExposure] = field(default_factory=dict)
    role_tier: dict[tuple[str, str | None], ContextExposure] = field(default_factory=dict)
    agent: dict[str, ContextExposure] = field(default_factory=dict)
    role: dict[str, ContextExposure] = field(default_factory=dict)
    tier: dict[str | None, ContextExposure] = field(default_factory=dict)
    global_exposure: ContextExposure = field(default_factory=ContextExposure)


def build_context_v2_registry(observations: list[ContextObservation]) -> ContextV2Registry:
    registry = ContextV2Registry()
    for observation in observations:
        _add_observation(registry, observation)
    return registry


def _add_observation(registry: ContextV2Registry, observation: ContextObservation) -> None:
    tier = observation.tier
    _get_or_create(
        registry.agent_map_tier,
        (observation.agent_name, observation.map_name, tier),
    ).add(observation)
    _get_or_create(registry.agent_tier, (observation.agent_name, tier)).add(observation)
    _get_or_create(
        registry.role_map_tier,
        (observation.role, observation.map_name, tier),
    ).add(observation)
    _get_or_create(registry.role_tier, (observation.role, tier)).add(observation)
    _get_or_create(registry.agent, observation.agent_name).add(observation)
    _get_or_create(registry.role, observation.role).add(observation)
    _get_or_create(registry.tier, tier).add(observation)
    registry.global_exposure.add(observation)


def _get_or_create(mapping: dict[Any, ContextExposure], key: Any) -> ContextExposure:
    if key not in mapping:
        mapping[key] = ContextExposure()
    return mapping[key]


def exposure_for_v2_level(
    registry: ContextV2Registry,
    level: ContextV2Level,
    observation: ContextObservation,
) -> ContextExposure:
    tier = observation.tier
    if level == ContextV2Level.AGENT_MAP_TIER:
        return registry.agent_map_tier.get(
            (observation.agent_name, observation.map_name, tier),
            ContextExposure(),
        )
    if level == ContextV2Level.AGENT_TIER:
        return registry.agent_tier.get((observation.agent_name, tier), ContextExposure())
    if level == ContextV2Level.ROLE_MAP_TIER:
        return registry.role_map_tier.get(
            (observation.role, observation.map_name, tier),
            ContextExposure(),
        )
    if level == ContextV2Level.ROLE_TIER:
        return registry.role_tier.get((observation.role, tier), ContextExposure())
    if level == ContextV2Level.AGENT:
        return registry.agent.get(observation.agent_name, ContextExposure())
    if level == ContextV2Level.ROLE:
        return registry.role.get(observation.role, ContextExposure())
    if level == ContextV2Level.TIER:
        return registry.tier.get(tier, ContextExposure())
    return registry.global_exposure


def observed_rate(observation: ContextObservation, feature: str) -> float | None:
    if feature == "kpr":
        return safe_ratio(observation.kills, observation.rounds)
    if feature == "dpr":
        return safe_ratio(observation.deaths, observation.rounds)
    if feature == "apr":
        return safe_ratio(observation.assists, observation.rounds)
    if feature == "kast":
        return observation.kast_pct
    if feature == "opening_frequency":
        return safe_ratio(
            observation.first_kills + observation.first_deaths,
            observation.rounds,
        )
    if feature == "opening_efficiency":
        return safe_ratio(
            observation.first_kills,
            observation.first_kills + observation.first_deaths,
        )
    if feature == "clutch":
        if observation.clutch_attempts is None or observation.clutch_attempts <= 0:
            return None
        return safe_ratio(observation.clutch_wins or 0, observation.clutch_attempts)
    raise KeyError(f"Unknown rate feature: {feature}")


def rate_from_exposure(exposure: ContextExposure, feature: str) -> float | None:
    if feature == "kpr":
        return safe_ratio(exposure.kills, exposure.rounds)
    if feature == "dpr":
        return safe_ratio(exposure.deaths, exposure.rounds)
    if feature == "apr":
        return safe_ratio(exposure.assists, exposure.rounds)
    if feature == "kast":
        if exposure.rounds == 0:
            return None
        return (exposure.kast_rounds / exposure.rounds) * 100.0
    if feature == "opening_frequency":
        return safe_ratio(exposure.first_kills + exposure.first_deaths, exposure.rounds)
    if feature == "opening_efficiency":
        return safe_ratio(exposure.first_kills, exposure.first_kills + exposure.first_deaths)
    if feature == "clutch":
        return safe_ratio(exposure.clutch_wins, exposure.clutch_attempts)
    raise KeyError(f"Unknown rate feature: {feature}")


def exposure_weight(exposure: ContextExposure, feature: str) -> float:
    if feature == "opening_efficiency":
        return float(exposure.first_kills + exposure.first_deaths)
    if feature == "clutch":
        return float(exposure.clutch_attempts)
    if feature == "kast":
        return float(exposure.rounds)
    return float(exposure.rounds)


def partial_residual(
    observed: float | None,
    context_mean: float | None,
    global_mean: float | None,
    lam: float,
) -> float | None:
    if observed is None:
        return None
    if lam <= 0.0 or context_mean is None or global_mean is None:
        return observed
    clamped = min(1.0, max(0.0, lam))
    return observed - clamped * (context_mean - global_mean)


def hierarchical_mean(
    registry: ContextV2Registry,
    observation: ContextObservation,
    level: ContextV2Level,
    feature: str,
    tau: float,
) -> tuple[float | None, str]:
    """Return (shrunk mean, leaf level actually used for reporting)."""
    if level == ContextV2Level.NONE:
        global_mean = rate_from_exposure(registry.global_exposure, feature)
        return global_mean, ContextV2Level.NONE.value
    mean = _shrunk_mean(registry, observation, level, feature, tau)
    return mean, level.value


def _shrunk_mean(
    registry: ContextV2Registry,
    observation: ContextObservation,
    level: ContextV2Level,
    feature: str,
    tau: float,
) -> float | None:
    if level == ContextV2Level.NONE:
        return rate_from_exposure(registry.global_exposure, feature)
    exposure = exposure_for_v2_level(registry, level, observation)
    specific = rate_from_exposure(exposure, feature)
    parent = PARENT_LEVEL[level]
    if parent is None:
        return specific
    parent_mean = _shrunk_mean(registry, observation, parent, feature, tau)
    weight = _shrink_weight(exposure_weight(exposure, feature), tau)
    if specific is None:
        return parent_mean
    if parent_mean is None:
        return specific
    return weight * specific + (1.0 - weight) * parent_mean


def _shrink_weight(exposure: float, tau: float) -> float:
    if exposure <= 0.0:
        return 0.0
    if tau <= 0.0:
        return 1.0
    return exposure / (exposure + tau)


def adjust_context_v2_observation(
    observation: ContextObservation,
    *,
    residual_adr: float | None,
    registry: ContextV2Registry,
    rules: dict[str, FeatureContextRule],
    lam: float,
    tau: float,
) -> ContextAdjustedFeatures:
    global_means = {
        feature: rate_from_exposure(registry.global_exposure, feature)
        for feature in RATE_FEATURE_NAMES
    }
    expected: dict[str, float | None] = {}
    levels: dict[str, str] = {}
    residuals: dict[str, float | None] = {}
    observed: dict[str, float | None] = {}

    for feature in RATE_FEATURE_NAMES:
        rule = rules.get(feature, FeatureContextRule(feature, ContextV2Level.NONE))
        observed[feature] = observed_rate(observation, feature)
        if rule.level == ContextV2Level.NONE or lam <= 0.0:
            expected[feature] = global_means[feature]
            levels[feature] = ContextV2Level.NONE.value
            residuals[feature] = observed[feature]
            continue
        context_mean, used_level = hierarchical_mean(
            registry,
            observation,
            rule.level,
            feature,
            tau,
        )
        expected[feature] = context_mean
        levels[feature] = used_level
        residuals[feature] = partial_residual(
            observed[feature],
            context_mean,
            global_means[feature],
            lam,
        )

    kpr = observed["kpr"]
    dpr = observed["dpr"]
    apr = observed["apr"]
    opening_frequency = observed["opening_frequency"]
    clutch_attempts = observation.clutch_attempts
    clutch_rate_raw = observed["clutch"]

    primary_level = levels.get("kpr") or ContextV2Level.NONE.value
    return ContextAdjustedFeatures(
        kpr=kpr,
        kpr_expected=expected["kpr"],
        kpr_residual=residuals["kpr"],
        dpr=dpr,
        dpr_expected=expected["dpr"],
        dpr_residual=residuals["dpr"],
        apr=apr,
        apr_expected=expected["apr"],
        apr_residual=residuals["apr"],
        opening_frequency=opening_frequency,
        opening_frequency_expected=expected["opening_frequency"],
        opening_frequency_residual=residuals["opening_frequency"],
        opening_efficiency_raw=observed["opening_efficiency"],
        opening_efficiency_adjusted=residuals["opening_efficiency"],
        kast=observed["kast"],
        kast_expected=expected["kast"],
        kast_residual=residuals["kast"],
        residual_adr=residual_adr,
        clutch_rate_raw=clutch_rate_raw,
        clutch_rate_adjusted=residuals["clutch"] if clutch_attempts else None,
        baseline_level=primary_level,
        reference_rounds=registry.global_exposure.rounds,
        reference_observations=registry.global_exposure.observation_count,
        feature_baseline_levels=levels,
    )


def no_context_features(
    observation: ContextObservation,
    *,
    residual_adr: float | None,
) -> ContextAdjustedFeatures:
    kpr = observed_rate(observation, "kpr")
    dpr = observed_rate(observation, "dpr")
    apr = observed_rate(observation, "apr")
    opening_frequency = observed_rate(observation, "opening_frequency")
    opening_efficiency = observed_rate(observation, "opening_efficiency")
    kast = observed_rate(observation, "kast")
    clutch = observed_rate(observation, "clutch")
    none_levels = {feature: ContextV2Level.NONE.value for feature in RATE_FEATURE_NAMES}
    return ContextAdjustedFeatures(
        kpr=kpr,
        kpr_expected=None,
        kpr_residual=kpr,
        dpr=dpr,
        dpr_expected=None,
        dpr_residual=dpr,
        apr=apr,
        apr_expected=None,
        apr_residual=apr,
        opening_frequency=opening_frequency,
        opening_frequency_expected=None,
        opening_frequency_residual=opening_frequency,
        opening_efficiency_raw=opening_efficiency,
        opening_efficiency_adjusted=opening_efficiency,
        kast=kast,
        kast_expected=None,
        kast_residual=kast,
        residual_adr=residual_adr,
        clutch_rate_raw=clutch,
        clutch_rate_adjusted=clutch,
        baseline_level=ContextV2Level.NONE.value,
        reference_rounds=0,
        reference_observations=0,
        feature_baseline_levels=none_levels,
    )
