from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, Match, PlayerMapStats, Team
from app.providers.vlr_provider import FileVLRProvider
from app.services.event_ingestion import EventIngestionService
from tests.vlr_fixtures import EVENTS_DIR, MATCHES_DIR


def _service(db_session: Session) -> EventIngestionService:
    provider = FileVLRProvider(MATCHES_DIR, events_dir=EVENTS_DIR)
    return EventIngestionService(db_session, provider)


def test_event_ingestion_summary_counts(db_session: Session) -> None:
    summary = _service(db_session).ingest(91000)

    assert summary.event_id == 91000
    assert summary.matches_discovered == 4
    assert summary.matches_ingested == 2
    assert summary.matches_skipped == 1
    assert summary.matches_failed == 1
    assert summary.player_map_stats_created == 30
    assert len(summary.errors) == 2

    event = db_session.scalar(select(Event).where(Event.vlr_event_id == 91000))
    assert event is not None
    assert event.name == "Champions 2024"
    assert event.region == "NA"
    assert event.status == "completed"
    assert event.start_date == date(2024, 8, 1)
    assert event.end_date == date(2024, 8, 25)

    teams = db_session.scalars(select(Team).where(Team.vlr_team_id.in_([91001, 91002]))).all()
    assert len(teams) == 2

    matches = db_session.scalars(
        select(Match).where(Match.vlr_match_id.in_([900001, 900002]))
    ).all()
    assert len(matches) == 2
    assert db_session.scalar(select(func.count()).select_from(PlayerMapStats)) == 30


def test_event_ingestion_rerun_is_idempotent(db_session: Session) -> None:
    service = _service(db_session)
    first = service.ingest(91000)
    second = service.ingest(91000)

    assert first.player_map_stats_created == 30
    assert second.player_map_stats_created == 0
    assert second.matches_ingested == 2
    assert db_session.scalar(select(func.count()).select_from(Event)) == 2
    assert db_session.scalar(select(Event).where(Event.vlr_event_id == 91000)) is not None
    assert db_session.scalar(select(func.count()).select_from(Match)) == 2
    assert db_session.scalar(select(func.count()).select_from(PlayerMapStats)) == 30


def test_one_bad_match_does_not_stop_remaining_matches(db_session: Session) -> None:
    summary = _service(db_session).ingest(91000)

    ingested_ids = {match.vlr_match_id for match in db_session.scalars(select(Match)).all()}
    assert 900001 in ingested_ids
    assert 900002 in ingested_ids
    assert 999999 not in ingested_ids
    assert summary.matches_failed == 1
    assert any("999998" in error for error in summary.errors)
