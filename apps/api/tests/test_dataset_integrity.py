from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Match, PlayerMapStats
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.services.cir_readiness_service import NOT_READY, CirReadinessService
from app.services.dataset_audit_service import DatasetAuditService
from app.services.dataset_integrity_service import DatasetIntegrityService
from app.services.event_ingestion import EventIngestionService
from app.services.sample_validation_service import SampleValidationService
from tests.factories import seed_match_graph
from tests.vlrggapi_fixtures import event_91000, match_900001_bo3


def _codes(report: object) -> set[str]:
    return {warning.code for warning in report.warnings}


def test_integrity_warns_unexpected_player_count(db_session: Session) -> None:
    seed_match_graph(db_session)
    report = DatasetIntegrityService().check(db_session)
    assert "unexpected_player_stat_count" in _codes(report)
    text = DatasetIntegrityService().format_report(report)
    assert "integrity_warning_count:" in text


def test_integrity_warns_impossible_values_without_rewriting(db_session: Session) -> None:
    seeded = seed_match_graph(db_session)
    stats = seeded["stats"]
    assert isinstance(stats, PlayerMapStats)
    stats.kills = -1
    stats.kast_pct = 140.0
    stats.adr = -8.0
    stats.clutch_wins = 5
    stats.clutch_attempts = 1
    stats.first_kills = 99
    stats.first_deaths = 99
    db_session.flush()

    report = DatasetIntegrityService().check(db_session)
    codes = _codes(report)
    assert "negative_combat_stat" in codes
    assert "kast_out_of_range" in codes
    assert "negative_adr" in codes
    assert "clutch_wins_gt_attempts" in codes
    assert "first_kills_gt_rounds" in codes
    assert "first_deaths_gt_rounds" in codes

    db_session.refresh(stats)
    assert stats.kills == -1
    assert stats.kast_pct == 140.0
    assert stats.clutch_wins == 5


def test_integrity_warns_match_winner_mismatch(db_session: Session) -> None:
    seeded = seed_match_graph(db_session)
    match = seeded["match"]
    team_b = seeded["team_b"]
    assert isinstance(match, Match)
    match.winner_team_id = team_b.id
    db_session.flush()

    report = DatasetIntegrityService().check(db_session)
    assert "match_winner_mismatch" in _codes(report)


def test_integrity_warns_rounds_mismatch(db_session: Session) -> None:
    seeded = seed_match_graph(db_session)
    stats = seeded["stats"]
    assert isinstance(stats, PlayerMapStats)
    stats.rounds = 3
    db_session.flush()

    report = DatasetIntegrityService().check(db_session)
    assert "player_rounds_mismatch" in _codes(report)


def test_dataset_audit_includes_coverage_and_eligibility(db_session: Session) -> None:
    seed_match_graph(db_session)
    report = DatasetAuditService().audit(db_session)
    assert report.player_map_stats == 1
    assert report.total_rounds == 21
    assert "Duelist" in report.observations_by_role
    assert "T1" not in report.observations_by_tier or report.observations_by_tier
    assert "global" in report.context_baseline_coverage
    assert 100 in report.eligible_players_by_rounds
    assert report.eligible_players_by_rounds[100] == 0
    text = DatasetAuditService().format_report(report)
    assert "agent_map_tier:" in text
    assert "eligible_players_by_rounds:" in text


def test_cir_readiness_not_ready_for_tiny_dataset(db_session: Session) -> None:
    seed_match_graph(db_session)
    audit = DatasetAuditService().audit(db_session)
    readiness = CirReadinessService().assess(audit)
    assert readiness.status == NOT_READY
    assert any("PlayerMapStats" in reason for reason in readiness.reasons)


def test_sample_validation_matches_ingested_json(db_session: Session, tmp_path: Path) -> None:
    from app.providers.vlr_api_ingestion_provider import StaticVlrApiIngestionProvider
    from app.services.ingestion_sources import VlrApiEventIngestionSource

    cache = VlrggApiRawCache(tmp_path)
    cache.save("matches", 900001, match_900001_bo3())
    provider = StaticVlrApiIngestionProvider(
        {900001: match_900001_bo3()},
        events={91000: event_91000()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    EventIngestionService(db_session, VlrApiEventIngestionSource(provider)).ingest_event(91000)

    report = SampleValidationService().validate(db_session, cache, match_ids=[900001])
    assert report.matches_compared == 1
    assert report.player_rows_compared == 20
    assert report.discrepancies == []
