from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_v01 import CIR_METRIC_NAME, CIR_V01_VERSION
from app.models import Event, MetricVersion
from app.services.cir_final_validation_service import CirFinalValidationService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from tests.test_cir_training_service import _add_match_with_map, _seed_training_graph
from tests.test_context_v2_experiment import _add_roles, _persist_v01_pair


def _seed_multi_event_graph(db_session: Session) -> dict[str, object]:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    graph["event"].tier = "T1"
    graph["event"].region = "Americas"
    events = [
        Event(
            vlr_event_id=9001,
            name="EMEA Stage",
            region="EMEA",
            tier="T1",
            start_date=date(2024, 9, 1),
            season_year=2024,
        ),
        Event(
            vlr_event_id=9002,
            name="Pacific Challengers",
            region="Pacific",
            tier="T2",
            start_date=date(2024, 10, 1),
            season_year=2024,
        ),
        Event(
            vlr_event_id=9003,
            name="China Stage",
            region="China",
            tier="T2",
            start_date=date(2024, 11, 1),
            season_year=2024,
        ),
    ]
    db_session.add_all(events)
    db_session.flush()
    base = datetime(2024, 9, 5, 18, 0, tzinfo=UTC)
    vlr_match_id = 61000
    for event_index, event in enumerate(events):
        for map_index in range(3):
            vlr_match_id += 1
            stats = _add_match_with_map(
                db_session,
                graph,
                played_at=base + timedelta(days=event_index * 20 + map_index),
                vlr_match_id=vlr_match_id,
                winner=graph["team_a"] if map_index % 2 == 0 else graph["team_b"],
                map_name="Haven",
                team_a_score=13 if map_index % 2 == 0 else 8,
                team_b_score=8 if map_index % 2 == 0 else 13,
            )
            stats.match_map.match.event_id = event.id
    db_session.flush()
    return graph


def test_final_validation_does_not_overwrite_cir_versions(db_session: Session) -> None:
    _seed_multi_event_graph(db_session)
    preserved = _persist_v01_pair(db_session)
    report = CirFinalValidationService(
        db_session,
        require_complete_maps=False,
        bootstrap_iterations=8,
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
    assert report.frozen_features == ["kpr_residual", "negative_dpr_residual"]
    assert report.recommendation.readiness != "READY_FOR_FRONTEND"


def test_final_validation_covers_required_diagnostics(db_session: Session) -> None:
    _seed_multi_event_graph(db_session)
    first = CirFinalValidationService(
        db_session,
        require_complete_maps=False,
        bootstrap_iterations=6,
        bootstrap_seed=42,
    ).run()
    second = CirFinalValidationService(
        db_session,
        require_complete_maps=False,
        bootstrap_iterations=6,
        bootstrap_seed=42,
    ).run()
    assert first.primary.validation_metrics.rmse == second.primary.validation_metrics.rmse
    assert first.bootstrap.kpr.median == second.bootstrap.kpr.median
    assert len(first.temporal_splits) >= 2
    assert first.rolling.folds
    assert first.event_holdouts
    assert {item.role for item in first.role_results} == {
        "Duelist",
        "Initiator",
        "Controller",
        "Sentinel",
    }
    assert first.combat_redundancy.conclusion
    assert first.aggregation_sanity.conclusion
    assert first.target_sensitivity.conclusion
    assert {item.name for item in first.context_sensitivity} >= {"context_v2"}
    assert first.leakage_audit
    assert first.recommendation.readiness in {
        "NOT_READY",
        "READY_FOR_FINAL_METRIC_VERSION",
        "READY_FOR_FRONTEND",
    }
    assert {row.round_threshold for row in first.sample_size} >= {50, 100, 250, 500}
    assert first.coefficient_stability.fold_count >= 1
    names = {item.name for item in first.baselines}
    assert "combat_only_cir_candidate" in names
    assert "team_average_kd" in names
