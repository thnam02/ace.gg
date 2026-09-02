from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.metrics.cir.config import CIR_NAME, CIR_V02_VERSION, CIR_V03_VERSION
from app.models import DataSyncRun, Event, Match, MatchMap, PlayerMapStats
from app.models.metric_version import MetricVersion
from app.normalizers.event_status import canonical_event_status
from app.providers.vlr_api_ingestion_provider import (
    CachingVlrApiIngestionProvider,
    StaticVlrApiIngestionProvider,
    VlrApiIngestionProvider,
)
from app.providers.vlrggapi_factory import create_vlr_api_ingestion_provider, create_vlrggapi_client
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.schemas.ingestion import EventIngestionSummary, NormalizedEvent
from app.schemas.vct_circuit import (
    CircuitName,
    EventStatus,
    VctDiscoveredEvent,
    VctEventSyncResult,
    VctReconcileState,
    VctSyncJobStatus,
    VctSyncReport,
)
from app.services.cir_snapshot_service import CirSnapshotService, load_frozen_cir_v02
from app.services.json_event_ingestion import ingest_json_event
from app.services.match_ingestion import MatchIngestionService
from app.services.team_rating_service import TeamRatingService
from app.services.vct_circuit_discovery import VctCircuitDiscoveryService

VlrApiProvider = (
    VlrApiIngestionProvider | CachingVlrApiIngestionProvider | StaticVlrApiIngestionProvider
)


