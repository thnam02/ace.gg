from __future__ import annotations

import copy
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics.cir.config import CIR_V02_VERSION, MetricVersionStatus
from app.models import Event, Match, MatchMap, MetricVersion, PlayerMapStats, PlayerMetricSnapshot
from app.providers.vct_circuit_provider import StaticVctCircuitProvider
from app.providers.vlr_api_ingestion_provider import StaticVlrApiIngestionProvider
from app.schemas.vct_circuit import EventStatus, VctSyncJobStatus
from app.services.cir_v02_training_service import CirV02TrainingService
from app.services.vct_circuit_discovery import VctCircuitDiscoveryService
from app.services.vct_sync_service import VctDailySyncService, format_vct_sync_report
from tests.test_cir_training_service import _seed_training_graph
from tests.vlrggapi_fixtures import event_91000, match_900001_bo3, match_900002_bo1

SYNC_HTML = (Path(__file__).parent / "fixtures" / "vct_sync.html").read_text(encoding="utf-8")


def _event_payload(name: str) -> dict:
    payload = event_91000()
    payload["segments"]["event"]["name"] = name
    payload["segments"]["event"]["series"] = "Valorant Champions Tour 2026"
    payload["segments"]["event"]["dates"] = "Apr 10 - May 25, 2026"
    return payload


def _match(match_id: int, source: dict) -> dict:
    payload = copy.deepcopy(source)
    payload["match_id"] = str(match_id)
    return payload


def _provider() -> StaticVlrApiIngestionProvider:
    return StaticVlrApiIngestionProvider(
        {
            900001: _match(900001, match_900001_bo3()),
            900002: _match(900002, match_900002_bo1()),
            910001: _match(910001, match_900001_bo3()),
            910002: _match(910002, match_900002_bo1()),
        },
        events={
            2860: _event_payload("VCT 2026: Americas Stage 1"),
            2977: _event_payload("VCT 2026: Americas Stage 2"),
            2766: _event_payload("Valorant Champions 2026"),
        },
        event_matches={
            2860: {
                "matches": [
                    {"match_id": "900001", "status": "Completed"},
                    {"match_id": "900002", "status": "Completed"},
                ]
            },
            2977: {
                "matches": [
                    {"match_id": "910001", "status": "Completed"},
                    {"match_id": "910002", "status": "Upcoming"},
                ]
            },
            2766: {"matches": []},
        },
    )


def _service(db_session: Session, html: str | None = None) -> VctDailySyncService:
    discovery = VctCircuitDiscoveryService(
        StaticVctCircuitProvider(html or SYNC_HTML),
        season_year=2026,
    )
    return VctDailySyncService(
        db_session,
        season_year=2026,
        discovery=discovery,
        provider=_provider(),
    )


def test_sync_classifies_missing_upcoming_ongoing_and_completed(db_session: Session) -> None:
    report = _service(db_session).sync(skip_snapshot_refresh=True)
    by_id = {item.vlr_event_id: item for item in report.events}
    assert by_id[2860].reconcile_state == "missing"
    assert by_id[2860].action == "ingest"
    assert by_id[2977].reconcile_state == "ongoing"
    assert by_id[2766].reconcile_state == "upcoming"
    assert by_id[2766].action == "metadata"
    assert "VCT 2026 sync" in format_vct_sync_report(report)
    assert report.job_status in {VctSyncJobStatus.SUCCESS, VctSyncJobStatus.PARTIAL_SUCCESS}


def test_completed_backfill_and_upcoming_metadata_only(db_session: Session) -> None:
    _service(db_session).sync(skip_snapshot_refresh=True)
    completed = db_session.scalar(select(Event).where(Event.vlr_event_id == 2860))
    upcoming = db_session.scalar(select(Event).where(Event.vlr_event_id == 2766))
    assert completed is not None
    assert completed.tier == "T1"
    assert completed.circuit == "VCT"
    assert completed.region == "Americas"
    assert completed.status == EventStatus.COMPLETED.value
    assert completed.stage == "Stage 1"
    assert upcoming is not None
    assert upcoming.status == EventStatus.UPCOMING.value
    assert upcoming.region == "INTL"
    upcoming_matches = db_session.scalar(
        select(func.count(Match.id)).where(Match.event_id == upcoming.id)
    )
    upcoming_stats = db_session.scalar(
        select(func.count(PlayerMapStats.id))
        .join(MatchMap, MatchMap.id == PlayerMapStats.match_map_id)
        .join(Match, Match.id == MatchMap.match_id)
        .where(Match.event_id == upcoming.id)
    )
    assert upcoming_matches == 0
    assert upcoming_stats == 0
    completed_matches = db_session.scalar(
        select(func.count(Match.id)).where(Match.event_id == completed.id)
    )
    assert completed_matches == 2


