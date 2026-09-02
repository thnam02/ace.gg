from __future__ import annotations

from datetime import datetime
from typing import Any

from app.normalizers.player_identity_resolver import PlayerIdentityResolver
from app.normalizers.rounds_resolver import resolve_map_rounds, resolve_player_rounds
from app.normalizers.vlr_api_parsing import (
    as_dict,
    as_list,
    clutch_stats_from_advanced,
    max_kills_from_advanced,
    parse_best_of,
    parse_datetime_text,
    parse_map_team_score,
    parse_vlr_id,
    team_tag_from_name,
    unwrap_match_payload,
    year_from_text,
)
from app.parsers.agents import (
    UNKNOWN_AGENT_NAME,
    agent_role,
    normalize_agent_name,
)
from app.parsers.numbers import parse_int, parse_optional_float
from app.schemas.ingestion import (
    NormalizedAgent,
    NormalizedEvent,
    NormalizedMatchData,
    NormalizedMatchMap,
    NormalizedPlayer,
    NormalizedPlayerMapStats,
    NormalizedTeam,
)
from app.schemas.ingestion_diagnostics import IngestionDiagnostics
from app.services.map_completeness import MapCompleteness, classify_player_stat_count


class VlrApiMatchNormalizer:
    """Convert vlrggapi match details JSON into canonical ingestion DTOs."""

    def __init__(self, diagnostics: IngestionDiagnostics | None = None) -> None:
        self._diagnostics = diagnostics

    def normalize(
        self,
        match_data: dict[str, Any],
        *,
        event_id: int,
        event: NormalizedEvent | None = None,
        identity_resolver: PlayerIdentityResolver | None = None,
    ) -> NormalizedMatchData:
        match_data = unwrap_match_payload(match_data)
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

        default_year = normalized_event.season_year or (
            normalized_event.start_date.year if normalized_event.start_date else None
        )
        if default_year is None:
            default_year = year_from_text(normalized_event.name)
        played_at = parse_datetime_text(
            str(match_data.get("date") or ""),
            default_year=default_year,
        )
        maps = self._normalize_maps(
            match_data,
            team_a=team_a,
            team_b=team_b,
            identity_resolver=identity_resolver,
            match_date=played_at,
            event_id=event_id,
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
            played_at=played_at,
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
        identity_resolver: PlayerIdentityResolver | None,
        match_date: datetime | None,
        event_id: int,
    ) -> list[NormalizedMatchMap]:
        performance = as_dict(match_data.get("performance"))
        maps: list[NormalizedMatchMap] = []
        for index, entry in enumerate(as_list(match_data.get("maps")), start=1):
            row = as_dict(entry)
            map_name = str(row.get("map_name") or f"Map {index}")
            score = as_dict(row.get("score"))
            team_a_score = parse_map_team_score(score.get("team1"))
            team_b_score = parse_map_team_score(score.get("team2"))
            winner_id = None
            if team_a_score is not None and team_b_score is not None:
                if team_a_score > team_b_score:
                    winner_id = team_a.vlr_team_id
                elif team_b_score > team_a_score:
                    winner_id = team_b.vlr_team_id

            map_rounds = resolve_map_rounds(team_a_score, team_b_score)

            players_payload = as_dict(row.get("players"))
            team_a_stats = self._normalize_player_stats(
                as_list(players_payload.get("team1")),
                team_vlr_id=team_a.vlr_team_id,
                team_name=team_a.name,
                team_tag=team_a.tag,
                performance=performance,
                identity_resolver=identity_resolver,
                map_rounds=map_rounds,
                match_id=parse_vlr_id(match_data.get("match_id")),
                map_number=index,
                match_date=match_date,
                event_id=event_id,
            )
            team_b_stats = self._normalize_player_stats(
                as_list(players_payload.get("team2")),
                team_vlr_id=team_b.vlr_team_id,
                team_name=team_b.name,
                team_tag=team_b.tag,
                performance=performance,
                identity_resolver=identity_resolver,
                map_rounds=map_rounds,
                match_id=parse_vlr_id(match_data.get("match_id")),
                map_number=index,
                match_date=match_date,
                event_id=event_id,
            )
            player_stats = team_a_stats + team_b_stats
            if (
                team_a_score is not None
                and team_b_score is not None
                and self._diagnostics is not None
            ):
                completeness = classify_player_stat_count(len(player_stats))
                if completeness is MapCompleteness.COMPLETE:
                    self._diagnostics.maps_complete += 1
                elif completeness is MapCompleteness.EMPTY:
                    self._diagnostics.maps_empty += 1
                else:
                    self._diagnostics.maps_incomplete += 1

            maps.append(
                NormalizedMatchMap(
                    map_number=index,
                    map_name=map_name,
                    team_a_score=team_a_score,
                    team_b_score=team_b_score,
                    winner_vlr_team_id=winner_id,
                    rounds_played=map_rounds,
                    player_stats=player_stats,
                )
            )
        return maps

    def _normalize_player_stats(
        self,
        players: list[Any],
        *,
        team_vlr_id: int,
        team_name: str,
        team_tag: str,
        performance: dict[str, Any],
        identity_resolver: PlayerIdentityResolver | None,
        map_rounds: int | None,
        match_id: int | None,
        map_number: int,
        match_date: datetime | None,
        event_id: int,
    ) -> list[NormalizedPlayerMapStats]:
        stats: list[NormalizedPlayerMapStats] = []
        for entry in players:
            row = as_dict(entry)
            handle = str(row.get("name") or "").strip()
            if not handle:
                continue

            explicit_id = parse_vlr_id(row.get("id"))
            player_id: int | None = None
            if identity_resolver is not None:
                player_id = identity_resolver.resolve(
                    handle,
                    explicit_id,
                    team_vlr_id=team_vlr_id,
                    team_name=team_name,
                    team_tag=team_tag,
                    match_date=match_date,
                    event_id=event_id,
                )
            elif explicit_id is not None:
                player_id = explicit_id

            if player_id is None:
                message = (
                    f"match_id={match_id} map={map_number} player={handle}: unresolved identity"
                )
                if self._diagnostics is not None:
                    self._diagnostics.rejected_stat_rows.append(message)
                continue

            rounds, _ = resolve_player_rounds(row, map_rounds=map_rounds)
            if rounds is None:
                message = f"match_id={match_id} map={map_number} player={handle}: unresolved rounds"
                if self._diagnostics is not None:
                    self._diagnostics.missing_rounds += 1
                    self._diagnostics.rejected_stat_rows.append(message)
                continue

            raw_agent = str(row.get("agent") or "").strip()
            agent_name = normalize_agent_name(raw_agent or UNKNOWN_AGENT_NAME)
            if (
                raw_agent
                and agent_name == UNKNOWN_AGENT_NAME
                and raw_agent.strip().lower() != "unknown"
                and self._diagnostics is not None
            ):
                self._diagnostics.record_invalid_agent(raw_agent)
            if agent_name == UNKNOWN_AGENT_NAME and self._diagnostics is not None:
                self._diagnostics.unknown_agent_rows += 1
            clutch_wins, clutch_attempts = clutch_stats_from_advanced(performance, handle)
            if clutch_wins is None and clutch_attempts is None and self._diagnostics is not None:
                self._diagnostics.missing_clutch += 1

            kast = parse_optional_float(row.get("kast"))
            if kast is None and self._diagnostics is not None:
                self._diagnostics.missing_kast += 1

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
                    rounds=rounds,
                    kills=parse_int(row.get("kills"), default=0),
                    deaths=parse_int(row.get("deaths"), default=0),
                    assists=parse_int(row.get("assists"), default=0),
                    first_kills=parse_int(row.get("fk"), default=0),
                    first_deaths=parse_int(row.get("fd"), default=0),
                    adr=parse_optional_float(row.get("adr")),
                    kast_pct=kast,
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
