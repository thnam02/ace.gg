from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.providers.vlr_api_ingestion_provider import (
    CachingVlrApiIngestionProvider,
    VlrApiIngestionProvider,
)
from app.providers.vlrggapi_factory import create_vlr_api_ingestion_provider, create_vlrggapi_client
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.schemas.ingestion import EventIngestionSummary
from app.services.event_ingestion import (
    EventIngestionService,
    load_known_player_index,
    load_player_team_history_index,
)
from app.services.historical_player_identity import HistoricalPlayerIdentityResolver
from app.services.ingestion_sources import VlrApiEventIngestionSource

VlrApiProvider = VlrApiIngestionProvider | CachingVlrApiIngestionProvider


def ingest_json_event(
    session: Session,
    event_id: int,
    *,
    dry_run: bool = False,
    raw_cache_dir: Path | None = None,
    base_url: str | None = None,
    provider: VlrApiProvider | None = None,
    identity_lookup: HistoricalPlayerIdentityResolver | None = None,
) -> EventIngestionSummary:
    api_url = base_url or settings.vlrggapi_base_url
    client = None
    owns_provider = provider is None
    if provider is None:
        client = create_vlrggapi_client(api_url, timeout=60.0, request_delay=1.2, max_retries=8)
        base_provider = create_vlr_api_ingestion_provider(api_url, client=client)
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
    service = EventIngestionService(session, source, dry_run=dry_run)
    try:
        return service.ingest_event(event_id)
    finally:
        if owns_provider and client is not None:
            client.close()


def ingest_json_events(
    session: Session,
    event_ids: list[int],
    *,
    dry_run: bool = False,
    continue_on_error: bool = True,
    raw_cache_dir: Path | None = None,
    base_url: str | None = None,
) -> list[EventIngestionSummary]:
    api_url = base_url or settings.vlrggapi_base_url
    client = create_vlrggapi_client(api_url, timeout=60.0, request_delay=1.2, max_retries=8)
    base_provider = create_vlr_api_ingestion_provider(api_url, client=client)
    provider: VlrApiProvider = base_provider
    if raw_cache_dir is not None:
        cache = VlrggApiRawCache(raw_cache_dir)
        provider = CachingVlrApiIngestionProvider(base_provider, cache)
    lookup = HistoricalPlayerIdentityResolver(provider)
    summaries: list[EventIngestionSummary] = []
    try:
        for event_id in event_ids:
            try:
                summaries.append(
                    ingest_json_event(
                        session,
                        event_id,
                        dry_run=dry_run,
                        provider=provider,
                        identity_lookup=lookup,
                    )
                )
            except Exception:
                if not continue_on_error:
                    raise
                summaries.append(
                    EventIngestionSummary(
                        event_id=event_id,
                        matches_failed=1,
                        errors=[f"event_id={event_id}: ingestion failed"],
                        dry_run=dry_run,
                    )
                )
    finally:
        client.close()
    return summaries
