from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.metrics.bayesian_clutch import (
    bayesian_rate,
    estimate_beta_prior,
    estimate_beta_prior_from_exposure,
)
from app.metrics.derived import safe_ratio
from app.schemas.context_features import ContextAdjustedFeatures


class BaselineLevel(StrEnum):
    AGENT_MAP_TIER = "agent_map_tier"
    ROLE_MAP_TIER = "role_map_tier"
    ROLE_TIER = "role_tier"
    TIER = "tier"
    GLOBAL = "global"


BASELINE_HIERARCHY: tuple[BaselineLevel, ...] = (
    BaselineLevel.AGENT_MAP_TIER,
    BaselineLevel.ROLE_MAP_TIER,
    BaselineLevel.ROLE_TIER,
    BaselineLevel.TIER,
    BaselineLevel.GLOBAL,
)


@dataclass(frozen=True)
class BaselineThresholds:
    agent_map_tier_min_rounds: int = 200
    role_map_tier_min_rounds: int = 100
    role_tier_min_rounds: int = 50
    tier_min_rounds: int = 20
    global_min_rounds: int = 1

    def min_rounds_for(self, level: BaselineLevel) -> int:
        mapping = {
            BaselineLevel.AGENT_MAP_TIER: self.agent_map_tier_min_rounds,
            BaselineLevel.ROLE_MAP_TIER: self.role_map_tier_min_rounds,
            BaselineLevel.ROLE_TIER: self.role_tier_min_rounds,
            BaselineLevel.TIER: self.tier_min_rounds,
            BaselineLevel.GLOBAL: self.global_min_rounds,
        }
        return mapping[level]


@dataclass(frozen=True)
class ContextObservation:
    observation_id: UUID
    role: str
    agent_name: str
    map_name: str
    tier: str | None
    played_at: datetime | None
    rounds: int
    kills: int
    deaths: int
    assists: int
    first_kills: int
    first_deaths: int
    kast_pct: float | None
    clutch_wins: int | None
    clutch_attempts: int | None


@dataclass
class ContextExposure:
    rounds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    first_kills: int = 0
    first_deaths: int = 0
    kast_rounds: float = 0.0
    clutch_wins: int = 0
    clutch_attempts: int = 0
    observation_count: int = 0
    opening_efficiency_pairs: list[tuple[int, int]] = field(default_factory=list)
    clutch_pairs: list[tuple[int, int]] = field(default_factory=list)

    def add(self, observation: ContextObservation) -> None:
        self.rounds += observation.rounds
        self.kills += observation.kills
        self.deaths += observation.deaths
        self.assists += observation.assists
        self.first_kills += observation.first_kills
        self.first_deaths += observation.first_deaths
        self.observation_count += 1

        kast_rounds = approximate_kast_rounds(observation)
        if kast_rounds is not None:
            self.kast_rounds += kast_rounds

        opening_duels = observation.first_kills + observation.first_deaths
        if opening_duels > 0:
            self.opening_efficiency_pairs.append(
                (observation.first_kills, observation.first_deaths)
            )

        if observation.clutch_attempts is not None and observation.clutch_attempts > 0:
            wins = observation.clutch_wins or 0
            self.clutch_wins += wins
            self.clutch_attempts += observation.clutch_attempts
            self.clutch_pairs.append((wins, observation.clutch_attempts))


@dataclass
class BaselineRegistry:
    agent_map_tier: dict[tuple[str, str, str | None], ContextExposure] = field(default_factory=dict)
    role_map_tier: dict[tuple[str, str, str | None], ContextExposure] = field(default_factory=dict)
    role_tier: dict[tuple[str, str | None], ContextExposure] = field(default_factory=dict)
    tier: dict[str | None, ContextExposure] = field(default_factory=dict)
    global_exposure: ContextExposure = field(default_factory=ContextExposure)


def approximate_kast_rounds(observation: ContextObservation) -> float | None:
    if observation.kast_pct is None or observation.rounds == 0:
        return None
    # KAST is stored as a percentage (e.g. 76.2); approximate round counts via rounding.
    return round(observation.kast_pct / 100.0 * observation.rounds)


def build_baseline_registry(observations: list[ContextObservation]) -> BaselineRegistry:
    registry = BaselineRegistry()
    for observation in observations:
        _add_to_registry(registry, observation)
    return registry


def _add_to_registry(registry: BaselineRegistry, observation: ContextObservation) -> None:
    tier = observation.tier
    agent_map_key = (observation.agent_name, observation.map_name, tier)
    role_map_key = (observation.role, observation.map_name, tier)
    role_tier_key = (observation.role, tier)

    _get_or_create(registry.agent_map_tier, agent_map_key).add(observation)
    _get_or_create(registry.role_map_tier, role_map_key).add(observation)
    _get_or_create(registry.role_tier, role_tier_key).add(observation)
    _get_or_create(registry.tier, tier).add(observation)
    registry.global_exposure.add(observation)


def _get_or_create(mapping: dict[Any, ContextExposure], key: Any) -> ContextExposure:
    if key not in mapping:
        mapping[key] = ContextExposure()
    exposure = mapping[key]
    return exposure


