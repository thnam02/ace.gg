from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MatchMap, Player, PlayerMapStats, PlayerTeamHistory, Team
from app.providers.vlr_provider import VLRProvider
from app.schemas.ingestion import EventIngestionSummary
from app.schemas.ingestion_diagnostics import IngestionDiagnostics
from app.services.ingestion_source import EventIngestionSource
from app.services.ingestion_sources import HtmlEventIngestionSource, VlrApiEventIngestionSource
from app.services.match_ingestion import MatchIngestionService

logger = logging.getLogger(__name__)


class EventIngestionService:
    """Discover and ingest all matches for a VLR event."""

    def __init__(
        self,
        session: Session,
        source: object,
        *,
        match_ingestion: MatchIngestionService | None = None,
        dry_run: bool = False,
    ) -> None:
        self._session = session
        self._dry_run = dry_run
        if hasattr(source, "load_event_page"):
            self._source = cast(EventIngestionSource, source)
        else:
            self._source = HtmlEventIngestionSource(cast(VLRProvider, source))
        self._match_ingestion = match_ingestion or MatchIngestionService(session)

    def ingest(self, event_id: int) -> EventIngestionSummary:
        return self.ingest_event(event_id)

    def ingest_event(
        self,
        event_id: int,
        *,
        skip_matches: bool = False,
        completed_matches_only: bool = False,
    ) -> EventIngestionSummary:
        stats_before = self._player_map_stats_count()
        maps_before = self._match_maps_count()
        errors: list[str] = []
        matches_ingested = 0
        matches_skipped = 0
        matches_failed = 0

        page_data = self._source.load_event_page(event_id)
        discovered_ids = list(page_data.match_ids)
        ingest_ids = discovered_ids
        if skip_matches:
            ingest_ids = []
        elif completed_matches_only:
            completed_fn = getattr(self._source, "completed_match_ids", None)
            if callable(completed_fn):
                completed_ids = set(completed_fn())
                ingest_ids = [match_id for match_id in discovered_ids if match_id in completed_ids]
                matches_skipped += len(discovered_ids) - len(ingest_ids)

        if not self._dry_run:
            self._persist_event_context(page_data)

        for match_id in ingest_ids:
            outcome, message = self._ingest_match(match_id, event_id)
            if outcome == "ingested":
                matches_ingested += 1
            elif outcome == "skipped":
                matches_skipped += 1
            else:
                matches_failed += 1
            if message:
                errors.append(message)

        if not self._dry_run:
            self._persist_event_context(page_data)

        stats_created = 0
        maps_created = 0
        if not self._dry_run:
            stats_created = self._player_map_stats_count() - stats_before
            maps_created = self._match_maps_count() - maps_before

        diagnostics = _extract_diagnostics(self._source)
        if isinstance(self._source, VlrApiEventIngestionSource):
            self._source.finalize_diagnostics()
            diagnostics = self._source.diagnostics
        return EventIngestionSummary(
            event_id=event_id,
            matches_discovered=len(discovered_ids),
            matches_ingested=matches_ingested,
            matches_skipped=matches_skipped,
            matches_failed=matches_failed,
            player_map_stats_created=stats_created,
            maps_created=maps_created,
            missing_rounds=diagnostics.missing_rounds,
            missing_kast=diagnostics.missing_kast,
            missing_clutch=diagnostics.missing_clutch,
            unresolved_players=diagnostics.unresolved_player_count(),
            ambiguous_players=diagnostics.ambiguous_player_count(),
            resolved_by_id=diagnostics.player_identity.resolved_by_id,
            resolved_by_event_roster=diagnostics.player_identity.resolved_by_event_roster,
            resolved_by_team_roster=diagnostics.player_identity.resolved_by_team_roster,
            resolved_by_history=diagnostics.player_identity.resolved_by_history,
            resolved_by_db_identity=diagnostics.player_identity.resolved_by_db_identity,
            resolved_by_search=diagnostics.player_identity.resolved_by_search,
            invalid_agent_values=list(diagnostics.invalid_agent_values),
            unknown_agent_rows=diagnostics.unknown_agent_rows,
            maps_complete=diagnostics.maps_complete,
            maps_incomplete=diagnostics.maps_incomplete,
            maps_empty=diagnostics.maps_empty,
            dry_run=self._dry_run,
            errors=errors + diagnostics.rejected_stat_rows,
        )

    def _persist_event_context(self, page_data: object) -> None:
        from app.schemas.ingestion import NormalizedEventPageData

        if not isinstance(page_data, NormalizedEventPageData):
            return
        self._match_ingestion.upsert_event(page_data.event)
        for team in page_data.participating_teams:
            self._match_ingestion.upsert_team(team)
        self._session.flush()

    def _ingest_match(self, match_id: int, event_id: int) -> tuple[str, str | None]:
        try:
            data = self._source.load_match(match_id, event_id)
        except FileNotFoundError as exc:
            logger.warning("Skipping match_id=%s: %s", match_id, exc)
            return "skipped", f"match_id={match_id}: {exc}"
        except Exception as exc:
            if _is_missing_match_error(exc):
                logger.warning("Skipping match_id=%s: %s", match_id, exc)
                return "skipped", f"match_id={match_id}: {exc}"
            logger.exception("Failed to load match_id=%s for event_id=%s", match_id, event_id)
            return "failed", f"match_id={match_id}: {exc}"

        if self._dry_run:
            return "ingested", None

        try:
            if data.event.vlr_event_id != event_id:
                logger.warning(
                    "Match %s belongs to event %s, expected %s",
                    match_id,
                    data.event.vlr_event_id,
                    event_id,
                )
            self._match_ingestion.ingest(data)
            return "ingested", None
        except Exception as exc:
            logger.exception("Failed to ingest match_id=%s for event_id=%s", match_id, event_id)
            return "failed", f"match_id={match_id}: {exc}"

    def _player_map_stats_count(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0)

    def _match_maps_count(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(MatchMap)) or 0)

    def ingest_with_retry(
        self,
        event_id: int,
        *,
        retries: int = 0,
        on_retry: Callable[[int, str], None] | None = None,
    ) -> EventIngestionSummary:
        attempt = 0
        summary = self.ingest_event(event_id)
        while summary.matches_failed > 0 and attempt < retries:
            attempt += 1
            failed_ids = [
                int(token.split("=", 1)[1].split(":")[0])
                for token in summary.errors
                if token.startswith("match_id=")
            ]
            if not failed_ids:
                break

            errors: list[str] = []
            matches_ingested = summary.matches_ingested
            matches_skipped = summary.matches_skipped
            matches_failed = 0
            stats_before = self._player_map_stats_count()

            for match_id in failed_ids:
                if on_retry is not None:
                    on_retry(match_id, f"retry attempt {attempt}")
                outcome, message = self._ingest_match(match_id, event_id)
                if outcome == "ingested":
                    matches_ingested += 1
                elif outcome == "skipped":
                    matches_skipped += 1
                else:
                    matches_failed += 1
                if message:
                    errors.append(message)

            stats_created = summary.player_map_stats_created + (
                self._player_map_stats_count() - stats_before
            )
            summary = EventIngestionSummary(
                event_id=event_id,
                matches_discovered=summary.matches_discovered,
                matches_ingested=matches_ingested,
                matches_skipped=matches_skipped,
                matches_failed=matches_failed,
                player_map_stats_created=stats_created,
                maps_created=summary.maps_created,
                missing_rounds=summary.missing_rounds,
                missing_kast=summary.missing_kast,
                missing_clutch=summary.missing_clutch,
                unresolved_players=summary.unresolved_players,
                ambiguous_players=summary.ambiguous_players,
                resolved_by_id=summary.resolved_by_id,
                resolved_by_event_roster=summary.resolved_by_event_roster,
                resolved_by_team_roster=summary.resolved_by_team_roster,
                resolved_by_history=summary.resolved_by_history,
                resolved_by_db_identity=summary.resolved_by_db_identity,
                resolved_by_search=summary.resolved_by_search,
                invalid_agent_values=list(summary.invalid_agent_values),
                unknown_agent_rows=summary.unknown_agent_rows,
                maps_complete=summary.maps_complete,
                maps_incomplete=summary.maps_incomplete,
                maps_empty=summary.maps_empty,
                dry_run=summary.dry_run,
                errors=errors,
            )
        return summary


