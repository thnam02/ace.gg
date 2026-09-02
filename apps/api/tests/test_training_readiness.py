from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.dataset_audit_service import DatasetAuditReport
from app.services.dataset_training_readiness import (
    NOT_READY,
    READY_TO_TRAIN,
    READY_WITH_WARNINGS,
    DatasetTrainingReadinessService,
)
from app.services.scale_event_set import SCALE_EVENT_IDS, SCALE_EVENT_SET
from app.services.team_rating_service import TeamRatingService
from tests.factories import seed_match_graph


def _ready_audit(**overrides: object) -> DatasetAuditReport:
    report = DatasetAuditReport(
        players=400,
        teams=80,
        events=8,
        matches=400,
        maps=900,
        player_map_stats=9000,
        total_rounds=180_000,
        observations_by_role={
            "Duelist": 2000,
            "Initiator": 2000,
            "Controller": 2000,
            "Sentinel": 2000,
        },
        observations_by_tier={"T1": 5000, "T2": 4000},
        maps_complete=850,
        maps_incomplete=20,
        maps_empty=0,
        complete_map_pct=97.7,
        unresolved_identity_slots_pct=0.2,
        maps_eligible_for_cir=850,
        player_map_stats_eligible_for_cir=8500,
        missing_rounds=0,
        missing_adr=10,
        missing_kast=10,
        missing_clutch=9000,
        unknown_agent_rows=0,
        invalid_agent_values=[],
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


def test_training_gates_hard_stop() -> None:
    report = _ready_audit(complete_map_pct=50.0, maps_eligible_for_cir=40)
    result = DatasetTrainingReadinessService().assess(report)
    assert result.status == NOT_READY
    assert result.can_train is False
    assert result.blockers


def test_training_gates_preferred_warnings() -> None:
    report = _ready_audit(complete_map_pct=85.0, maps_eligible_for_cir=200)
    result = DatasetTrainingReadinessService().assess(report)
    assert result.status == READY_WITH_WARNINGS
    assert result.can_train is True
    assert result.warnings


def test_training_gates_ready() -> None:
    result = DatasetTrainingReadinessService().assess(_ready_audit())
    assert result.status == READY_TO_TRAIN
    assert result.can_train is True
    assert not result.blockers
    assert not result.warnings


def test_scale_event_set_is_diverse_and_completed() -> None:
    assert len(SCALE_EVENT_IDS) == 8
    assert len(set(SCALE_EVENT_IDS)) == 8
    tiers = {item.tier for item in SCALE_EVENT_SET}
    regions = {item.region for item in SCALE_EVENT_SET}
    assert "T1" in tiers and "T2" in tiers
    assert {"NA", "EMEA", "Pacific", "China", "INTL", "Americas"} <= regions


def test_elo_rebuild_reports_distribution(db_session: Session) -> None:
    seed_match_graph(db_session)
    summary = TeamRatingService(db_session).rebuild_team_ratings()
    assert summary.teams_rated == 2
    assert summary.rating_min is not None
    assert summary.rating_max is not None
    assert summary.highest_rated_teams