class VctDailySyncService:
    """Discover official VCT events and incrementally ingest through the existing stack."""

    def __init__(
        self,
        session: Session,
        *,
        season_year: int | None = None,
        discovery: VctCircuitDiscoveryService | None = None,
        provider: VlrApiProvider | None = None,
        raw_cache_dir: Path | None = None,
    ) -> None:
        self._session = session
        self._season_year = season_year or settings.vct_sync_season_year
        self._discovery = discovery or VctCircuitDiscoveryService(season_year=self._season_year)
        self._provider = provider
        self._raw_cache_dir = raw_cache_dir
        self._events = MatchIngestionService(session)

    def sync(
        self,
        *,
        dry_run: bool = False,
        force: bool = False,
        event_id: int | None = None,
        status: EventStatus | None = None,
        skip_snapshot_refresh: bool = False,
        continue_on_error: bool = True,
    ) -> VctSyncReport:
        started = datetime.now(tz=UTC)
        clock = monotonic()
        report = VctSyncReport(
            season_year=self._season_year,
            dry_run=dry_run,
            started_at=started,
        )
        v02_before = _frozen_parameter_fingerprint(self._session, CIR_V02_VERSION)

        try:
            discovered = self._discovery.discover()
        except Exception as exc:
            report.job_status = VctSyncJobStatus.FAILED
            report.errors.append(f"circuit discovery failed: {exc}")
            return self._finalize(report, started, clock, dry_run=dry_run)

        if event_id is not None:
            discovered = [item for item in discovered if item.vlr_event_id == event_id]
        if status is not None:
            discovered = [item for item in discovered if item.status == status]

        report.events_discovered = len(discovered)
        report.completed_events = sum(
            1 for item in discovered if item.status == EventStatus.COMPLETED
        )
        report.ongoing_events = sum(1 for item in discovered if item.status == EventStatus.ONGOING)
        report.upcoming_events = sum(
            1 for item in discovered if item.status == EventStatus.UPCOMING
        )

        existing_ids = {
            row.vlr_event_id
            for row in self._session.scalars(select(Event)).all()
            if row.vlr_event_id is not None
        }
        ingested_any_matches = False
        provider = self._provider
        owned_client = None
        if provider is None and not dry_run:
            owned_client = create_vlrggapi_client(
                settings.vlrggapi_base_url,
                timeout=60.0,
                request_delay=2.5,
                max_retries=12,
            )
            provider = create_vlr_api_ingestion_provider(
                settings.vlrggapi_base_url, client=owned_client
            )
            if self._raw_cache_dir is not None:
                provider = CachingVlrApiIngestionProvider(
                    provider, VlrggApiRawCache(self._raw_cache_dir)
                )

        try:
            for item in discovered:
                existed = item.vlr_event_id in existing_ids
                try:
                    result = self._sync_event(
                        item,
                        existed_before=existed,
                        dry_run=dry_run,
                        force=force,
                        provider=provider,
                    )
                except Exception as exc:
                    if not continue_on_error:
                        raise
                    result = VctEventSyncResult(
                        vlr_event_id=item.vlr_event_id,
                        name=item.name,
                        status=item.status.value,
                        region=item.region,
                        stage=item.stage,
                        reconcile_state=VctReconcileState.MISSING.value,
                        action="failed",
                        existed_before=existed,
                        errors=[str(exc)],
                    )
                report.events.append(result)
                report.errors.extend(result.errors)
                if not existed and result.action != "failed":
                    report.events_added += 1
                    existing_ids.add(item.vlr_event_id)
                elif existed and result.action not in {"skip", "failed"}:
                    report.events_updated += 1
                report.matches_added += result.matches_ingested
                report.maps_added += result.maps_added
                report.player_map_stats_added += result.player_map_stats_added
                report.identity_resolution_failures += result.unresolved_players
                report.incomplete_maps += result.maps_incomplete
                if result.matches_ingested > 0:
                    ingested_any_matches = True
        finally:
            if owned_client is not None:
                owned_client.close()

        if ingested_any_matches and not dry_run:
            TeamRatingService(self._session).rebuild_team_ratings()
            report.elo_rebuilt = True

        if not skip_snapshot_refresh and not dry_run:
            self._refresh_frozen_snapshots(report)

        v02_after = _frozen_parameter_fingerprint(self._session, CIR_V02_VERSION)
        report.v02_parameters_frozen = v02_before == v02_after
        if v02_before and v02_after and v02_before != v02_after:
            report.errors.append("CIR v0.2 frozen parameters changed during sync")

        failures = [item for item in report.events if item.action == "failed" or item.errors]
        if not discovered:
            report.job_status = VctSyncJobStatus.FAILED
            report.errors.append("no VCT events discovered")
        elif failures and len(failures) == len(report.events):
            report.job_status = VctSyncJobStatus.FAILED
        elif failures:
            report.job_status = VctSyncJobStatus.PARTIAL_SUCCESS
        else:
            report.job_status = VctSyncJobStatus.SUCCESS
        return self._finalize(report, started, clock, dry_run=dry_run)

    def _sync_event(
        self,
        item: VctDiscoveredEvent,
        *,
        existed_before: bool,
        dry_run: bool,
        force: bool,
        provider: VlrApiProvider | None,
    ) -> VctEventSyncResult:
        previous = self._session.scalar(
            select(Event).where(Event.vlr_event_id == item.vlr_event_id)
        )
        previous_status = canonical_event_status(previous.status) if previous else None
        state = self._reconcile_state(item, previous, previous_status)
        action = self._action_for(item, state, previous_status=previous_status, force=force)

        result = VctEventSyncResult(
            vlr_event_id=item.vlr_event_id,
            name=item.name,
            status=item.status.value,
            region=item.region,
            stage=item.stage,
            reconcile_state=state.value,
            action=action,
            existed_before=existed_before,
        )
        if dry_run:
            return result

        if action == "skip":
            self._stamp_circuit_metadata(item)
            return result

        skip_matches = action == "metadata"
        completed_only = item.status == EventStatus.ONGOING
        summary = ingest_json_event(
            self._session,
            item.vlr_event_id,
            dry_run=False,
            provider=provider,
            skip_matches=skip_matches,
            completed_matches_only=completed_only,
        )
        self._stamp_circuit_metadata(item)
        self._fill_from_summary(result, summary)
        if summary.errors and summary.matches_failed > 0 and summary.matches_ingested == 0:
            result.action = "failed"
        return result

    def _reconcile_state(
        self,
        item: VctDiscoveredEvent,
        event: Event | None,
        previous_status: EventStatus | None,
    ) -> VctReconcileState:
        if item.status == EventStatus.UPCOMING:
            return VctReconcileState.UPCOMING
        if item.status == EventStatus.ONGOING:
            return VctReconcileState.ONGOING
        if event is None:
            return VctReconcileState.MISSING
        if previous_status == EventStatus.ONGOING:
            return VctReconcileState.INCOMPLETE
        if _event_is_complete(self._session, event):
            return VctReconcileState.COMPLETE
        return VctReconcileState.INCOMPLETE

    def _action_for(
        self,
        item: VctDiscoveredEvent,
        state: VctReconcileState,
        *,
        previous_status: EventStatus | None,
        force: bool,
    ) -> str:
        if item.status == EventStatus.UPCOMING:
            return "metadata"
        if item.status == EventStatus.ONGOING:
            return "ingest"
        if force or state in {VctReconcileState.MISSING, VctReconcileState.INCOMPLETE}:
            return "ingest"
        if previous_status == EventStatus.ONGOING:
            return "ingest"
        return "skip"

    def _stamp_circuit_metadata(self, item: VctDiscoveredEvent) -> Event:
        return self._events.upsert_event(
            NormalizedEvent(
                vlr_event_id=item.vlr_event_id,
                name=item.name,
                region=item.region,
                tier="T1",
                circuit=CircuitName.VCT.value,
                stage=item.stage,
                start_date=item.start_date,
                end_date=item.end_date,
                season_year=item.season_year,
                status=item.status.value,
            )
        )

    def _refresh_frozen_snapshots(self, report: VctSyncReport) -> None:
        service = CirSnapshotService(self._session)
        versions = [CIR_V02_VERSION]
        if _metric_version_exists(self._session, CIR_V03_VERSION):
            versions.append(CIR_V03_VERSION)
        players_seen: set[UUID] = set()
        for version in versions:
            frozen = load_frozen_cir_v02(self._session, version=version)
            if frozen is None:
                continue
            before = copy.deepcopy(_frozen_parameter_fingerprint(self._session, version))
            try:
                frozen_after, players, _failures = service.refresh(version=version)
            except ValueError as exc:
                report.errors.append(str(exc))
                continue
            after = _frozen_parameter_fingerprint(self._session, version)
            if before and after and before != after:
                report.errors.append(f"{version} parameters changed during snapshot refresh")
            report.cir_versions_refreshed.append(frozen_after.metric_version.version)
            report.cir_snapshots_refreshed += len(players)
            players_seen.update(player.player_id for player in players)
        report.players_affected = len(players_seen)
        report.retrained_cir = False

    def _finalize(
        self,
        report: VctSyncReport,
        started: datetime,
        clock: float,
        *,
        dry_run: bool,
    ) -> VctSyncReport:
        report.finished_at = datetime.now(tz=UTC)
        report.duration_seconds = round(monotonic() - clock, 3)
        if not dry_run:
            self._session.add(
                DataSyncRun(
                    circuit=CircuitName.VCT.value,
                    season_year=self._season_year,
                    started_at=started,
                    finished_at=report.finished_at,
                    status=report.job_status.value,
                    report=report.model_dump(mode="json"),
                )
            )
            self._session.flush()
        return report

    def _fill_from_summary(
        self,
        result: VctEventSyncResult,
        summary: EventIngestionSummary,
    ) -> None:
        result.matches_discovered = summary.matches_discovered
        result.matches_ingested = summary.matches_ingested
        result.matches_skipped = summary.matches_skipped
        result.matches_failed = summary.matches_failed
        result.maps_added = summary.maps_created
        result.player_map_stats_added = summary.player_map_stats_created
        result.maps_complete = summary.maps_complete
        result.maps_incomplete = summary.maps_incomplete
        result.unresolved_players = summary.unresolved_players
        result.errors.extend(summary.errors)