def _extract_diagnostics(source: EventIngestionSource) -> IngestionDiagnostics:
    if isinstance(source, VlrApiEventIngestionSource):
        return source.diagnostics
    return IngestionDiagnostics()


def _is_missing_match_error(exc: Exception) -> bool:
    from app.providers.vlrggapi_errors import VlrggApiHttpError, VlrggApiStatusError

    if isinstance(exc, VlrggApiHttpError) and exc.status_code in {404, 0}:
        return True
    if isinstance(exc, VlrggApiStatusError):
        return True
    if isinstance(exc, ValueError) and "missing match_id" in str(exc).lower():
        return True
    return False


def load_known_player_index(session: Session) -> tuple[dict[str, int], set[str]]:
    from app.normalizers.vlr_api_parsing import normalize_player_name

    name_ids: dict[str, set[int]] = defaultdict(set)
    for player in session.scalars(select(Player)):
        name_ids[normalize_player_name(player.handle)].add(player.vlr_player_id)
    unique = {name: next(iter(ids)) for name, ids in name_ids.items() if len(ids) == 1}
    ambiguous = {name for name, ids in name_ids.items() if len(ids) > 1}
    return unique, ambiguous


def load_known_player_handles(session: Session) -> dict[str, int]:
    handles, _ambiguous = load_known_player_index(session)
    return handles


def load_player_team_history_index(
    session: Session,
) -> tuple[dict[tuple[str, int], set[int]], dict[int, set[int]]]:
    from app.normalizers.vlr_api_parsing import normalize_player_name

    history_index: dict[tuple[str, int], set[int]] = defaultdict(set)
    player_teams: dict[int, set[int]] = defaultdict(set)
    rows = session.execute(
        select(Player.handle, Player.vlr_player_id, Team.vlr_team_id)
        .select_from(PlayerTeamHistory)
        .join(Player, Player.id == PlayerTeamHistory.player_id)
        .join(Team, Team.id == PlayerTeamHistory.team_id)
    ).all()
    for handle, player_id, team_id in rows:
        if not handle or player_id is None or team_id is None:
            continue
        normalized = normalize_player_name(handle)
        history_index[(normalized, int(team_id))].add(int(player_id))
        player_teams[int(player_id)].add(int(team_id))
    return dict(history_index), dict(player_teams)
