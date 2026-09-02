from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.normalizers.vlr_api_parsing import normalize_player_name
from app.providers.vlrggapi_client import VlrggApiClient
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache


class VlrApiIngestionProvider:
    """Fetch raw vlrggapi JSON for ingestion."""

    def __init__(self, client: VlrggApiClient) -> None:
        self._client = client

    def close(self) -> None:
        self._client.close()

    def get_match(self, match_id: int) -> dict[str, Any]:
        return self._client.get_data("/v2/match/details", params={"match_id": match_id})

    def get_event(self, event_id: int) -> dict[str, Any]:
        return self._client.get_data(f"/v2/event/{event_id}")

    def get_event_matches(self, event_id: int) -> dict[str, Any]:
        return self._client.get_data("/v2/events/matches", params={"event_id": event_id})

    def get_player(self, player_id: int) -> dict[str, Any]:
        return self._client.get_data(
            "/v2/player",
            params={"id": player_id, "q": "profile"},
        )

    def get_team(self, team_id: int) -> dict[str, Any]:
        return self._client.get_data("/v2/team", params={"id": team_id, "q": "profile"})

    def search(self, query: str) -> dict[str, Any]:
        return self._client.get_data("/v2/search", params={"q": query})


class StaticVlrApiIngestionProvider:
    """In-memory vlrggapi JSON keyed by resource ID (tests/fixtures)."""

    def __init__(
        self,
        matches: Mapping[int, dict[str, Any]],
        *,
        events: Mapping[int, dict[str, Any]] | None = None,
        event_matches: Mapping[int, dict[str, Any]] | None = None,
        players: Mapping[int, dict[str, Any]] | None = None,
        teams: Mapping[int, dict[str, Any]] | None = None,
        searches: Mapping[str, dict[str, Any]] | None = None,
    ) -> None:
        self._matches = dict(matches)
        self._events = dict(events or {})
        self._event_matches = dict(event_matches or {})
        self._players = dict(players or {})
        self._teams = dict(teams or {})
        self._searches = {
            normalize_player_name(str(key)): value for key, value in (searches or {}).items()
        }

    def close(self) -> None:
        return None

    def get_match(self, match_id: int) -> dict[str, Any]:
        try:
            return self._matches[match_id]
        except KeyError as exc:
            from app.providers.vlrggapi_errors import VlrggApiHttpError

            raise VlrggApiHttpError(404, f"/v2/match/details?match_id={match_id}") from exc

    def get_event(self, event_id: int) -> dict[str, Any]:
        try:
            return self._events[event_id]
        except KeyError as exc:
            from app.providers.vlrggapi_errors import VlrggApiHttpError

            raise VlrggApiHttpError(404, f"/v2/event/{event_id}") from exc

    def get_event_matches(self, event_id: int) -> dict[str, Any]:
        if event_id in self._event_matches:
            return self._event_matches[event_id]
        return self.get_event(event_id)

    def get_player(self, player_id: int) -> dict[str, Any]:
        try:
            return self._players[player_id]
        except KeyError as exc:
            from app.providers.vlrggapi_errors import VlrggApiHttpError

            raise VlrggApiHttpError(404, f"/v2/player?id={player_id}") from exc

    def get_team(self, team_id: int) -> dict[str, Any]:
        try:
            return self._teams[team_id]
        except KeyError as exc:
            from app.providers.vlrggapi_errors import VlrggApiHttpError

            raise VlrggApiHttpError(404, f"/v2/team?id={team_id}") from exc

    def search(self, query: str) -> dict[str, Any]:
        key = normalize_player_name(query)
        try:
            return self._searches[key]
        except KeyError as exc:
            from app.providers.vlrggapi_errors import VlrggApiHttpError

            raise VlrggApiHttpError(404, f"/v2/search?q={query}") from exc


class CachingVlrApiIngestionProvider:
    """Wrap a provider and persist raw JSON via VlrggApiRawCache."""

    def __init__(
        self,
        provider: VlrApiIngestionProvider | StaticVlrApiIngestionProvider,
        cache: VlrggApiRawCache,
    ) -> None:
        self._provider = provider
        self._cache = cache

    def close(self) -> None:
        self._provider.close()

    def get_match(self, match_id: int) -> dict[str, Any]:
        cached = self._cache.load("matches", match_id)
        if cached is not None:
            return cached
        data = self._provider.get_match(match_id)
        self._cache.save("matches", match_id, data)
        return data

    def get_event(self, event_id: int) -> dict[str, Any]:
        cached = self._cache.load("events", event_id)
        if cached is not None:
            return cached
        data = self._provider.get_event(event_id)
        self._cache.save("events", event_id, data)
        return data

    def get_event_matches(self, event_id: int) -> dict[str, Any]:
        cached = self._cache.load("event_matches", event_id)
        if cached is not None:
            return cached
        data = self._provider.get_event_matches(event_id)
        self._cache.save("event_matches", event_id, data)
        return data

    def get_player(self, player_id: int) -> dict[str, Any]:
        cached = self._cache.load("players", player_id)
        if cached is not None:
            return cached
        data = self._provider.get_player(player_id)
        self._cache.save("players", player_id, data)
        return data

    def get_team(self, team_id: int) -> dict[str, Any]:
        cached = self._cache.load("teams", team_id)
        if cached is not None:
            return cached
        data = self._provider.get_team(team_id)
        self._cache.save("teams", team_id, data)
        return data

    def search(self, query: str) -> dict[str, Any]:
        cached = self._cache.load_key("player_search", query)
        if cached is not None:
            return cached
        data = self._provider.search(query)
        self._cache.save_key("player_search", query, data)
        return data
