import re

import httpx

from app.schemas.player import PlayerProfile, PlayerStats

_VLR_PLAYER_PATH = re.compile(r"/player/(\d+)")


def _parse_float(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    cleaned = str(value).replace("%", "").strip()
    if not cleaned:
        return 0.0
    return float(cleaned)


def _aggregate_agent_stats(agent_stats: list[dict[str, object]]) -> tuple[PlayerStats, float]:
    if not agent_stats:
        empty = PlayerStats(matches=0, acs=0.0, kd=0.0, hs_percent=0.0, adr=0.0, win_rate=0.0)
        return empty, 0.0

    total_rounds = sum(int(entry.get("rounds") or 0) for entry in agent_stats)
    total_kills = sum(int(entry.get("kills") or 0) for entry in agent_stats)
    total_deaths = sum(int(entry.get("deaths") or 0) for entry in agent_stats)
    matches = max(int(entry.get("use_count") or 0) for entry in agent_stats)

    if total_rounds > 0:
        acs = (
            sum(
                _parse_float(entry.get("acs")) * int(entry.get("rounds") or 0)
                for entry in agent_stats
            )
            / total_rounds
        )
        adr = (
            sum(
                _parse_float(entry.get("adr")) * int(entry.get("rounds") or 0)
                for entry in agent_stats
            )
            / total_rounds
        )
        avg_rating = (
            sum(
                _parse_float(entry.get("rating")) * int(entry.get("rounds") or 0)
                for entry in agent_stats
            )
            / total_rounds
        )
    else:
        acs = _parse_float(agent_stats[0].get("acs"))
        adr = _parse_float(agent_stats[0].get("adr"))
        avg_rating = _parse_float(agent_stats[0].get("rating"))

    kd = total_kills / total_deaths if total_deaths else float(total_kills)

    stats = PlayerStats(
        matches=matches,
        acs=round(acs, 1),
        kd=round(kd, 2),
        hs_percent=0.0,
        adr=round(adr, 1),
        win_rate=0.0,
    )
    return stats, round(avg_rating, 2)


def _win_rate_from_matches(matches: list[dict[str, object]], team_names: set[str]) -> float:
    if not matches or not team_names:
        return 0.0

    wins = 0
    counted = 0
    for match in matches:
        teams = match.get("teams")
        if not isinstance(teams, dict):
            continue

        team1 = str(teams.get("team1") or "")
        team2 = str(teams.get("team2") or "")
        score = str(match.get("score") or "")
        parts = score.split("-")
        if len(parts) != 2:
            continue

        try:
            score1, score2 = int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            continue

        player_side: int | None = None
        if team1 in team_names:
            player_side = 1
        elif team2 in team_names:
            player_side = 2
        else:
            continue

        counted += 1
        if player_side == 1 and score1 > score2:
            wins += 1
        elif player_side == 2 and score2 > score1:
            wins += 1

    if counted == 0:
        return 0.0
    return round(wins / counted, 2)


class VlrPlayerDataProvider:
    """Pro player data from a self-hosted vlrggapi instance."""

    def __init__(
        self,
        base_url: str,
        default_players: list[str],
        stats_region: str,
        stats_timespan: str,
        player_timespan: str,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_players = default_players
        self._stats_region = stats_region
        self._stats_timespan = stats_timespan
        self._player_timespan = player_timespan
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)
        self._hs_cache: dict[str, float] | None = None

    def close(self) -> None:
        self._client.close()

    def list_players(self) -> list[PlayerProfile]:
        profiles: list[PlayerProfile] = []
        for player_ref in self._default_players:
            profile = self.get_player(player_ref)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def get_player(self, player_id: str) -> PlayerProfile | None:
        vlr_id = self._resolve_vlr_id(player_id)
        if vlr_id is None:
            return None

        profile_data = self._get_json(
            "/v2/player",
            params={"id": vlr_id, "q": "profile", "timespan": self._player_timespan},
        )
        if profile_data is None:
            return None

        matches_data = self._get_json(
            "/v2/player",
            params={"id": vlr_id, "q": "matches", "page": 1},
        )
        matches: list[dict[str, object]] = []
        if isinstance(matches_data, dict):
            raw_matches = matches_data.get("matches")
            if isinstance(raw_matches, list):
                matches = [entry for entry in raw_matches if isinstance(entry, dict)]

        return self._map_profile(vlr_id, profile_data, matches)

    def _resolve_vlr_id(self, player_ref: str) -> str | None:
        trimmed = player_ref.strip()
        if not trimmed:
            return None

        if trimmed.isdigit():
            return trimmed

        path_match = _VLR_PLAYER_PATH.search(trimmed)
        if path_match:
            return path_match.group(1)

        search_data = self._get_json("/v2/search", params={"q": trimmed})
        if not isinstance(search_data, dict):
            return None

        segments = search_data.get("segments")
        if not isinstance(segments, dict):
            return None

        results = segments.get("results")
        if not isinstance(results, dict):
            return None

        players = results.get("players")
        if not isinstance(players, list) or not players:
            return None

        first = players[0]
        if not isinstance(first, dict):
            return None

        player_id = first.get("id")
        return str(player_id) if player_id is not None else None

    def _map_profile(
        self,
        vlr_id: str,
        data: dict[str, object],
        matches: list[dict[str, object]],
    ) -> PlayerProfile:
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        current_teams = (
            data.get("current_teams") if isinstance(data.get("current_teams"), list) else []
        )
        past_teams = data.get("past_teams") if isinstance(data.get("past_teams"), list) else []
        agent_stats = data.get("agent_stats") if isinstance(data.get("agent_stats"), list) else []

        typed_agent_stats = [entry for entry in agent_stats if isinstance(entry, dict)]
        stats, avg_rating = _aggregate_agent_stats(typed_agent_stats)

        display_name = str(info.get("name") or vlr_id)
        team_names: set[str] = set()
        team: str | None = None

        for entry in current_teams:
            if isinstance(entry, dict) and entry.get("name"):
                name = str(entry["name"])
                team_names.add(name)
                if team is None:
                    team = name

        for entry in past_teams:
            if isinstance(entry, dict) and entry.get("name"):
                team_names.add(str(entry["name"]))

        stats.win_rate = _win_rate_from_matches(matches, team_names)
        stats.hs_percent = self._headshot_percent_for(display_name)

        return PlayerProfile(
            id=vlr_id,
            display_name=display_name,
            riot_id=f"https://www.vlr.gg/player/{vlr_id}",
            team=team,
            region=str(info.get("country") or "Unknown"),
            rank=f"{avg_rating:.2f} rating",
            stats=stats,
        )

    def _headshot_percent_for(self, display_name: str) -> float:
        if self._hs_cache is None:
            self._hs_cache = {}
            stats_data = self._get_json(
                "/v2/stats",
                params={"region": self._stats_region, "timespan": self._stats_timespan},
            )
            if isinstance(stats_data, dict):
                segments = stats_data.get("segments")
                if isinstance(segments, list):
                    for entry in segments:
                        if not isinstance(entry, dict):
                            continue
                        player_name = str(entry.get("player") or "").lower()
                        if player_name:
                            self._hs_cache[player_name] = _parse_float(
                                entry.get("headshot_percentage")
                            )

        return self._hs_cache.get(display_name.lower(), 0.0)

    def _get_json(self, path: str, params: dict[str, str | int] | None = None) -> object | None:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        payload = response.json()
        if not isinstance(payload, dict):
            return None

        if payload.get("status") != "success":
            return None

        return payload.get("data")
