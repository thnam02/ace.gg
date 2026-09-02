from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics.cir_v01 import CIR_METRIC_NAME, CIR_V01_VERSION
from app.models import Match, MatchMap, MetricVersion, PlayerMapStats, PlayerMetricSnapshot
from app.services.cir_training_service import CIRTrainingService
from tests.factories import seed_match_graph


def _cir_service(db_session: Session) -> CIRTrainingService:
    return CIRTrainingService(db_session, require_complete_maps=False)


def _add_scored_map(
    db_session: Session,
    graph: dict[str, object],
    *,
    match: Match,
    map_number: int,
    map_name: str,
    team_a_score: int,
    team_b_score: int,
    winner: object,
    rounds: int,
    kills: int,
    vlr_match_id_suffix: int,
) -> PlayerMapStats:
    match_map = MatchMap(
        match_id=match.id,
        map_number=map_number,
        map_name=map_name,
        team_a_score=team_a_score,
        team_b_score=team_b_score,
        winner_team_id=winner.id,
        rounds_played=rounds,
    )
    db_session.add(match_map)
    db_session.flush()

    stats = PlayerMapStats(
        match_map_id=match_map.id,
        player_id=graph["player"].id,
        team_id=graph["team_a"].id,
        agent_id=graph["agent"].id,
        rounds=rounds,
        kills=kills,
        deaths=rounds - kills // 2,
        assists=4,
        first_kills=3,
        first_deaths=2,
        adr=150.0 + vlr_match_id_suffix,
        kast_pct=70.0,
        clutch_wins=1,
        clutch_attempts=2,
        acs=220.0,
        vlr_rating=1.0,
    )
    db_session.add(stats)
    db_session.flush()
    return stats


def _add_match_with_map(
    db_session: Session,
    graph: dict[str, object],
    *,
    played_at: datetime,
    vlr_match_id: int,
    winner: object,
    map_name: str,
    team_a_score: int,
    team_b_score: int,
) -> PlayerMapStats:
    match = Match(
        vlr_match_id=vlr_match_id,
        event_id=graph["event"].id,
        team_a_id=graph["team_a"].id,
        team_b_id=graph["team_b"].id,
        winner_team_id=winner.id,
        played_at=played_at,
        status="completed",
    )
    db_session.add(match)
    db_session.flush()
    rounds = team_a_score + team_b_score
    return _add_scored_map(
        db_session,
        graph,
        match=match,
        map_number=1,
        map_name=map_name,
        team_a_score=team_a_score,
        team_b_score=team_b_score,
        winner=winner,
        rounds=rounds,
        kills=rounds // 2,
        vlr_match_id_suffix=vlr_match_id % 100,
    )


def _seed_training_graph(db_session: Session) -> dict[str, object]:
    graph = seed_match_graph(db_session)
    _add_match_with_map(
        db_session,
        graph,
        played_at=datetime(2024, 8, 11, 18, 0, tzinfo=UTC),
        vlr_match_id=51001,
        winner=graph["team_a"],
        map_name="Haven",
        team_a_score=13,
        team_b_score=9,
    )
    _add_match_with_map(
        db_session,
        graph,
        played_at=datetime(2024, 8, 12, 18, 0, tzinfo=UTC),
        vlr_match_id=51002,
        winner=graph["team_b"],
        map_name="Split",
        team_a_score=10,
        team_b_score=13,
    )
    _add_match_with_map(
        db_session,
        graph,
        played_at=datetime(2024, 8, 13, 18, 0, tzinfo=UTC),
        vlr_match_id=51003,
        winner=graph["team_a"],
        map_name="Ascent",
        team_a_score=13,
        team_b_score=7,
    )
    return graph


def test_train_cir_v01_persists_metric_version(db_session: Session) -> None:
    _seed_training_graph(db_session)
    result = _cir_service(db_session).train_cir_v01()

    metric_version = db_session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_METRIC_NAME,
            MetricVersion.version == CIR_V01_VERSION,
        )
    )
    assert metric_version is not None
    assert result.metric_version_id == str(metric_version.id)
    assert len(metric_version.feature_names) == 8
    assert "alpha" in metric_version.regularization_parameters
    assert result.coefficients


def test_train_cir_v01_is_deterministic(db_session: Session) -> None:
    _seed_training_graph(db_session)
    service = _cir_service(db_session)
    first = service.train_cir_v01()
    second = service.train_cir_v01()
    assert first.coefficients == second.coefficients
    assert first.ridge_alpha == second.ridge_alpha


def test_train_cir_v01_creates_player_snapshots(db_session: Session) -> None:
    graph = _seed_training_graph(db_session)
    _cir_service(db_session).train_cir_v01()

    snapshot = db_session.scalar(
        select(PlayerMetricSnapshot).where(PlayerMetricSnapshot.player_id == graph["player"].id)
    )
    assert snapshot is not None
    assert snapshot.cir is not None
    assert snapshot.raw_cir is not None
    assert snapshot.rounds > 0


def test_metric_version_idempotent_rebuild(db_session: Session) -> None:
    _seed_training_graph(db_session)
    service = _cir_service(db_session)
    service.train_cir_v01()
    count_first = db_session.scalar(select(func.count()).select_from(MetricVersion))
    service.train_cir_v01()
    count_second = db_session.scalar(select(func.count()).select_from(MetricVersion))
    assert count_first == 1
    assert count_second == 1


def test_chronological_split_has_train_validation_test(db_session: Session) -> None:
    _seed_training_graph(db_session)
    result = _cir_service(db_session).train_cir_v01()
    assert result.split_counts.train_maps >= 1
    assert result.split_counts.validation_maps + result.split_counts.test_maps >= 1


def test_evaluation_reports_rmse(db_session: Session) -> None:
    _seed_training_graph(db_session)
    result = _cir_service(db_session).train_cir_v01()
    assert result.evaluation.train_rmse is not None


def test_real_experiment_does_not_overwrite_v01(db_session: Session) -> None:
    _seed_training_graph(db_session)
    CIRTrainingService(db_session, require_complete_maps=False).train_cir_v01()
    CIRTrainingService(
        db_session,
        require_complete_maps=False,
        persist_version="v0.1-real-2026",
        events_used=[2765, 2857],
    ).train_cir_v01()

    versions = list(db_session.scalars(select(MetricVersion)).all())
    names = {(item.name, item.version) for item in versions}
    assert (CIR_METRIC_NAME, CIR_V01_VERSION) in names
    assert (CIR_METRIC_NAME, "v0.1-real-2026") in names
    real = next(item for item in versions if item.version == "v0.1-real-2026")
    assert real.regularization_parameters["events_used"] == [2765, 2857]
    assert "feature_enabled" in real.regularization_parameters
    assert "residual_adr" in real.regularization_parameters
    assert "bayesian_priors" in real.regularization_parameters
