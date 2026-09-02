from __future__ import annotations

from math import sqrt
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir.combat import equal_weight_combat_factor, pca_equivalent_pc1
from app.metrics.cir.config import (
    CIR_NAME,
    CIR_V02_FEATURE_NAMES,
    CIR_V02_VERSION,
    SHRINKAGE_K,
    TAU,
    MetricVersionStatus,
    SampleStatus,
    production_context_spec,
)
from app.metrics.cir.context import (
    context_expectation_table,
    expected_rates,
    load_combat_registry,
    serialize_combat_registry,
)
from app.metrics.cir.reliability import (
    reliability_for_rounds,
    sample_status_for_rounds,
    sample_weight,
)
from app.metrics.cir.scoring import kpr_residual, negative_dpr_residual
from app.metrics.cir_scoring import empirical_cdf, round_weighted_mean
from app.metrics.cir_standardization import fit_standardization
from app.metrics.context_baselines import ContextObservation
from app.metrics.context_v2 import build_context_v2_registry
from app.metrics.context_v2_config import CONTEXT_MODE_V1, CONTEXT_MODE_V2
from app.models import MetricVersion, PlayerMetricSnapshot
from app.services.cir_snapshot_service import CirSnapshotService
from app.services.cir_v02_training_service import CirV02TrainingService, CirVersionExistsError
from tests.test_cir_training_service import _seed_training_graph


def _observation(
    *,
    role: str,
    tier: str,
    rounds: int,
    kills: int,
    deaths: int,
) -> ContextObservation:
    return ContextObservation(
        observation_id=uuid4(),
        role=role,
        agent_name="Jett",
        map_name="Bind",
        tier=tier,
        played_at=None,
        rounds=rounds,
        kills=kills,
        deaths=deaths,
        assists=0,
        first_kills=0,
        first_deaths=0,
        kast_pct=None,
        clutch_wins=None,
        clutch_attempts=None,
    )


def test_round_weighted_expectations_not_equal_map_average() -> None:
    observations = [
        _observation(role="Duelist", tier="T1", rounds=10, kills=10, deaths=5),
        _observation(role="Duelist", tier="T1", rounds=90, kills=9, deaths=90),
    ]
    registry = build_context_v2_registry(observations)
    expected_kpr, expected_dpr = expected_rates(
        registry, observations[0], tau=0.0
    )
    assert expected_kpr == pytest.approx(19 / 100)
    assert expected_dpr == pytest.approx(95 / 100)
    equal_weight = ((10 / 10) + (9 / 90)) / 2
    assert expected_kpr != pytest.approx(equal_weight)


def test_hierarchical_shrinkage_mixes_parent() -> None:
    observations = [
        _observation(role="Duelist", tier="T1", rounds=50, kills=50, deaths=25),
        _observation(role="Sentinel", tier="T1", rounds=450, kills=225, deaths=225),
    ]
    registry = build_context_v2_registry(observations)
    expected_kpr, _ = expected_rates(registry, observations[0], tau=TAU)
    raw = 50 / 50
    parent = 275 / 500
    weight = 50 / (50 + TAU)
    assert expected_kpr == pytest.approx(weight * raw + (1 - weight) * parent)


def test_kpr_and_negative_dpr_residuals() -> None:
    assert kpr_residual(0.84, 0.77) == pytest.approx(0.07)
    assert negative_dpr_residual(0.60, 0.65) == pytest.approx(0.05)


def test_equal_weight_is_pca_equivalent_for_ranking() -> None:
    combat = equal_weight_combat_factor(1.2, -0.4)
    pc1 = pca_equivalent_pc1(1.2, -0.4)
    assert combat == pytest.approx(0.5 * 1.2 + 0.5 * -0.4)
    assert pc1 == pytest.approx(combat * sqrt(2))


def test_train_only_standardization_does_not_use_eval_maps() -> None:
    train = [{"kpr_residual": 0.1, "negative_dpr_residual": -0.2}]
    params = fit_standardization(train, feature_names=CIR_V02_FEATURE_NAMES)
    assert params.means["kpr_residual"] == pytest.approx(0.1)
    assert params.stds["kpr_residual"] == pytest.approx(1.0)


def test_sample_labels_and_reliability() -> None:
    assert sample_status_for_rounds(99) == SampleStatus.LOW_SAMPLE
    assert sample_status_for_rounds(100) == SampleStatus.PROVISIONAL
    assert sample_status_for_rounds(249) == SampleStatus.PROVISIONAL
    assert sample_status_for_rounds(250) == SampleStatus.ESTABLISHED
    assert reliability_for_rounds(250).value == "HIGH"
    assert sample_weight(50, SHRINKAGE_K) == pytest.approx(0.5)


def test_empirical_cdf_is_bounded_percentile() -> None:
    reference = [-1.0, 0.0, 1.0]
    assert empirical_cdf(-2.0, reference) == pytest.approx(0.0)
    assert empirical_cdf(1.0, reference) == pytest.approx(100.0)
    assert 0.0 <= empirical_cdf(0.0, reference) <= 100.0


