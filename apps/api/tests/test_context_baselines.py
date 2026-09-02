from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.metrics.bayesian_clutch import estimate_beta_prior
from app.metrics.context_baselines import (
    BaselineLevel,
    BaselineRegistry,
    BaselineThresholds,
    ContextObservation,
    adjust_context_observation,
    approximate_kast_rounds,
    build_baseline_registry,
    filter_reference_observations,
    select_baseline_level,
)


def _obs(
    observation_id: int,
    *,
    role: str = "Duelist",
    agent_name: str = "Jett",
    map_name: str = "Bind",
    tier: str | None = "S",
    rounds: int = 20,
    kills: int = 10,
    deaths: int = 8,
    assists: int = 4,
    first_kills: int = 3,
    first_deaths: int = 2,
    kast_pct: float | None = 70.0,
    clutch_wins: int | None = 1,
    clutch_attempts: int | None = 2,
    played_at: datetime | None = None,
) -> ContextObservation:
    return ContextObservation(
        observation_id=UUID(int=observation_id),
        role=role,
        agent_name=agent_name,
        map_name=map_name,
        tier=tier,
        played_at=played_at,
        rounds=rounds,
        kills=kills,
        deaths=deaths,
        assists=assists,
        first_kills=first_kills,
        first_deaths=first_deaths,
        kast_pct=kast_pct,
        clutch_wins=clutch_wins,
        clutch_attempts=clutch_attempts,
    )


def test_exposure_weighted_kpr_dpr_apr_baselines() -> None:
    references = [
        _obs(1, rounds=20, kills=10, deaths=6, assists=2),
        _obs(2, rounds=30, kills=15, deaths=12, assists=6),
    ]
    registry = build_baseline_registry(references)
    evaluation = _obs(3, agent_name="Reyna", rounds=20, kills=12, deaths=8, assists=4)
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=5.0,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.kpr == pytest.approx(12 / 20)
    assert adjusted.kpr_expected == pytest.approx(25 / 50)
    assert adjusted.kpr_residual == pytest.approx(12 / 20 - 25 / 50)
    assert adjusted.dpr_expected == pytest.approx(18 / 50)
    assert adjusted.apr_expected == pytest.approx(8 / 50)


def test_opening_frequency_exposure_weighted_baseline() -> None:
    references = [
        _obs(1, rounds=20, first_kills=4, first_deaths=2),
        _obs(2, rounds=30, first_kills=3, first_deaths=3),
    ]
    registry = build_baseline_registry(references)
    evaluation = _obs(3, agent_name="Reyna", rounds=20, first_kills=5, first_deaths=1)
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=999,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.opening_frequency == pytest.approx(6 / 20)
    assert adjusted.opening_frequency_expected == pytest.approx(12 / 50)
    assert adjusted.opening_frequency_residual == pytest.approx(6 / 20 - 12 / 50)


def test_opening_efficiency_pooled_probability_and_shrinkage() -> None:
    references = [
        _obs(1, first_kills=8, first_deaths=2),
        _obs(2, first_kills=6, first_deaths=4),
    ]
    registry = build_baseline_registry(references)
    evaluation = _obs(3, agent_name="Reyna", first_kills=1, first_deaths=1)
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=999,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.opening_efficiency_raw == pytest.approx(0.5)
    assert adjusted.opening_efficiency_adjusted is not None
    assert adjusted.opening_efficiency_adjusted != adjusted.opening_efficiency_raw


def test_opening_efficiency_large_sample_converges_toward_raw() -> None:
    references = [_obs(i, first_kills=8, first_deaths=2) for i in range(1, 21)]
    registry = build_baseline_registry(references)
    evaluation = _obs(99, agent_name="Reyna", first_kills=40, first_deaths=10)
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=999,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.opening_efficiency_raw == pytest.approx(0.8)
    assert adjusted.opening_efficiency_adjusted is not None
    assert abs(adjusted.opening_efficiency_adjusted - adjusted.opening_efficiency_raw) < 0.1


def test_kast_weighted_baseline_from_approximate_rounds() -> None:
    references = [
        _obs(1, rounds=20, kast_pct=60.0),
        _obs(2, rounds=30, kast_pct=80.0),
    ]
    registry = build_baseline_registry(references)
    evaluation = _obs(3, agent_name="Reyna", rounds=20, kast_pct=70.0)
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=999,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    expected_kast_rounds = round(60 / 100 * 20) + round(80 / 100 * 30)
    expected_pct = (expected_kast_rounds / 50) * 100.0

    assert adjusted.kast == 70.0
    assert adjusted.kast_expected == pytest.approx(expected_pct)
    assert adjusted.kast_residual == pytest.approx(70.0 - expected_pct)


def test_approximate_kast_rounds_uses_rounding() -> None:
    observation = _obs(1, rounds=21, kast_pct=76.2)
    assert approximate_kast_rounds(observation) == round(76.2 / 100 * 21)