def exposure_for_level(
    registry: BaselineRegistry,
    level: BaselineLevel,
    observation: ContextObservation,
) -> ContextExposure:
    tier = observation.tier
    if level == BaselineLevel.AGENT_MAP_TIER:
        return registry.agent_map_tier.get(
            (observation.agent_name, observation.map_name, tier),
            ContextExposure(),
        )
    if level == BaselineLevel.ROLE_MAP_TIER:
        return registry.role_map_tier.get(
            (observation.role, observation.map_name, tier),
            ContextExposure(),
        )
    if level == BaselineLevel.ROLE_TIER:
        return registry.role_tier.get((observation.role, tier), ContextExposure())
    if level == BaselineLevel.TIER:
        return registry.tier.get(tier, ContextExposure())
    return registry.global_exposure


def select_baseline_level(
    registry: BaselineRegistry,
    observation: ContextObservation,
    thresholds: BaselineThresholds,
) -> tuple[BaselineLevel, ContextExposure]:
    for level in BASELINE_HIERARCHY:
        exposure = exposure_for_level(registry, level, observation)
        min_rounds = thresholds.min_rounds_for(level)
        if exposure.observation_count > 0 and exposure.rounds >= min_rounds:
            return level, exposure
    return BaselineLevel.GLOBAL, registry.global_exposure


def filter_reference_observations(
    observations: list[ContextObservation],
    evaluation: ContextObservation,
) -> list[ContextObservation]:
    return [
        observation
        for observation in observations
        if observation.observation_id != evaluation.observation_id
        and _is_not_future(observation, evaluation)
    ]


def _is_not_future(reference: ContextObservation, evaluation: ContextObservation) -> bool:
    if evaluation.played_at is None or reference.played_at is None:
        return True
    return reference.played_at <= evaluation.played_at


def adjust_context_observation(
    observation: ContextObservation,
    *,
    residual_adr: float | None,
    registry: BaselineRegistry,
    thresholds: BaselineThresholds = BaselineThresholds(),
) -> ContextAdjustedFeatures:
    level, exposure = select_baseline_level(registry, observation, thresholds)

    kpr = safe_ratio(observation.kills, observation.rounds)
    dpr = safe_ratio(observation.deaths, observation.rounds)
    apr = safe_ratio(observation.assists, observation.rounds)

    kpr_expected = safe_ratio(exposure.kills, exposure.rounds)
    dpr_expected = safe_ratio(exposure.deaths, exposure.rounds)
    apr_expected = safe_ratio(exposure.assists, exposure.rounds)

    opening_duels = observation.first_kills + observation.first_deaths
    opening_frequency = safe_ratio(opening_duels, observation.rounds)
    opening_frequency_expected = safe_ratio(
        exposure.first_kills + exposure.first_deaths,
        exposure.rounds,
    )

    opening_efficiency_raw = safe_ratio(observation.first_kills, opening_duels)
    oe_prior = (
        estimate_beta_prior(exposure.opening_efficiency_pairs)
        if exposure.opening_efficiency_pairs
        else estimate_beta_prior_from_exposure(
            exposure.first_kills,
            exposure.first_deaths,
            exposure.observation_count,
        )
    )
    opening_efficiency_adjusted = (
        bayesian_rate(observation.first_kills, observation.first_deaths, oe_prior)
        if opening_duels > 0
        else None
    )

    kast = observation.kast_pct
    kast_expected = _kast_expected_pct(exposure)

    clutch_attempts = observation.clutch_attempts
    clutch_wins = observation.clutch_wins or 0
    clutch_rate_raw = (
        safe_ratio(clutch_wins, clutch_attempts)
        if clutch_attempts is not None and clutch_attempts > 0
        else None
    )
    clutch_prior = (
        estimate_beta_prior(exposure.clutch_pairs)
        if exposure.clutch_pairs
        else estimate_beta_prior_from_exposure(
            exposure.clutch_wins,
            exposure.clutch_attempts - exposure.clutch_wins,
            exposure.observation_count,
        )
    )
    clutch_rate_adjusted = None
    if clutch_attempts is not None and clutch_attempts > 0:
        failures = clutch_attempts - clutch_wins
        clutch_rate_adjusted = bayesian_rate(clutch_wins, failures, clutch_prior)

    return ContextAdjustedFeatures(
        kpr=kpr,
        kpr_expected=kpr_expected,
        kpr_residual=_residual(kpr, kpr_expected),
        dpr=dpr,
        dpr_expected=dpr_expected,
        dpr_residual=_residual(dpr, dpr_expected),
        apr=apr,
        apr_expected=apr_expected,
        apr_residual=_residual(apr, apr_expected),
        opening_frequency=opening_frequency,
        opening_frequency_expected=opening_frequency_expected,
        opening_frequency_residual=_residual(opening_frequency, opening_frequency_expected),
        opening_efficiency_raw=opening_efficiency_raw,
        opening_efficiency_adjusted=opening_efficiency_adjusted,
        kast=kast,
        kast_expected=kast_expected,
        kast_residual=_residual(kast, kast_expected),
        residual_adr=residual_adr,
        clutch_rate_raw=clutch_rate_raw,
        clutch_rate_adjusted=clutch_rate_adjusted,
        baseline_level=level.value,
        reference_rounds=exposure.rounds,
        reference_observations=exposure.observation_count,
    )


def _kast_expected_pct(exposure: ContextExposure) -> float | None:
    if exposure.rounds == 0:
        return None
    return (exposure.kast_rounds / exposure.rounds) * 100.0


def _residual(observed: float | None, expected: float | None) -> float | None:
    if observed is None or expected is None:
        return None
    return observed - expected