def test_round_weighted_player_aggregation_not_equal_maps() -> None:
    assert round_weighted_mean([(1.0, 10), (0.0, 90)]) == pytest.approx(0.1)


def test_production_context_is_v2_not_v1() -> None:
    spec = production_context_spec()
    assert spec.mode == CONTEXT_MODE_V2
    assert spec.mode != CONTEXT_MODE_V1
    assert spec.lam == 1.0
    assert spec.tau == 500.0


def test_context_registry_round_trip() -> None:
    observations = [_observation(role="Duelist", tier="T1", rounds=20, kills=16, deaths=10)]
    registry = build_context_v2_registry(observations)
    restored = load_combat_registry(serialize_combat_registry(registry))
    rows = context_expectation_table(restored, tau=TAU)
    assert rows[0]["role"] == "Duelist"
    assert rows[0]["exposure"] == 20
    assert rows[0]["tau"] == TAU


def test_train_cir_v02_persists_isolated_version(db_session: Session) -> None:
    _seed_training_graph(db_session)
    result = CirV02TrainingService(
        db_session, require_complete_maps=False, bootstrap_iterations=0
    ).train()

    metric_version = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_NAME,
            MetricVersion.version == CIR_V02_VERSION,
        )
    )
    assert metric_version is not None
    assert result.metric_version_id == str(metric_version.id)
    assert metric_version.feature_names == list(CIR_V02_FEATURE_NAMES)
    assert "residual_adr" not in metric_version.feature_names
    assert metric_version.model_coefficients["combat_factor_type"] == "equal_weight_standardized"
    assert metric_version.model_coefficients["pca_equivalent"] is True
    assert metric_version.regularization_parameters["context_type"] == "context_v2"
    snapshots = list(
        db_session.scalars(
            select(PlayerMetricSnapshot).where(
                PlayerMetricSnapshot.metric_version_id == metric_version.id
            )
        ).all()
    )
    assert snapshots
    assert all(0.0 <= (row.cir or 0.0) <= 100.0 for row in snapshots)
    assert all(row.rounds > 0 for row in snapshots)
    assert all(row.sample_status is not None for row in snapshots)


def test_train_cir_v02_does_not_overwrite_v01(db_session: Session) -> None:
    _seed_training_graph(db_session)
    v01 = MetricVersion(
        name=CIR_NAME,
        version="v0.1-real-2026",
        status=MetricVersionStatus.RESEARCH.value,
        feature_names=["kpr_residual"],
        standardization_parameters={"means": {}, "stds": {}},
        model_coefficients={},
        regularization_parameters={},
        shrinkage_parameters={"k": 500},
        reference_population={"shrunk_raw_cir_values": [0.0]},
    )
    db_session.add(v01)
    db_session.flush()
    CirV02TrainingService(db_session, require_complete_maps=False).train()
    kept = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_NAME,
            MetricVersion.version == "v0.1-real-2026",
        )
    )
    assert kept is not None
    assert kept.id == v01.id


def test_train_cir_v02_refuses_silent_overwrite(db_session: Session) -> None:
    _seed_training_graph(db_session)
    trainer = CirV02TrainingService(db_session, require_complete_maps=False)
    trainer.train()
    with pytest.raises(CirVersionExistsError):
        trainer.train()


def test_snapshot_refresh_is_idempotent_and_does_not_refit(db_session: Session) -> None:
    _seed_training_graph(db_session)
    trainer = CirV02TrainingService(db_session, require_complete_maps=False)
    first = trainer.train()
    version = db_session.get(MetricVersion, first.metric_version_id)
    assert version is not None
    frozen_mean = version.shrinkage_parameters["reference_mean"]
    snapshots_before = db_session.scalar(
        select(PlayerMetricSnapshot).where(
            PlayerMetricSnapshot.metric_version_id == version.id
        )
    )
    assert snapshots_before is not None
    cir_before = snapshots_before.cir
    CirSnapshotService(db_session, require_complete_maps=False).refresh()
    version_after = db_session.get(MetricVersion, version.id)
    assert version_after is not None
    assert version_after.shrinkage_parameters["reference_mean"] == frozen_mean
    snapshots_after = list(
        db_session.scalars(
            select(PlayerMetricSnapshot).where(
                PlayerMetricSnapshot.metric_version_id == version.id
            )
        ).all()
    )
    assert len(snapshots_after) == 1
    assert snapshots_after[0].cir == pytest.approx(cir_before or 0.0)


def test_no_future_leakage_in_train_expectations() -> None:
    train = [_observation(role="Duelist", tier="T1", rounds=100, kills=80, deaths=50)]
    later = [_observation(role="Duelist", tier="T1", rounds=100, kills=10, deaths=90)]
    registry = build_context_v2_registry(train)
    expected_kpr, _ = expected_rates(registry, later[0], tau=0.0)
    assert expected_kpr == pytest.approx(0.8)
    leaked = build_context_v2_registry(train + later)
    leaked_kpr, _ = expected_rates(leaked, later[0], tau=0.0)
    assert leaked_kpr != pytest.approx(expected_kpr)