def test_ongoing_ingests_completed_matches_only(db_session: Session) -> None:
    _service(db_session).sync(skip_snapshot_refresh=True)
    event = db_session.scalar(select(Event).where(Event.vlr_event_id == 2977))
    assert event is not None
    assert event.status == EventStatus.ONGOING.value
    match_ids = set(
        db_session.scalars(select(Match.vlr_match_id).where(Match.event_id == event.id)).all()
    )
    assert match_ids == {910001}


def test_idempotent_repeated_sync_does_not_duplicate_rows(db_session: Session) -> None:
    service = _service(db_session)
    service.sync(skip_snapshot_refresh=True)
    first_matches = db_session.scalar(select(func.count(Match.id))) or 0
    first_maps = db_session.scalar(select(func.count(MatchMap.id))) or 0
    first_stats = db_session.scalar(select(func.count(PlayerMapStats.id))) or 0
    service.sync(skip_snapshot_refresh=True)
    assert db_session.scalar(select(func.count(Match.id))) == first_matches
    assert db_session.scalar(select(func.count(MatchMap.id))) == first_maps
    assert db_session.scalar(select(func.count(PlayerMapStats.id))) == first_stats
    events = db_session.scalars(
        select(Event).where(Event.vlr_event_id.in_([2860, 2977, 2766]))
    ).all()
    assert len(events) == 3


def test_upcoming_to_ongoing_then_completed_transition(db_session: Session) -> None:
    html_upcoming = """
    <html><head><title>Valorant Champions Tour 2026</title></head><body>
    <div class="wf-title">Valorant Champions Tour 2026</div>
    <a class="wf-card mod-flex event-item" href="/event/2977/vct-2026-americas-stage-2">
      <div class="event-item-title">VCT 2026: Americas Stage 2</div>
      <span class="event-item-desc-item-status mod-upcoming">upcoming</span>
    </a></body></html>
    """
    _service(db_session, html_upcoming).sync(skip_snapshot_refresh=True)
    event = db_session.scalar(select(Event).where(Event.vlr_event_id == 2977))
    assert event is not None
    assert event.status == EventStatus.UPCOMING.value
    assert (
        db_session.scalar(select(func.count(Match.id)).where(Match.event_id == event.id)) or 0
    ) == 0

    html_ongoing = html_upcoming.replace("upcoming", "ongoing")
    _service(db_session, html_ongoing).sync(skip_snapshot_refresh=True)
    db_session.refresh(event)
    assert event.status == EventStatus.ONGOING.value
    assert (
        db_session.scalar(select(func.count(Match.id)).where(Match.event_id == event.id)) or 0
    ) == 1

    html_completed = html_ongoing.replace("ongoing", "completed")
    _service(db_session, html_completed).sync(skip_snapshot_refresh=True)
    db_session.refresh(event)
    assert event.status == EventStatus.COMPLETED.value


def test_partial_failure_continues(db_session: Session) -> None:
    provider = _provider()
    original = provider.get_event

    def flaky_get_event(event_id: int):
        if event_id == 2860:
            raise RuntimeError("boom")
        return original(event_id)

    provider.get_event = flaky_get_event  # type: ignore[method-assign]
    discovery = VctCircuitDiscoveryService(StaticVctCircuitProvider(SYNC_HTML), season_year=2026)
    report = VctDailySyncService(
        db_session, season_year=2026, discovery=discovery, provider=provider
    ).sync(skip_snapshot_refresh=True)
    by_id = {item.vlr_event_id: item for item in report.events}
    assert by_id[2860].action == "failed"
    assert db_session.scalar(select(Event).where(Event.vlr_event_id == 2766)) is not None
    assert report.job_status == VctSyncJobStatus.PARTIAL_SUCCESS


def test_sync_does_not_retrain_or_mutate_frozen_v02(db_session: Session) -> None:
    _seed_training_graph(db_session)
    trained = CirV02TrainingService(db_session, require_complete_maps=False).train()
    version = db_session.get(MetricVersion, trained.metric_version_id)
    assert version is not None
    before = {
        "std": version.standardization_parameters,
        "reg": version.regularization_parameters,
        "shr": version.shrinkage_parameters,
        "ref": version.reference_population,
        "status": version.status,
    }
    report = _service(db_session).sync(skip_snapshot_refresh=False)
    db_session.refresh(version)
    assert version.version == CIR_V02_VERSION
    assert version.status == MetricVersionStatus.PRODUCTION.value
    assert version.standardization_parameters == before["std"]
    assert version.regularization_parameters == before["reg"]
    assert version.shrinkage_parameters == before["shr"]
    assert version.reference_population == before["ref"]
    assert report.retrained_cir is False
    assert report.v02_parameters_frozen is True
    assert db_session.scalar(
        select(func.count(PlayerMetricSnapshot.id)).where(
            PlayerMetricSnapshot.metric_version_id == version.id
        )
    )


def test_dry_run_does_not_write_events(db_session: Session) -> None:
    report = _service(db_session).sync(dry_run=True, skip_snapshot_refresh=True)
    assert report.dry_run is True
    assert db_session.scalar(select(func.count(Event.id))) == 0
    assert report.events_discovered >= 3
