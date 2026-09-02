from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_combat_factor_config import (
    CANDIDATE_KINDS,
    EQUAL_WEIGHT,
    NEGATIVE_DPR_ONLY,
    NET_COMBAT_RATE,
    PCA_COMBAT_FACTOR,
    TWO_FEATURE,
)
from app.metrics.cir_v01 import CIR_METRIC_NAME, CIR_V01_VERSION
from app.models import MetricVersion
from app.services.cir_combat_factor_experiment_service import CirCombatFactorExperimentService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from tests.test_cir_final_validation_experiment import _seed_multi_event_graph
from tests.test_context_v2_experiment import _persist_v01_pair


def test_combat_factor_does_not_overwrite_cir_versions(db_session: Session) -> None:
    _seed_multi_event_graph(db_session)
    preserved = _persist_v01_pair(db_session)
    report = CirCombatFactorExperimentService(
        db_session,
        require_complete_maps=False,
        bootstrap_iterations=6,
        bootstrap_seed=42,
    ).run()
    versions = {(item.name, item.version) for item in db_session.scalars(select(MetricVersion))}
    assert (CIR_METRIC_NAME, CIR_V01_VERSION) in versions
    assert (CIR_METRIC_NAME, CIR_REAL_EXPERIMENT_VERSION) in versions
    assert (CIR_METRIC_NAME, "v0.2-real-2026") not in versions
    real = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_METRIC_NAME,
            MetricVersion.version == CIR_REAL_EXPERIMENT_VERSION,
        )
    )
    assert real is not None
    assert dict(real.model_coefficients) == preserved["coefficients"]
    assert report.preserved_metric_version == CIR_REAL_EXPERIMENT_VERSION
    assert report.persisted_version is None
    assert report.recommendation.readiness != "READY_FOR_FRONTEND"
    assert report.recommendation.persist is False


def test_combat_factor_covers_required_diagnostics(db_session: Session) -> None:
    _seed_multi_event_graph(db_session)
    first = CirCombatFactorExperimentService(
        db_session,
        require_complete_maps=False,
        bootstrap_iterations=6,
        bootstrap_seed=42,
    ).run()
    second = CirCombatFactorExperimentService(
        db_session,
        require_complete_maps=False,
        bootstrap_iterations=6,
        bootstrap_seed=42,
    ).run()
    kinds = {item.kind for item in first.candidates}
    assert kinds == set(CANDIDATE_KINDS)
    two = next(item for item in first.candidates if item.kind == TWO_FEATURE)
    ncr = next(item for item in first.candidates if item.kind == NET_COMBAT_RATE)
    pca = next(item for item in first.candidates if item.kind == PCA_COMBAT_FACTOR)
    ndpr = next(item for item in first.candidates if item.kind == NEGATIVE_DPR_ONLY)
    equal = next(item for item in first.candidates if item.kind == EQUAL_WEIGHT)
    assert two.n_combat_dimensions == 2
    assert ncr.n_combat_dimensions == 1
    assert pca.n_combat_dimensions == 1
    assert ndpr.n_combat_dimensions == 1
    assert equal.n_combat_dimensions == 1
    assert first.pca.kpr_loading_pc1 is not None
    assert (first.pca.kpr_loading_pc1 or 0) >= 0
    assert (first.pca.ndpr_loading_pc1 or 0) >= 0
    assert first.pc2_diagnostic.note
    assert {item.kind for item in first.temporal} <= set(CANDIDATE_KINDS)
    assert first.rolling
    assert first.event_holdouts
    assert first.tier_results
    assert first.bootstrap
    assert first.ranking
    assert first.leakage_audit
    assert first.baselines
    names = {item.name for item in first.baselines}
    assert "team_average_kd" in names
    assert TWO_FEATURE in names
    assert first.recommendation.selection in {
        "KEEP_TWO_FEATURE_COMBAT",
        "USE_NEGATIVE_DPR_ONLY",
        "USE_NET_COMBAT_RATE",
        "USE_PCA_COMBAT_FACTOR",
        "USE_EQUAL_WEIGHT_COMBAT",
        "RETHINK_COMBAT_MODEL",
    }
    assert first.recommendation.readiness in {
        "NOT_READY",
        "READY_FOR_FINAL_METRIC_VERSION",
        "READY_FOR_FRONTEND",
    }
    assert (
        first.candidates[0].validation_metrics.rmse == second.candidates[0].validation_metrics.rmse
    )
    first_boot = next(item for item in first.bootstrap if item.kind == NET_COMBAT_RATE)
    second_boot = next(item for item in second.bootstrap if item.kind == NET_COMBAT_RATE)
    assert first_boot.coefficient.median == second_boot.coefficient.median
    assert any(item.name == "pca_loadings" for item in first.leakage_audit)
    assert any("train" in (item.fit_scope or "") for item in first.leakage_audit)
