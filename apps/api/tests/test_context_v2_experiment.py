from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_v01 import CIR_METRIC_NAME, CIR_V01_VERSION
from app.metrics.context_v2_config import (
    CONTEXT_MODE_V2,
    ContextExperimentSpec,
    default_context_experiment_matrix,
    feature_specific_rules,
)
from app.models import Agent, MetricVersion, Player, PlayerMapStats
from app.services.cir_training_service import CIRTrainingService
from app.services.context_v2_experiment_service import ContextV2ExperimentService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from tests.test_cir_training_service import _cir_service, _seed_training_graph


def _persist_v01_pair(db_session: Session) -> dict[str, object]:
    _cir_service(db_session).train_cir_v01()
    CIRTrainingService(
        db_session,
        require_complete_maps=False,
        persist_version=CIR_REAL_EXPERIMENT_VERSION,
        events_used=[1188],
    ).train_cir_v01()
    real = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_METRIC_NAME,
            MetricVersion.version == CIR_REAL_EXPERIMENT_VERSION,
        )
    )
    assert real is not None
    return {
        "coefficients": dict(real.model_coefficients),
        "standardization": dict(real.standardization_parameters),
        "feature_names": list(real.feature_names),
    }


def _add_roles(db_session: Session, graph: dict[str, object]) -> None:
    omen = Agent(name="Omen", role="Controller")
    sova = Agent(name="Sova", role="Initiator")
    cypher = Agent(name="Cypher", role="Sentinel")
    controller = Player(vlr_player_id=9001, handle="controller")
    initiator = Player(vlr_player_id=9002, handle="initiator")
    sentinel = Player(vlr_player_id=9003, handle="sentinel")
    db_session.add_all([omen, sova, cypher, controller, initiator, sentinel])
    db_session.flush()
    stats = graph["stats"]
    for player, agent, assists in (
        (controller, omen, 12),
        (initiator, sova, 6),
        (sentinel, cypher, 3),
    ):
        db_session.add(
            PlayerMapStats(
                match_map_id=stats.match_map_id,
                player_id=player.id,
                team_id=graph["team_a"].id,
                agent_id=agent.id,
                rounds=21,
                kills=10,
                deaths=12,
                assists=assists,
                first_kills=1,
                first_deaths=2,
                adr=140.0,
                kast_pct=68.0,
                clutch_wins=0,
                clutch_attempts=1,
                acs=180.0,
                vlr_rating=0.9,
            )
        )
    db_session.flush()


def test_experiment_does_not_overwrite_v01_real(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    preserved = _persist_v01_pair(db_session)

    report = ContextV2ExperimentService(
        db_session,
        require_complete_maps=False,
        matrix={
            "no_context": default_context_experiment_matrix()["no_context"],
            "context_v1": default_context_experiment_matrix()["context_v1"],
            "context_v2_partial_lambda_0.5": default_context_experiment_matrix()[
                "context_v2_partial_lambda_0.5"
            ],
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
    assert report.best_validation_configuration is not None
    assert report.recommendations.decision in {
        "KEEP_CONTEXT_V1",
        "USE_NO_CONTEXT",
        "USE_CONTEXT_V2",
    }


def test_unpersisted_fit_does_not_write_metric_version(db_session: Session) -> None:
    _seed_training_graph(db_session)
    before = db_session.scalar(select(MetricVersion).where(MetricVersion.version == "v0.1"))
    CIRTrainingService(
        db_session,
        require_complete_maps=False,
        persist=False,
        persist_version="should-not-write",
        rebuild_ratings=True,
    ).train_cir_v01()
    after = list(db_session.scalars(select(MetricVersion)).all())
    if before is None:
        assert after == []
    else:
        assert all(item.version != "should-not-write" for item in after)


def test_experiment_reproducible_and_reports_required_fields(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _add_roles(db_session, graph)
    matrix = {
        name: default_context_experiment_matrix()[name]
        for name in ("no_context", "context_v1", "context_v2_feature_specific_full")
    }
    service = ContextV2ExperimentService(
        db_session,
        require_complete_maps=False,
        matrix=matrix,
    )
    first = service.run()
    second = service.run()
    assert first.best_validation_configuration == second.best_validation_configuration
    by_name = {item.name: item for item in first.experiments}
    assert set(by_name) == set(matrix)
    for item in first.experiments:
        assert item.validation_metrics.rmse is not None
        assert item.coefficients
        assert item.role_bias_metrics.counts
    assert first.controller_diagnosis.evidence
    assert first.recommendations.selected_shrinkage_k in {50.0, 100.0, 250.0, 500.0}


def test_lambda_tuning_uses_validation_rmse(db_session: Session) -> None:
    _seed_training_graph(db_session)
    spec = ContextExperimentSpec(
        name="tuned_lambda",
        mode=CONTEXT_MODE_V2,
        lam=1.0,
        tau=0.0,
        tune_lambda=True,
        rules=feature_specific_rules(),
        simplicity_rank=2,
    )
    report = ContextV2ExperimentService(
        db_session,
        require_complete_maps=False,
        matrix={"tuned_lambda": spec},
    ).run()
    result = report.experiments[0]
    assert result.selected_lambda in {0.0, 0.25, 0.5, 0.75, 1.0}


def test_tau_tuning_uses_validation_rmse(db_session: Session) -> None:
    _seed_training_graph(db_session)
    spec = ContextExperimentSpec(
        name="tuned_tau",
        mode=CONTEXT_MODE_V2,
        lam=1.0,
        tau=200.0,
        hierarchical=True,
        tune_tau=True,
        rules=feature_specific_rules(),
        simplicity_rank=5,
    )
    report = ContextV2ExperimentService(
        db_session,
        require_complete_maps=False,
        matrix={"tuned_tau": spec},
    ).run()
    assert report.experiments[0].selected_tau in {50.0, 100.0, 200.0, 500.0}


def test_future_split_does_not_leak_into_train_baselines(db_session: Session) -> None:
    _seed_training_graph(db_session)
    trainer = CIRTrainingService(
        db_session,
        require_complete_maps=False,
        persist=False,
        context_mode=CONTEXT_MODE_V2,
        context_spec=default_context_experiment_matrix()["context_v2_feature_specific_full"],
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
