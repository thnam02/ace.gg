from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_feature_pruning_config import default_feature_subset_matrix
from app.metrics.cir_v01 import CIR_METRIC_NAME, CIR_V01_VERSION
from app.models import MetricVersion, Player, PlayerMapStats
from app.services.cir_feature_pruning_service import CirFeaturePruningService
from app.services.cir_training_service import CIRTrainingService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from tests.test_cir_training_service import _add_match_with_map, _seed_training_graph
from tests.test_context_v2_experiment import _add_roles, _persist_v01_pair


def test_pruning_does_not_overwrite_v01_real(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    preserved = _persist_v01_pair(db_session)

    report = CirFeaturePruningService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        subset_matrix={
            name: default_feature_subset_matrix()[name]
            for name in ("combat_only", "combat_plus_apr", "full_candidate")
        },
    ).run()

    versions = {(item.name, item.version) for item in db_session.scalars(select(MetricVersion))}
    assert (CIR_METRIC_NAME, CIR_V01_VERSION) in versions
    assert (CIR_METRIC_NAME, CIR_REAL_EXPERIMENT_VERSION) in versions
    real = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_METRIC_NAME,
            MetricVersion.version == CIR_REAL_EXPERIMENT_VERSION,
        )
    )
    assert real is not None
    assert dict(real.model_coefficients) == preserved["coefficients"]
    assert dict(real.standardization_parameters) == preserved["standardization"]
    assert report.preserved_metric_version == CIR_REAL_EXPERIMENT_VERSION
    assert report.selected_subset in {"combat_only", "combat_plus_apr", "full_candidate"}


def test_subset_training_and_reproducibility(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    matrix = {
        name: default_feature_subset_matrix()[name]
        for name in (
            "combat_only",
            "combat_plus_apr",
            "combat_plus_kast",
            "combat_plus_apr_kast",
            "combat_plus_residual_adr",
            "combat_plus_opening",
            "full_candidate",
        )
    }
    service = CirFeaturePruningService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        subset_matrix=matrix,
    )
    first = service.run()
    second = service.run()
    assert first.selected_subset == second.selected_subset
    by_name = {item.name: item for item in first.subset_results}
    assert set(by_name) == set(matrix)
    for item in first.subset_results:
        assert item.validation_metrics.rmse is not None
        assert item.number_of_features == len(item.features)
        assert item.ridge_alpha is not None
        assert item.coefficient_signs
        assert item.coefficient_magnitudes
        assert item.role_bias_metrics.counts is not None
    combat = by_name["combat_only"]
    assert combat.features == ["kpr_residual", "negative_dpr_residual"]
    assert first.kast_diagnosis.feature == "kast_residual"
    assert first.apr_diagnosis.feature == "apr_residual"
    assert first.opening_diagnosis.feature == "opening"
    assert first.residual_adr_diagnosis.univariate.name
    assert first.dispositions
    assert first.recommendation.clutch == "disabled"
    assert first.recommendation.shrinkage_k == 50.0
    second_by_name = {item.name: item for item in second.subset_results}
    assert by_name["combat_only"].validation_metrics.rmse == (
        second_by_name["combat_only"].validation_metrics.rmse
    )


def test_validation_only_selection_ignores_test_metrics(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    report = CirFeaturePruningService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        subset_matrix={
            "combat_only": default_feature_subset_matrix()["combat_only"],
            "full_candidate": default_feature_subset_matrix()["full_candidate"],
        },
    ).run()
    by_name = {item.name: item for item in report.subset_results}
    selected = by_name[report.selected_subset or ""]
    other_name = "full_candidate" if selected.name == "combat_only" else "combat_only"
    other = by_name[other_name]
    if selected.validation_metrics.rmse is not None and other.validation_metrics.rmse is not None:
        assert selected.validation_metrics.rmse <= other.validation_metrics.rmse * 1.01 + 1e-9


def test_future_split_does_not_leak_into_pruning_train(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    _add_match_with_map(
        db_session,
        graph,
        played_at=datetime(2025, 1, 1, 18, 0, tzinfo=UTC),
        vlr_match_id=61001,
        winner=graph["team_a"],
        map_name="Lotus",
        team_a_score=13,
        team_b_score=5,
    )
    trainer = CIRTrainingService(
        db_session,
        require_complete_maps=False,
        persist=False,
        shrinkage_k=50.0,
        feature_names=("kpr_residual", "negative_dpr_residual"),
    )
    _result, bundle = trainer.fit_cir_v01()
    train_ids = {row.stats.match_map_id for row in bundle.prepared_maps if row.split == "train"}
    later_ids = {row.stats.match_map_id for row in bundle.prepared_maps if row.split != "train"}
    assert train_ids
    assert later_ids
    assert train_ids.isdisjoint(later_ids)
    train_max = max(
        row.stats.match_map.match.played_at
        for row in bundle.prepared_maps
        if row.split == "train" and row.stats.match_map.match.played_at is not None
    )
    for row in bundle.prepared_maps:
        if row.split != "train" and row.stats.match_map.match.played_at is not None:
            assert row.stats.match_map.match.played_at >= train_max
    report = CirFeaturePruningService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        subset_matrix={"combat_only": ("kpr_residual", "negative_dpr_residual")},
    ).run()
    assert report.feature_diagnostics
    assert report.residual_adr_diagnosis.univariate.sample_size >= 0


def test_role_bias_and_stability_fields_present(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    duelist = Player(vlr_player_id=9101, handle="duelist")
    db_session.add(duelist)
    db_session.flush()
    stats = graph["stats"]
    agent = graph["agent"]
    db_session.add(
        PlayerMapStats(
            match_map_id=stats.match_map_id,
            player_id=duelist.id,
            team_id=graph["team_a"].id,
            agent_id=agent.id,
            rounds=21,
            kills=18,
            deaths=10,
            assists=2,
            first_kills=5,
            first_deaths=1,
            adr=170.0,
            kast_pct=75.0,
            clutch_wins=0,
            clutch_attempts=1,
            acs=240.0,
            vlr_rating=1.2,
        )
    )
    db_session.flush()
    report = CirFeaturePruningService(
        db_session,
        require_complete_maps=False,
        shrinkage_k=50.0,
        subset_matrix={
            "combat_only": default_feature_subset_matrix()["combat_only"],
            "combat_plus_apr": default_feature_subset_matrix()["combat_plus_apr"],
            "combat_plus_opening": default_feature_subset_matrix()["combat_plus_opening"],
        },
    ).run()
    for item in report.subset_results:
        bias = item.role_bias_metrics
        assert "Controller" in bias.medians or bias.counts
        assert bias.max_role_median_gap is None or isinstance(bias.max_role_median_gap, float)
    assert report.apr_diagnosis.by_role_outcome_correlation
    assert report.stability
    thresholds = {row.round_threshold for row in report.stability}
    assert {100, 250, 500} <= thresholds
