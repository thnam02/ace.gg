from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_v01 import CIR_METRIC_NAME, CIR_V01_VERSION
from app.metrics.mir.mir_config import MIR_METRIC_NAME, SUPPORT_ASSIST
from app.models import MetricVersion
from app.services.mir_experiment_service import MirExperimentService
from app.services.mir_training_service import MirTrainingService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from tests.test_cir_training_service import _add_match_with_map, _seed_training_graph
from tests.test_context_v2_experiment import _add_roles, _persist_v01_pair


def test_mir_does_not_overwrite_cir_versions(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    preserved = _persist_v01_pair(db_session)

    report = MirExperimentService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        persist=False,
    ).run()

    versions = {(item.name, item.version) for item in db_session.scalars(select(MetricVersion))}
    assert (CIR_METRIC_NAME, CIR_V01_VERSION) in versions
    assert (CIR_METRIC_NAME, CIR_REAL_EXPERIMENT_VERSION) in versions
    assert (MIR_METRIC_NAME, "v0.1-experimental-2026") not in versions
    real = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_METRIC_NAME,
            MetricVersion.version == CIR_REAL_EXPERIMENT_VERSION,
        )
    )
    assert real is not None
    assert dict(real.model_coefficients) == preserved["coefficients"]
    assert report.preserved_metric_version == CIR_REAL_EXPERIMENT_VERSION
    assert report.economy_enabled is False
    assert report.recommendation.economy == "disabled"
    assert report.selected_subset is not None


def test_mir_reproducible_and_reports_required_fields(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    service = MirExperimentService(db_session, require_complete_maps=False, shrinkage_k=50.0)
    first = service.run()
    second = service.run()
    assert first.selected_subset == second.selected_subset
    assert {item.name for item in first.subset_results} == {
        item.name for item in second.subset_results
    }
    assert first.raw_vs_unique
    assert {item.signal for item in first.raw_vs_unique} >= {
        "APR",
        "KAST",
        "Opening Frequency",
        "Opening Efficiency",
    }
    assert {item.component for item in first.component_evidence} == {
        "combat",
        "support",
        "opening",
        "economy",
    }
    assert first.role_analysis
    assert first.recommendation.decision in {
        "COMBAT_ONLY_REMAINS_BEST",
        "MIR_SUPPORT_ADDS_VALUE",
        "MIR_OPENING_ADDS_VALUE",
        "MIR_ECONOMY_ADDS_VALUE",
        "MIR_MULTI_COMPONENT",
    }
    assert first.recommendation.readiness in {
        "NOT_READY",
        "READY_FOR_FINAL_VALIDATION",
        "READY_FOR_FRONTEND",
    }


def test_mir_future_split_does_not_leak(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    _add_match_with_map(
        db_session,
        graph,
        played_at=datetime(2025, 1, 1, 18, 0, tzinfo=UTC),
        vlr_match_id=71001,
        winner=graph["team_a"],
        map_name="Lotus",
        team_a_score=13,
        team_b_score=5,
    )
    bundle = MirTrainingService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        persist=False,
        rebuild_ratings=True,
    ).prepare_bundle()
    train_max = max(
        row.stats.match_map.match.played_at
        for row in bundle.player_maps
        if row.split == "train" and row.stats.match_map.match.played_at is not None
    )
    for row in bundle.player_maps:
        if row.split != "train" and row.stats.match_map.match.played_at is not None:
            assert row.stats.match_map.match.played_at >= train_max
    train_ids = {row.stats.match_map_id for row in bundle.player_maps if row.split == "train"}
    later_ids = {row.stats.match_map_id for row in bundle.player_maps if row.split != "train"}
    assert train_ids
    assert later_ids
    assert train_ids.isdisjoint(later_ids)
    assert any(SUPPORT_ASSIST in row.raw_features for row in bundle.player_maps)
