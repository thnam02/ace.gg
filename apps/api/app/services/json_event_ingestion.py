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
from app.services.event_ingestion import EventIngestionService, load_known_player_index
from app.services.ingestion_sources import VlrApiEventIngestionSource


def ingest_json_event(
    session: Session,
    event_id: int,
    *,
    dry_run: bool = False,
    raw_cache_dir: Path | None = None,
    base_url: str | None = None,
) -> EventIngestionSummary:
    api_url = base_url or settings.vlrggapi_base_url
    client = create_vlrggapi_client(api_url, timeout=60.0, request_delay=1.2, max_retries=8)
    base_provider = create_vlr_api_ingestion_provider(api_url, client=client)
    provider: VlrApiIngestionProvider | CachingVlrApiIngestionProvider = base_provider
    if raw_cache_dir is not None:
        cache = VlrggApiRawCache(raw_cache_dir)
        provider = CachingVlrApiIngestionProvider(base_provider, cache)

    known_handles, known_ambiguous = load_known_player_index(session)
    source = VlrApiEventIngestionSource(
        provider,
        known_handles=known_handles,
        known_ambiguous=known_ambiguous,
    )
    service = EventIngestionService(session, source, dry_run=dry_run)
    return service.ingest_event(event_id)


def ingest_json_events(
    session: Session,
    event_ids: list[int],
    *,
    dry_run: bool = False,
    continue_on_error: bool = True,
    raw_cache_dir: Path | None = None,
    base_url: str | None = None,
) -> list[EventIngestionSummary]:
    summaries: list[EventIngestionSummary] = []
    for event_id in event_ids:
        try:
            summaries.append(
                ingest_json_event(
                    session,
                    event_id,
                    dry_run=dry_run,
                    raw_cache_dir=raw_cache_dir,
                    base_url=base_url,
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
    return summaries