def latest_sync_run(session: Session) -> DataSyncRun | None:
    return session.scalar(select(DataSyncRun).order_by(DataSyncRun.started_at.desc()).limit(1))


def latest_match_played_at(session: Session) -> datetime | None:
    return session.scalar(
        select(func.max(Match.played_at))
        .join(Event, Event.id == Match.event_id)
        .where(
            Event.circuit == CircuitName.VCT.value,
            Event.tier == "T1",
        )
    )


def format_vct_sync_report(report: VctSyncReport) -> str:
    lines = [
        "VCT 2026 sync",
        "",
        f"Events discovered: {report.events_discovered}",
        f"Completed: {report.completed_events}",
        f"Ongoing: {report.ongoing_events}",
        f"Upcoming: {report.upcoming_events}",
        "",
        f"New events: {report.events_added}",
        f"Events updated: {report.events_updated}",
        f"Matches added: {report.matches_added}",
        f"Maps added: {report.maps_added}",
        f"Stats rows added: {report.player_map_stats_added}",
        f"Players rescored: {report.players_affected}",
        f"CIR snapshots refreshed: {report.cir_snapshots_refreshed}",
        f"Identity failures: {report.identity_resolution_failures}",
        f"Incomplete maps: {report.incomplete_maps}",
        f"Duration: {report.duration_seconds}s",
        f"CIR v0.2 frozen: {report.v02_parameters_frozen}",
        f"Retrained CIR: {report.retrained_cir}",
        "",
        f"Status: {report.job_status.value}",
    ]
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"  {error}" for error in report.errors[:40])
    return "\n".join(lines)


def _event_is_complete(session: Session, event: Event) -> bool:
    matches = session.scalar(select(func.count(Match.id)).where(Match.event_id == event.id)) or 0
    stats = (
        session.scalar(
            select(func.count(PlayerMapStats.id))
            .join(MatchMap, MatchMap.id == PlayerMapStats.match_map_id)
            .join(Match, Match.id == MatchMap.match_id)
            .where(Match.event_id == event.id)
        )
        or 0
    )
    return matches > 0 and stats > 0


def _metric_version_exists(session: Session, version: str) -> bool:
    return (
        session.scalar(
            select(MetricVersion.id).where(
                MetricVersion.name == CIR_NAME,
                MetricVersion.version == version,
            )
        )
        is not None
    )


def _frozen_parameter_fingerprint(session: Session, version: str) -> dict[str, Any] | None:
    row = session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_NAME,
            MetricVersion.version == version,
        )
    )
    if row is None:
        return None
    return {
        "standardization_parameters": copy.deepcopy(row.standardization_parameters),
        "model_coefficients": copy.deepcopy(row.model_coefficients),
        "regularization_parameters": copy.deepcopy(row.regularization_parameters),
        "shrinkage_parameters": copy.deepcopy(row.shrinkage_parameters),
        "reference_population": copy.deepcopy(row.reference_population),
    }
