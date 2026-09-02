from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PlayerMapStats
from app.parsers.event_parser import EventParser
from app.parsers.match_parser import MatchParser
from app.providers.vlr_provider import VLRProvider
from app.schemas.ingestion import EventIngestionSummary, NormalizedEventPageData
from app.services.match_ingestion import MatchIngestionService

logger = logging.getLogger(__name__)


class EventIngestionService:
    """Discover and ingest all matches for a VLR event."""

    def __init__(
        self,
        session: Session,
        provider: VLRProvider,
        *,
        event_parser: EventParser | None = None,
        match_parser: MatchParser | None = None,
        match_ingestion: MatchIngestionService | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._event_parser = event_parser or EventParser()
        self._match_parser = match_parser or MatchParser()
        self._match_ingestion = match_ingestion or MatchIngestionService(session)

    def ingest(self, event_id: int) -> EventIngestionSummary:
        stats_before = self._player_map_stats_count()
        errors: list[str] = []
        matches_ingested = 0
        matches_skipped = 0
        matches_failed = 0

        event_html = self._provider.get_event(event_id)
        matches_html = self._provider.get_event_matches(event_id)
        page_data = self._event_parser.parse(event_html, event_id=event_id)
        discovered_ids = self._discover_unique_match_ids(
            event_id,
            page_data,
            matches_html,
        )

        self._persist_event_context(page_data)

        for match_id in discovered_ids:
            outcome, message = self._ingest_match(match_id, event_id)
            if outcome == "ingested":
                matches_ingested += 1
            elif outcome == "skipped":
                matches_skipped += 1
            else:
                matches_failed += 1
            if message:
                errors.append(message)

        self._persist_event_context(page_data)

        stats_created = self._player_map_stats_count() - stats_before
        return EventIngestionSummary(
            event_id=event_id,
            matches_discovered=len(discovered_ids),
            matches_ingested=matches_ingested,
            matches_skipped=matches_skipped,
            matches_failed=matches_failed,
            player_map_stats_created=stats_created,
            errors=errors,
        )

    def _discover_unique_match_ids(
        self,
        event_id: int,
        page_data: NormalizedEventPageData,
        matches_html: str,
    ) -> list[int]:
        discovered = list(page_data.match_ids)
        for match_id in self._event_parser.discover_match_ids(matches_html, event_id=event_id):
            if match_id not in discovered:
                discovered.append(match_id)
        return discovered

    def _persist_event_context(self, page_data: NormalizedEventPageData) -> None:
        self._match_ingestion.upsert_event(page_data.event)
        for team in page_data.participating_teams:
            self._match_ingestion.upsert_team(team)
        self._session.flush()

    def _ingest_match(self, match_id: int, event_id: int) -> tuple[str, str | None]:
        try:
            html = self._provider.get_match(match_id)
        except FileNotFoundError as exc:
            logger.warning("Skipping match_id=%s: %s", match_id, exc)
            return "skipped", f"match_id={match_id}: {exc}"

        try:
            data = self._match_parser.parse(html, match_id=match_id)
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

    def ingest_with_retry(
        self,
        event_id: int,
        *,
        retries: int = 0,
        on_retry: Callable[[int, str], None] | None = None,
    ) -> EventIngestionSummary:
        attempt = 0
        summary = self.ingest(event_id)
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
                errors=errors,
            )
        return summary
