from __future__ import annotations

from typing import Any

from app.normalizers.player_identity_resolver import PlayerIdentityResolver
from app.normalizers.vlr_api_event_normalizer import VlrApiEventNormalizer
from app.normalizers.vlr_api_match_normalizer import VlrApiMatchNormalizer
from app.normalizers.vlr_api_parsing import as_dict, as_list, parse_vlr_id, unwrap_match_payload
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
        known_ambiguous: set[str] | None = None,
    ) -> None:
        self._provider = provider
        self._diagnostics = diagnostics or IngestionDiagnostics()
        self._event_normalizer = event_normalizer or VlrApiEventNormalizer()
        self._match_normalizer = match_normalizer or VlrApiMatchNormalizer(self._diagnostics)
        self._known_handles = known_handles or {}
        self._known_ambiguous = known_ambiguous or set()
        self._identity_resolver: PlayerIdentityResolver | None = None
        self._event: NormalizedEvent | None = None
        self._event_data: dict[str, Any] | None = None
        self._team_profile_cache: dict[int, dict[str, Any] | None] = {}

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
            known_ambiguous=self._known_ambiguous,
            diagnostics=self._diagnostics,
        )
        self._event = page_data.event
        self._team_profile_cache.clear()
        return page_data

    def load_match(self, match_id: int, event_id: int) -> NormalizedMatchData:
        match_data = self._provider.get_match(match_id)
        self._ensure_identity_resolver()
        self._enrich_team_rosters(match_data)
        return self._match_normalizer.normalize(
            match_data,
            event_id=event_id,
            event=self._event,
            identity_resolver=self._identity_resolver,
        )

    def _ensure_identity_resolver(self) -> None:
        if self._identity_resolver is not None:
            return
        if self._event_data is None:
            return
        self._identity_resolver = PlayerIdentityResolver.from_event_teams(
            self._event_data,
            known_handles=self._known_handles,
            known_ambiguous=self._known_ambiguous,
            diagnostics=self._diagnostics,
        )
        for team_id, payload in self._team_profile_cache.items():
            if payload is not None:
                self._identity_resolver.add_team_roster(team_id, payload)

    def _enrich_team_rosters(self, match_data: dict[str, Any]) -> None:
        if self._identity_resolver is None:
            return
        payload = unwrap_match_payload(match_data)
        for entry in as_list(payload.get("teams")):
            team_id = parse_vlr_id(as_dict(entry).get("id"))
            if team_id is None:
                continue
            self._ensure_team_roster(team_id)

    def _ensure_team_roster(self, team_id: int) -> None:
        if self._identity_resolver is None:
            return
        if team_id in self._team_profile_cache:
            self._diagnostics.team_profiles_cached += 1
            return
        try:
            profile = self._provider.get_team(team_id)
        except Exception:
            self._team_profile_cache[team_id] = None
            return
        self._team_profile_cache[team_id] = profile
        self._diagnostics.team_profiles_fetched += 1
        self._identity_resolver.add_team_roster(team_id, profile)
