from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.providers.vlr_api_ingestion_provider import (
    CachingVlrApiIngestionProvider,
    StaticVlrApiIngestionProvider,
    VlrApiIngestionProvider,
)
from app.providers.vlrggapi_client import VlrggApiClient
from app.providers.vlrggapi_factory import create_vlr_api_ingestion_provider, create_vlrggapi_client
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.schemas.ingestion import BulkIngestionSummary, EventIngestionSummary
from app.services.event_ingestion import (
    EventIngestionService,
    load_known_player_index,
    load_player_team_history_index,
)
from app.services.historical_player_identity import HistoricalPlayerIdentityResolver
from app.services.ingestion_sources import VlrApiEventIngestionSource

logger = logging.getLogger(__name__)

VlrApiProvider = (
    VlrApiIngestionProvider | CachingVlrApiIngestionProvider | StaticVlrApiIngestionProvider
)


def ingest_json_event(
    session: Session,
    event_id: int,
    *,
    dry_run: bool = False,
    raw_cache_dir: Path | None = None,
    base_url: str | None = None,
    provider: VlrApiProvider | None = None,
    identity_lookup: HistoricalPlayerIdentityResolver | None = None,
    client: VlrggApiClient | None = None,
) -> EventIngestionSummary:
    api_url = base_url or settings.vlrggapi_base_url
    owns_provider = provider is None
    owned_client = client
    if provider is None:
        owned_client = create_vlrggapi_client(
            api_url, timeout=60.0, request_delay=2.5, max_retries=12
        )
        base_provider = create_vlr_api_ingestion_provider(api_url, client=owned_client)
        provider = base_provider
        if raw_cache_dir is not None:
            cache = VlrggApiRawCache(raw_cache_dir)
            provider = CachingVlrApiIngestionProvider(base_provider, cache)

    lookup = identity_lookup or HistoricalPlayerIdentityResolver(provider)
    known_handles, known_ambiguous = load_known_player_index(session)
    history_index, player_teams = load_player_team_history_index(session)
    source = VlrApiEventIngestionSource(
        provider,
        known_handles=known_handles,
        known_ambiguous=known_ambiguous,
        history_index=history_index,
        player_teams=player_teams,
        identity_lookup=lookup,
    )
    hits_before, misses_before = _cache_counts(provider)
    http_429_before = _http_429_count(owned_client)
    service = EventIngestionService(session, source, dry_run=dry_run)
    try:
        summary = service.ingest_event(event_id)
    finally:
        if owns_provider and owned_client is not None:
            owned_client.close()
    hits_after, misses_after = _cache_counts(provider)
    summary.cache_hits = max(0, hits_after - hits_before)
    summary.cache_misses = max(0, misses_after - misses_before)
    summary.http_429_count = max(0, _http_429_count(owned_client) - http_429_before)
    return summary


def ingest_json_events(
    session: Session,
    event_ids: list[int],
    *,
    dry_run: bool = False,
    continue_on_error: bool = True,
    raw_cache_dir: Path | None = None,
    base_url: str | None = None,
    provider: VlrApiProvider | None = None,
    client: VlrggApiClient | None = None,
) -> BulkIngestionSummary:
    owns_client = False
    if provider is None:
        api_url = base_url or settings.vlrggapi_base_url
        client = create_vlrggapi_client(api_url, timeout=60.0, request_delay=2.5, max_retries=12)
        owns_client = True
        base_provider = create_vlr_api_ingestion_provider(api_url, client=client)
        provider = base_provider
        if raw_cache_dir is not None:
            cache = VlrggApiRawCache(raw_cache_dir)
            provider = CachingVlrApiIngestionProvider(base_provider, cache)
    lookup = HistoricalPlayerIdentityResolver(provider)
    event_summaries: list[EventIngestionSummary] = []
    try:
        for event_id in event_ids:
            try:
                event_summaries.append(
                    ingest_json_event(
                        session,
                        event_id,
                        dry_run=dry_run,
                        provider=provider,
                        identity_lookup=lookup,
                        client=client,
                    )
                )
                latest = event_summaries[-1]
                logger.info(
                    "event_id=%s ingested=%s failed=%s maps=%s cache_hits=%s "
                    "cache_misses=%s http_429=%s",
                    latest.event_id,
                    latest.matches_ingested,
                    latest.matches_failed,
                    latest.maps_created,
                    latest.cache_hits,
                    latest.cache_misses,
                    latest.http_429_count,
                )
            except Exception:
                if not continue_on_error:
                    raise
                event_summaries.append(
                    EventIngestionSummary(
                        event_id=event_id,
                        matches_failed=1,
                        errors=[f"event_id={event_id}: ingestion failed"],
                        dry_run=dry_run,
                    )
                )
    finally:
        if owns_client and client is not None:
            client.close()
    return summarize_bulk_ingestion(event_ids, event_summaries, dry_run=dry_run)


def summarize_bulk_ingestion(
    event_ids: list[int],
    event_summaries: list[EventIngestionSummary],
    *,
    dry_run: bool = False,
) -> BulkIngestionSummary:
    failed = sum(
        1 for item in event_summaries if item.matches_failed > 0 and item.matches_ingested == 0
    )
    completed = sum(
        1 for item in event_summaries if item.matches_failed == 0 or item.matches_ingested > 0
    )
    return BulkIngestionSummary(
        events_requested=len(event_ids),
        events_completed=completed,
        events_failed=failed,
        matches_discovered=sum(item.matches_discovered for item in event_summaries),
        matches_ingested=sum(item.matches_ingested for item in event_summaries),
        matches_skipped=sum(item.matches_skipped for item in event_summaries),
        matches_failed=sum(item.matches_failed for item in event_summaries),
        maps=sum(item.maps_created for item in event_summaries),
        player_map_stats=sum(item.player_map_stats_created for item in event_summaries),
        resolved_by_event_roster=sum(item.resolved_by_event_roster for item in event_summaries),
        resolved_by_team_roster=sum(item.resolved_by_team_roster for item in event_summaries),
        resolved_by_history=sum(item.resolved_by_history for item in event_summaries),
        resolved_by_search=sum(item.resolved_by_search for item in event_summaries),
        ambiguous=sum(item.ambiguous_players for item in event_summaries),
        unresolved=sum(item.unresolved_players for item in event_summaries),
        complete_maps=sum(item.maps_complete for item in event_summaries),
        incomplete_maps=sum(item.maps_incomplete for item in event_summaries),
        empty_maps=sum(item.maps_empty for item in event_summaries),
        http_429_count=sum(item.http_429_count for item in event_summaries),
        cache_hits=sum(item.cache_hits for item in event_summaries),
        cache_misses=sum(item.cache_misses for item in event_summaries),
        dry_run=dry_run,
        event_summaries=event_summaries,
    )


def _cache_counts(provider: VlrApiProvider) -> tuple[int, int]:
    if isinstance(provider, CachingVlrApiIngestionProvider):
        return provider.cache_hits, provider.cache_misses
    return 0, 0


def _http_429_count(client: VlrggApiClient | None) -> int:
    if client is None:
        return 0
    return int(getattr(client, "http_429_count", 0))
