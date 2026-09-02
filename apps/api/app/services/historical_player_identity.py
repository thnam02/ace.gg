from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from app.normalizers.vlr_api_parsing import (
    normalize_player_name,
    parse_player_profile_handle,
    parse_search_players,
    parse_vlr_id,
    profile_has_team_evidence,
    profile_matches_team,
    search_result_handle,
)


class IdentityLookupStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class IdentityLookupResult:
    status: IdentityLookupStatus
    vlr_player_id: int | None = None
    resolution_method: str | None = None
    confidence_reason: str = ""
    candidate_count: int = 0


class IdentityLookupProvider(Protocol):
    def search(self, query: str) -> dict[str, Any]: ...

    def get_player(self, player_id: int) -> dict[str, Any]: ...


class HistoricalPlayerIdentityResolver:
    """Search VLR and verify player profiles without fuzzy identity merges."""

    def __init__(self, provider: IdentityLookupProvider) -> None:
        self._provider = provider
        self._search_cache: dict[str, dict[str, Any] | None] = {}
        self._profile_cache: dict[int, dict[str, Any] | None] = {}
        self.searches_fetched = 0
        self.searches_cached = 0
        self.profiles_fetched = 0
        self.profiles_cached = 0

    def lookup(
        self,
        player_handle: str,
        *,
        match_team_id: int | None = None,
        match_date: datetime | None = None,
        event_id: int | None = None,
        team_name: str | None = None,
        team_tag: str | None = None,
    ) -> IdentityLookupResult:
        del match_team_id, match_date, event_id
        normalized = normalize_player_name(player_handle)
        if not normalized:
            return IdentityLookupResult(
                status=IdentityLookupStatus.UNRESOLVED,
                confidence_reason="empty handle",
            )

        payload = self._search(player_handle)
        if payload is None:
            return IdentityLookupResult(
                status=IdentityLookupStatus.UNRESOLVED,
                confidence_reason="player search failed",
            )

        rows = parse_search_players(payload)
        exact: list[tuple[int, dict[str, Any]]] = []
        seen_ids: set[int] = set()
        for row in rows:
            player_id = parse_vlr_id(row.get("id"))
            handle = search_result_handle(row)
            if player_id is None or not handle:
                continue
            if normalize_player_name(handle) != normalized:
                continue
            if player_id in seen_ids:
                continue
            seen_ids.add(player_id)
            exact.append((player_id, row))

        if not exact:
            return IdentityLookupResult(
                status=IdentityLookupStatus.UNRESOLVED,
                candidate_count=len(rows),
                confidence_reason="no exact handle match",
            )

        if len(exact) == 1:
            return self._verify_unique_candidate(
                exact[0][0],
                normalized_handle=normalized,
                team_name=team_name,
                team_tag=team_tag,
            )

        return self._disambiguate_candidates(
            exact,
            normalized_handle=normalized,
            team_name=team_name,
            team_tag=team_tag,
        )

    def _verify_unique_candidate(
        self,
        player_id: int,
        *,
        normalized_handle: str,
        team_name: str | None,
        team_tag: str | None,
    ) -> IdentityLookupResult:
        if not team_name and not team_tag:
            return IdentityLookupResult(
                status=IdentityLookupStatus.RESOLVED,
                vlr_player_id=player_id,
                resolution_method="search",
                confidence_reason=(
                    "exact handle + unique search result + no conflicting team evidence"
                ),
                candidate_count=1,
            )

        profile = self._profile(player_id)
        if profile is None:
            return IdentityLookupResult(
                status=IdentityLookupStatus.RESOLVED,
                vlr_player_id=player_id,
                resolution_method="search",
                confidence_reason=(
                    "exact handle + unique search result; profile unavailable, "
                    "no conflicting team evidence"
                ),
                candidate_count=1,
            )

        if not self._profile_handle_matches(profile, normalized_handle):
            return IdentityLookupResult(
                status=IdentityLookupStatus.UNRESOLVED,
                candidate_count=1,
                confidence_reason="unique search result profile handle does not match",
            )

        if profile_matches_team(profile, team_name=team_name, team_tag=team_tag):
            return IdentityLookupResult(
                status=IdentityLookupStatus.RESOLVED,
                vlr_player_id=player_id,
                resolution_method="search",
                confidence_reason="exact handle + candidate was associated with match team",
                candidate_count=1,
            )
        if not profile_has_team_evidence(profile):
            return IdentityLookupResult(
                status=IdentityLookupStatus.RESOLVED,
                vlr_player_id=player_id,
                resolution_method="search",
                confidence_reason=(
                    "exact handle + unique search result + no conflicting team evidence"
                ),
                candidate_count=1,
            )
        return IdentityLookupResult(
            status=IdentityLookupStatus.UNRESOLVED,
            candidate_count=1,
            confidence_reason="unique search result profile teams conflict with match team",
        )

    def _disambiguate_candidates(
        self,
        exact: list[tuple[int, dict[str, Any]]],
        *,
        normalized_handle: str,
        team_name: str | None,
        team_tag: str | None,
    ) -> IdentityLookupResult:
        candidate_count = len(exact)
        if not team_name and not team_tag:
            return IdentityLookupResult(
                status=IdentityLookupStatus.AMBIGUOUS,
                candidate_count=candidate_count,
                confidence_reason="multiple exact-handle players",
            )

        matching: list[int] = []
        for player_id, _row in exact:
            profile = self._profile(player_id)
            if profile is None:
                continue
            if not self._profile_handle_matches(profile, normalized_handle):
                continue
            if profile_matches_team(profile, team_name=team_name, team_tag=team_tag):
                matching.append(player_id)

        unique_ids = set(matching)
        if len(unique_ids) == 1:
            return IdentityLookupResult(
                status=IdentityLookupStatus.RESOLVED,
                vlr_player_id=next(iter(unique_ids)),
                resolution_method="search",
                confidence_reason="exact handle + unique team association among search candidates",
                candidate_count=candidate_count,
            )
        if unique_ids:
            return IdentityLookupResult(
                status=IdentityLookupStatus.AMBIGUOUS,
                candidate_count=candidate_count,
                confidence_reason="multiple exact-handle players associated with match team",
            )
        return IdentityLookupResult(
            status=IdentityLookupStatus.AMBIGUOUS,
            candidate_count=candidate_count,
            confidence_reason="multiple exact-handle players; no unique team evidence",
        )

    def _search(self, query: str) -> dict[str, Any] | None:
        key = normalize_player_name(query)
        if key in self._search_cache:
            self.searches_cached += 1
            return self._search_cache[key]
        try:
            payload = self._provider.search(query)
        except Exception:
            self._search_cache[key] = None
            return None
        self._search_cache[key] = payload
        self.searches_fetched += 1
        return payload

    def _profile(self, player_id: int) -> dict[str, Any] | None:
        if player_id in self._profile_cache:
            self.profiles_cached += 1
            return self._profile_cache[player_id]
        try:
            payload = self._provider.get_player(player_id)
        except Exception:
            self._profile_cache[player_id] = None
            return None
        self._profile_cache[player_id] = payload
        self.profiles_fetched += 1
        return payload

    def _profile_handle_matches(self, payload: dict[str, Any], normalized_handle: str) -> bool:
        profile_handle = parse_player_profile_handle(payload)
        if not profile_handle:
            return True
        return normalize_player_name(search_result_handle({"name": profile_handle})) == (
            normalized_handle
        )