def test_hierarchical_fallback_selects_role_map_tier() -> None:
    references = [
        _obs(1, agent_name="Jett", map_name="Bind", rounds=120, kills=60),
        _obs(2, agent_name="Reyna", map_name="Bind", rounds=120, kills=48),
    ]
    registry = build_baseline_registry(references)
    evaluation = _obs(3, agent_name="Sage", map_name="Bind", tier="S")
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=200,
        role_map_tier_min_rounds=100,
        role_tier_min_rounds=50,
        tier_min_rounds=20,
    )

    level, exposure = select_baseline_level(registry, evaluation, thresholds)
    assert level == BaselineLevel.ROLE_MAP_TIER
    assert exposure.rounds == 240


def test_minimum_exposure_threshold_falls_back_to_tier() -> None:
    references = [
        _obs(1, role="Duelist", agent_name="Jett", map_name="Bind", tier="S", rounds=30, kills=15),
        _obs(
            2,
            role="Initiator",
            agent_name="Sova",
            map_name="Haven",
            tier="S",
            rounds=30,
            kills=12,
        ),
    ]
    registry = build_baseline_registry(references)
    evaluation = _obs(3, role="Sentinel", agent_name="Sage", map_name="Split", tier="S")
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=200,
        role_map_tier_min_rounds=100,
        role_tier_min_rounds=50,
        tier_min_rounds=20,
    )

    level, _ = select_baseline_level(registry, evaluation, thresholds)
    assert level == BaselineLevel.TIER


def test_unseen_agent_map_uses_fallback_baseline() -> None:
    references = [_obs(1, agent_name="Jett", map_name="Bind", rounds=120, kills=60)]
    registry = build_baseline_registry(references)
    evaluation = _obs(2, agent_name="UnknownAgent", map_name="UnknownMap", tier="S")
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=200,
        role_map_tier_min_rounds=100,
        role_tier_min_rounds=50,
        tier_min_rounds=20,
        global_min_rounds=1,
    )

    level, exposure = select_baseline_level(registry, evaluation, thresholds)
    assert level in {BaselineLevel.TIER, BaselineLevel.GLOBAL, BaselineLevel.ROLE_TIER}
    assert exposure.rounds >= thresholds.global_min_rounds


def test_self_leakage_excluded_from_baseline() -> None:
    evaluation = _obs(1, rounds=20, kills=20, agent_name="Jett")
    with_leak = build_baseline_registry([evaluation])
    without_leak = build_baseline_registry(filter_reference_observations([evaluation], evaluation))
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    leaked = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=with_leak,
        thresholds=thresholds,
    )
    clean = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=without_leak,
        thresholds=thresholds,
    )

    assert leaked.kpr_expected == pytest.approx(1.0)
    assert clean.kpr_expected is None
    assert clean.reference_rounds == 0


def test_future_data_leakage_prevention() -> None:
    early = _obs(
        1,
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        rounds=20,
        kills=10,
    )
    future = _obs(
        2,
        played_at=datetime(2024, 6, 1, tzinfo=UTC),
        rounds=20,
        kills=18,
    )
    evaluation = _obs(3, played_at=datetime(2024, 3, 1, tzinfo=UTC), rounds=20, kills=12)

    all_obs = [early, future, evaluation]
    reference = filter_reference_observations(all_obs, evaluation)
    registry = build_baseline_registry(reference)
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.kpr_expected == pytest.approx(10 / 20)
    assert len(reference) == 1


def test_missing_kast_and_clutch_remain_none() -> None:
    evaluation = _obs(1, kast_pct=None, clutch_wins=None, clutch_attempts=None)
    registry = BaselineRegistry()
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.kast is None
    assert adjusted.kast_expected is None
    assert adjusted.clutch_rate_raw is None
    assert adjusted.clutch_rate_adjusted is None


def test_zero_opening_opportunities() -> None:
    evaluation = _obs(1, first_kills=0, first_deaths=0)
    registry = build_baseline_registry([_obs(2, first_kills=2, first_deaths=2)])
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.opening_efficiency_raw is None
    assert adjusted.opening_efficiency_adjusted is None
    assert adjusted.opening_frequency == 0.0


def test_zero_clutch_attempts() -> None:
    evaluation = _obs(1, clutch_wins=0, clutch_attempts=0)
    registry = build_baseline_registry([_obs(2, clutch_wins=1, clutch_attempts=2)])
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.clutch_rate_raw is None
    assert adjusted.clutch_rate_adjusted is None


def test_residual_adr_passed_through_without_second_adjustment() -> None:
    evaluation = _obs(1)
    registry = build_baseline_registry([_obs(2)])
    thresholds = BaselineThresholds(
        agent_map_tier_min_rounds=1,
        role_map_tier_min_rounds=1,
        role_tier_min_rounds=1,
        tier_min_rounds=1,
    )

    adjusted = adjust_context_observation(
        evaluation,
        residual_adr=12.5,
        registry=registry,
        thresholds=thresholds,
    )

    assert adjusted.residual_adr == 12.5


def test_bayesian_prior_not_hardcoded() -> None:
    low_rate = estimate_beta_prior([(1, 9), (1, 9)])
    high_rate = estimate_beta_prior([(9, 1), (9, 1)])
    assert low_rate.alpha / (low_rate.alpha + low_rate.beta) < 0.3
    assert high_rate.alpha / (high_rate.alpha + high_rate.beta) > 0.7
