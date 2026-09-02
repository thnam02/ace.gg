from __future__ import annotations

from typing import Any

from app.normalizers.vlr_api_parsing import (
    as_dict,
    as_list,
    clutch_stats_from_advanced,
    max_kills_from_advanced,
    parse_best_of,
    parse_datetime_text,
    parse_vlr_id,
    team_tag_from_name,
)
from app.parsers.agents import agent_role, normalize_agent_name
from app.parsers.numbers import parse_int, parse_optional_float, parse_optional_int
from app.schemas.ingestion import (
    NormalizedAgent,
    NormalizedEvent,
    NormalizedMatchData,
    NormalizedMatchMap,
    NormalizedPlayer,
    NormalizedPlayerMapStats,
    NormalizedTeam,
)


class VlrApiMatchNormalizer:
    """Convert vlrggapi match details JSON into canonical ingestion DTOs."""

    def normalize(
        self,
        match_data: dict[str, Any],
        *,
        event_id: int,
        event: NormalizedEvent | None = None,
        player_id_map: dict[str, int] | None = None,
    ) -> NormalizedMatchData:
        match_id = parse_vlr_id(match_data.get("match_id"))
        if match_id is None:
            raise ValueError("Match JSON is missing match_id")

        teams = self._normalize_teams(match_data)
        if len(teams) < 2:
            raise ValueError("Match JSON must include two teams")

        team_a, team_b = teams[0], teams[1]
        event_payload = as_dict(match_data.get("event"))
        normalized_event = event or NormalizedEvent(
            vlr_event_id=event_id,
            name=str(event_payload.get("name") or f"Event {event_id}"),
            region=None,
            tier=None,
            start_date=None,
            end_date=None,
            season_year=None,
            status=str(match_data.get("status") or None),
        )

        maps = self._normalize_maps(
            match_data,
            team_a=team_a,
            team_b=team_b,
            player_id_map=player_id_map or {},
        )

        winner_id = _series_winner(team_a, team_b, maps)
        status = str(match_data.get("status") or "").lower() or None
        if status is None and winner_id is not None:
            status = "completed"

        return NormalizedMatchData(
            vlr_match_id=match_id,
            event=normalized_event,
            team_a=team_a,
            team_b=team_b,
            winner_vlr_team_id=winner_id,
            played_at=parse_datetime_text(str(match_data.get("date") or "")),
            best_of=parse_best_of(
                str(match_data.get("map_vetos") or ""),
                len(maps),
            ),
            status=status,
            maps=maps,
        )

    def _normalize_teams(self, match_data: dict[str, Any]) -> list[NormalizedTeam]:
        teams: list[NormalizedTeam] = []
        for entry in as_list(match_data.get("teams")):
            row = as_dict(entry)
            team_id = parse_vlr_id(row.get("id"))
            name = str(row.get("name") or "").strip()
            if team_id is None or not name:
                continue
            teams.append(
                NormalizedTeam(
                    vlr_team_id=team_id,
                    name=name,
                    tag=team_tag_from_name(name),
                    country=None,
                    region=None,
                )
            )
        return teams

    def _normalize_maps(
        self,
        match_data: dict[str, Any],
        *,
        team_a: NormalizedTeam,
        team_b: NormalizedTeam,
        player_id_map: dict[str, int],
    ) -> list[NormalizedMatchMap]:
        performance = as_dict(match_data.get("performance"))
        maps: list[NormalizedMatchMap] = []
        for index, entry in enumerate(as_list(match_data.get("maps")), start=1):
            row = as_dict(entry)
            map_name = str(row.get("map_name") or f"Map {index}")
            score = as_dict(row.get("score"))
            team_a_score = parse_optional_int(as_dict(score.get("team1")).get("total"))
            team_b_score = parse_optional_int(as_dict(score.get("team2")).get("total"))
            winner_id = None
            if team_a_score is not None and team_b_score is not None:
                if team_a_score > team_b_score:
                    winner_id = team_a.vlr_team_id
                elif team_b_score > team_a_score:
                    winner_id = team_b.vlr_team_id

            rounds_played = None
            if team_a_score is not None and team_b_score is not None:
                rounds_played = team_a_score + team_b_score

            players_payload = as_dict(row.get("players"))
            team_a_stats = self._normalize_player_stats(
                as_list(players_payload.get("team1")),
                team_vlr_id=team_a.vlr_team_id,
                performance=performance,
                player_id_map=player_id_map,
            )
            team_b_stats = self._normalize_player_stats(
                as_list(players_payload.get("team2")),
                team_vlr_id=team_b.vlr_team_id,
                performance=performance,
                player_id_map=player_id_map,
            )

            maps.append(
                NormalizedMatchMap(
                    map_number=index,
                    map_name=map_name,
                    team_a_score=team_a_score,
                    team_b_score=team_b_score,
                    winner_vlr_team_id=winner_id,
                    rounds_played=rounds_played,
                    player_stats=team_a_stats + team_b_stats,
                )
            )
        return maps

    def _normalize_player_stats(
        self,
        players: list[Any],
        *,
        team_vlr_id: int,
        performance: dict[str, Any],
        player_id_map: dict[str, int],
    ) -> list[NormalizedPlayerMapStats]:
        stats: list[NormalizedPlayerMapStats] = []
        for entry in players:
            row = as_dict(entry)
            handle = str(row.get("name") or "").strip()
            if not handle:
                continue
            player_id = parse_vlr_id(row.get("id"))
            if player_id is None:
                player_id = player_id_map.get(handle.lower())
            if player_id is None:
                raise ValueError(f"Could not resolve VLR player id for {handle}")

            agent_name = normalize_agent_name(str(row.get("agent") or "Unknown"))
            clutch_wins, clutch_attempts = clutch_stats_from_advanced(performance, handle)
            max_kills = max_kills_from_advanced(performance, handle)

            stats.append(
                NormalizedPlayerMapStats(
                    player=NormalizedPlayer(
                        vlr_player_id=player_id,
                        handle=handle,
                        real_name=None,
                        country=None,
                    ),
                    team_vlr_id=team_vlr_id,
                    agent=NormalizedAgent(name=agent_name, role=agent_role(agent_name)),
                    rounds=parse_int(row.get("rounds"), default=0),
                    kills=parse_int(row.get("kills"), default=0),
                    deaths=parse_int(row.get("deaths"), default=0),
                    assists=parse_int(row.get("assists"), default=0),
                    first_kills=parse_int(row.get("fk"), default=0),
                    first_deaths=parse_int(row.get("fd"), default=0),
                    adr=parse_optional_float(row.get("adr")),
                    kast_pct=parse_optional_float(row.get("kast")),
                    acs=parse_optional_float(row.get("acs")),
                    vlr_rating=parse_optional_float(row.get("rating")),
                    headshot_pct=parse_optional_float(row.get("hs_pct")),
                    clutch_wins=clutch_wins,
                    clutch_attempts=clutch_attempts,
                    max_kills=max_kills,
                )
            )
        return stats


def _series_winner(
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
    maps: list[NormalizedMatchMap],
) -> int | None:
    team_a_maps = 0
    team_b_maps = 0
    for map_row in maps:
        if map_row.winner_vlr_team_id == team_a.vlr_team_id:
            team_a_maps += 1
        elif map_row.winner_vlr_team_id == team_b.vlr_team_id:
            team_b_maps += 1
    if team_a_maps > team_b_maps:
        return team_a.vlr_team_id
    if team_b_maps > team_a_maps:
        return team_b.vlr_team_id
    return None
