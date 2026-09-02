from __future__ import annotations

from typing import Any

from app.normalizers.player_identity_resolver import PlayerIdentityResolver
from app.normalizers.vlr_api_event_normalizer import VlrApiEventNormalizer
from app.normalizers.vlr_api_match_normalizer import VlrApiMatchNormalizer
from app.parsers.event_parser import EventParser
from app.parsers.match_parser import MatchParser
from app.providers.vlr_api_ingestion_provider import (
    CachingVlrApiIngestionProvider,
    StaticVlrApiIngestionProvider,
    VlrApiIngestionProvider,
)
from app.providers.vlr_provider import VLRProvider
from app.schemas.ingestion import NormalizedEvent, NormalizedEventPageData, NormalizedMatchData
from app.schemas.ingestion_diagnostics import IngestionDiagnostics


class HtmlEventIngestionSource:
    """HTML VLR provider + parsers."""

    def __init__(
        self,
        provider: VLRProvider,
        *,
        event_parser: EventParser | None = None,
        match_parser: MatchParser | None = None,
    ) -> None:
        self._provider = provider
        self._event_parser = event_parser or EventParser()
        self._match_parser = match_parser or MatchParser()

    def load_event_page(self, event_id: int) -> NormalizedEventPageData:
        event_html = self._provider.get_event(event_id)
        matches_html = self._provider.get_event_matches(event_id)
        page_data = self._event_parser.parse(event_html, event_id=event_id)
        for match_id in self._event_parser.discover_match_ids(matches_html, event_id=event_id):
            if match_id not in page_data.match_ids:
                page_data.match_ids.append(match_id)
        return page_data

    def load_match(self, match_id: int, event_id: int) -> NormalizedMatchData:
        html = self._provider.get_match(match_id)
        return self._match_parser.parse(html, match_id=match_id)


VlrApiIngestionProviderLike = (
    VlrApiIngestionProvider | StaticVlrApiIngestionProvider | CachingVlrApiIngestionProvider
)


class VlrApiEventIngestionSource:
    """vlrggapi JSON provider + normalizers."""

    def __init__(
        self,
        provider: VlrApiIngestionProviderLike,
        *,
        event_normalizer: VlrApiEventNormalizer | None = None,
        match_normalizer: VlrApiMatchNormalizer | None = None,
        diagnostics: IngestionDiagnostics | None = None,
        known_handles: dict[str, int] | None = None,
    ) -> None:
        self._provider = provider
        self._diagnostics = diagnostics or IngestionDiagnostics()
        self._event_normalizer = event_normalizer or VlrApiEventNormalizer()
        self._match_normalizer = match_normalizer or VlrApiMatchNormalizer(self._diagnostics)
        self._known_handles = known_handles or {}
        self._identity_resolver: PlayerIdentityResolver | None = None
        self._event: NormalizedEvent | None = None
        self._event_data: dict[str, Any] | None = None

    @property
    def diagnostics(self) -> IngestionDiagnostics:
        return self._diagnostics

    def load_event_page(self, event_id: int) -> NormalizedEventPageData:
        event_data = self._provider.get_event(event_id)
        event_matches_data = self._provider.get_event_matches(event_id)
        page_data = self._event_normalizer.normalize_event_page(
            event_id,
            event_data,
            event_matches_data,
        )
        self._event_data = event_data
        self._identity_resolver = PlayerIdentityResolver.from_event_teams(
            event_data,
            known_handles=self._known_handles,
            diagnostics=self._diagnostics,
        )
        self._event = page_data.event
        return page_data

    def load_match(self, match_id: int, event_id: int) -> NormalizedMatchData:
        match_data = self._provider.get_match(match_id)
        if self._identity_resolver is None and self._event_data is not None:
            self._identity_resolver = PlayerIdentityResolver.from_event_teams(
                self._event_data,
                known_handles=self._known_handles,
                diagnostics=self._diagnostics,
            )
        return self._match_normalizer.normalize(
            match_data,
            event_id=event_id,
            event=self._event,
            identity_resolver=self._identity_resolver,
        )
