from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.metrics.context_baselines import ContextObservation
from app.metrics.context_v2 import (
    ContextV2Level,
    FeatureContextRule,
    adjust_context_v2_observation,
    build_context_v2_registry,
    exposure_weight,
    hierarchical_mean,
    no_context_features,
    partial_residual,
    rate_from_exposure,
)
from app.metrics.context_v2_config import (
    CONTEXT_MODE_V2,
    ContextExperimentSpec,
    default_context_experiment_matrix,
    register_context_experiment,
)
from app.metrics.context_v2_diagnostics import (
    decide_context_recommendation,
    diagnose_controller_shift,
    prefer_simpler_if_similar,
    role_bias_metrics,
    select_context_configuration,
)
from app.schemas.context_v2 import ContextExperimentResult, SplitMetrics


def _obs(
    observation_id: int,
    *,
    role: str = "Duelist",
    agent_name: str = "Jett",
    map_name: str = "Bind",
    tier: str | None = "T1",
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


def _rules(**levels: ContextV2Level) -> dict[str, FeatureContextRule]:
    defaults = {
        "kpr": ContextV2Level.AGENT_MAP_TIER,
        "dpr": ContextV2Level.AGENT_MAP_TIER,
        "apr": ContextV2Level.AGENT_TIER,
        "kast": ContextV2Level.NONE,
        "opening_frequency": ContextV2Level.ROLE,
        "opening_efficiency": ContextV2Level.ROLE,
        "residual_adr": ContextV2Level.NONE,
        "clutch": ContextV2Level.NONE,
    }
    defaults.update(levels)
    return {name: FeatureContextRule(name, level) for name, level in defaults.items()}


def test_partial_lambda_zero_equals_observed() -> None:
    assert partial_residual(1.2, 0.8, 0.5, 0.0) == pytest.approx(1.2)


def test_partial_lambda_one_equals_full_adjustment() -> None:
    observed, context_mean, global_mean = 1.2, 0.8, 0.5
    full = observed - (context_mean - global_mean)
    assert partial_residual(observed, context_mean, global_mean, 1.0) == pytest.approx(full)


def test_lambda_zero_matches_no_context() -> None:
    references = [_obs(1, rounds=40, kills=20), _obs(2, rounds=10, kills=8)]
    registry = build_context_v2_registry(references)
    evaluation = _obs(3, rounds=20, kills=16)
    v2 = adjust_context_v2_observation(
        evaluation,
        residual_adr=12.0,
        registry=registry,
        rules=_rules(kpr=ContextV2Level.AGENT_MAP_TIER),
        lam=0.0,
        tau=0.0,
    )
    raw = no_context_features(evaluation, residual_adr=12.0)
    assert v2.kpr_residual == pytest.approx(raw.kpr_residual or 0.0)
    assert v2.residual_adr == pytest.approx(12.0)


def test_lambda_one_full_adjustment_uses_global_offset() -> None:
    references = [_obs(1, rounds=40, kills=16), _obs(2, rounds=10, kills=8)]
    registry = build_context_v2_registry(references)
    evaluation = _obs(3, rounds=20, kills=16)
    adjusted = adjust_context_v2_observation(
        evaluation,
        residual_adr=None,
        registry=registry,
        rules=_rules(kpr=ContextV2Level.GLOBAL),
        lam=1.0,
        tau=0.0,
    )
    observed = 16 / 20
    global_mean = (16 + 8) / (40 + 10)
    assert adjusted.kpr_residual == pytest.approx(observed - (global_mean - global_mean))
    assert adjusted.kpr_residual == pytest.approx(observed)


def test_feature_specific_rules_do_not_share_levels() -> None:
    references = [
        _obs(1, role="Controller", agent_name="Omen", assists=20, rounds=20),
        _obs(2, role="Duelist", agent_name="Jett", assists=2, rounds=20),
    ]
    registry = build_context_v2_registry(references)
    evaluation = _obs(3, role="Controller", agent_name="Omen", assists=10, rounds=20)
    rules = _rules(kpr=ContextV2Level.ROLE, apr=ContextV2Level.AGENT_TIER)
    adjusted = adjust_context_v2_observation(
        evaluation,
        residual_adr=3.0,
        registry=registry,
        rules=rules,
        lam=1.0,
        tau=0.0,
    )
    assert adjusted.feature_baseline_levels["kpr"] == "role"
    assert adjusted.feature_baseline_levels["apr"] == "agent_tier"
    assert adjusted.residual_adr == pytest.approx(3.0)


def test_exposure_weighted_baselines_not_equal_map_average() -> None:
    references = [
        _obs(1, rounds=10, kills=10),
        _obs(2, rounds=90, kills=9),
    ]
    registry = build_context_v2_registry(references)
    exposure = registry.global_exposure
    equal_weight = ((10 / 10) + (9 / 90)) / 2
    exposure_weighted = rate_from_exposure(exposure, "kpr")
    assert exposure_weighted == pytest.approx(19 / 100)
    assert exposure_weighted != pytest.approx(equal_weight)
    assert exposure_weight(exposure, "kpr") == pytest.approx(100)


def test_hierarchical_shrinkage_unseen_falls_back_to_parent() -> None:
    references = [_obs(1, agent_name="Jett", map_name="Bind", rounds=80, kills=40)]
    registry = build_context_v2_registry(references)
    unseen = _obs(2, agent_name="Jett", map_name="Haven", rounds=20, kills=15)
    mean, level = hierarchical_mean(
        registry,
        unseen,
        ContextV2Level.AGENT_MAP_TIER,
        "kpr",
        tau=50.0,
    )
    parent, _ = hierarchical_mean(
        registry,
        unseen,
        ContextV2Level.AGENT_TIER,
        "kpr",
        tau=50.0,
    )
    assert mean == pytest.approx(parent or 0.0)
    assert level == "agent_map_tier"


def test_hierarchical_tau_zero_uses_specific_when_present() -> None:
    references = [_obs(1, agent_name="Jett", map_name="Bind", rounds=80, kills=16)]
    registry = build_context_v2_registry(references)
    evaluation = _obs(2, agent_name="Jett", map_name="Bind", rounds=20, kills=18)
    mean, _ = hierarchical_mean(
        registry,
        evaluation,
        ContextV2Level.AGENT_MAP_TIER,
        "kpr",
        tau=0.0,
    )
    assert mean == pytest.approx(16 / 80)


def test_residual_adr_is_never_context_subtracted() -> None:
    references = [_obs(1)]
    registry = build_context_v2_registry(references)
    adjusted = adjust_context_v2_observation(
        _obs(2),
        residual_adr=7.5,
        registry=registry,
        rules=_rules(),
        lam=1.0,
        tau=50.0,
    )
    assert adjusted.residual_adr == pytest.approx(7.5)


def test_future_observations_are_not_in_train_registry() -> None:
    past = _obs(1, played_at=datetime(2026, 1, 1, tzinfo=UTC), kills=2, rounds=20)
    future = _obs(2, played_at=datetime(2026, 6, 1, tzinfo=UTC), kills=20, rounds=20)
    registry = build_context_v2_registry([past])
    assert registry.global_exposure.kills == 2
    assert future.kills not in {registry.global_exposure.kills}


def test_experiment_matrix_is_extensible() -> None:
    matrix = default_context_experiment_matrix()
    extra = ContextExperimentSpec(
        name="custom_agent_only",
        mode=CONTEXT_MODE_V2,
        lam=0.5,
        simplicity_rank=9,
    )
    extended = register_context_experiment(matrix, extra)
    assert "custom_agent_only" in extended
    assert "no_context" in extended
    assert "hierarchical_shrunk_context" in extended


def test_selection_ignores_test_metrics() -> None:
    worse_val_better_test = ContextExperimentResult(
        name="shiny_test",
        configuration={"mode": "context_v2", "simplicity_rank": 4},
        validation_metrics=SplitMetrics(rmse=3.0, r2=0.5, spearman=0.5),
        test_metrics=SplitMetrics(rmse=1.0, r2=0.9, spearman=0.9),
    )
    better_val_worse_test = ContextExperimentResult(
        name="honest_val",
        configuration={"mode": "no_context", "simplicity_rank": 0},
        validation_metrics=SplitMetrics(rmse=2.0, r2=0.7, spearman=0.7),
        test_metrics=SplitMetrics(rmse=4.0, r2=0.1, spearman=0.1),
    )
    winner = select_context_configuration([worse_val_better_test, better_val_worse_test])
    assert winner.name == "honest_val"


def test_similar_validation_rmse_prefers_simpler() -> None:
    complex_model = ContextExperimentResult(
        name="hierarchical_shrunk_context",
        configuration={"mode": "context_v2", "simplicity_rank": 5},
        validation_metrics=SplitMetrics(rmse=2.000, r2=0.80),
    )
    simple_model = ContextExperimentResult(
        name="no_context",
        configuration={"mode": "no_context", "simplicity_rank": 0},
        validation_metrics=SplitMetrics(rmse=2.005, r2=0.80),
    )
    winner = prefer_simpler_if_similar([complex_model, simple_model])
    assert winner.name == "no_context"


def test_role_bias_metrics_and_controller_diagnosis() -> None:
    bias = role_bias_metrics(
        {
            "Controller": [(60.0, 200), (70.0, 200)],
            "Duelist": [(40.0, 200), (50.0, 200)],
            "Initiator": [(42.0, 180)],
            "Sentinel": [(41.0, 160)],
        }
    )
    assert bias.max_role_median_gap == pytest.approx(24.0)
    assert bias.controller_vs_duelist_gap == pytest.approx(20.0)

    omen = no_context_features(
        _obs(1, role="Controller", agent_name="Omen", assists=12, rounds=20),
        residual_adr=1.0,
    )
    jett = no_context_features(
        _obs(2, role="Duelist", agent_name="Jett", assists=2, rounds=20),
        residual_adr=1.0,
    )
    diagnosis = diagnose_controller_shift(
        [("Controller", 20, omen), ("Duelist", 20, jett)],
        {"apr_residual": 0.2, "kpr_residual": 0.3, "negative_dpr_residual": 0.4},
    )
    assert diagnosis.evidence
    apr_controller = next(
        item for item in diagnosis.features if item.feature == "apr" and item.role == "Controller"
    )
    assert apr_controller.raw_role_mean == pytest.approx(12 / 20)


def test_decision_mapping() -> None:
    assert (
        decide_context_recommendation(
            ContextExperimentResult(name="context_v1", configuration={"mode": "context_v1"})
        )
        == "KEEP_CONTEXT_V1"
    )
    assert (
        decide_context_recommendation(
            ContextExperimentResult(name="no_context", configuration={"mode": "no_context"})
        )
        == "USE_NO_CONTEXT"
    )
    assert (
        decide_context_recommendation(
            ContextExperimentResult(
                name="context_v2_partial_lambda_0.5",
                configuration={"mode": "context_v2"},
            )
        )
        == "USE_CONTEXT_V2"
    )
