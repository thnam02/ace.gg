from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Match, MatchMap, PlayerMapStats
from app.normalizers.vlr_api_parsing import (
    as_dict,
    as_list,
    clutch_stats_from_advanced,
    unwrap_match_payload,
)
from app.parsers.agents import normalize_agent_name
from app.parsers.numbers import parse_optional_float, parse_optional_int
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache

_FLOAT_TOLERANCE = 0.51


@dataclass
class SampleDiscrepancy:
    match_id: int
    map_number: int
    player: str
    field: str
    source_value: str
    db_value: str


@dataclass
class SampleValidationReport:
    matches_compared: int = 0
    player_rows_compared: int = 0
    discrepancies: list[SampleDiscrepancy] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class SampleValidationService:
    """Compare canonical DB rows against cached raw vlrggapi match JSON."""

    def validate(
        self,
        session: Session,
        cache: VlrggApiRawCache,
        *,
        match_ids: list[int],
    ) -> SampleValidationReport:
        report = SampleValidationReport()
        for match_id in match_ids:
            payload = cache.load("matches", match_id)
            if payload is None:
                report.skipped.append(f"match_id={match_id}: raw JSON not in cache")
                continue
            match = session.scalar(
                select(Match)
                .where(Match.vlr_match_id == match_id)
                .options(
                    selectinload(Match.maps)
                    .selectinload(MatchMap.player_stats)
                    .selectinload(PlayerMapStats.player),
                    selectinload(Match.maps)
                    .selectinload(MatchMap.player_stats)
                    .selectinload(PlayerMapStats.agent),
                    selectinload(Match.maps)
                    .selectinload(MatchMap.player_stats)
                    .selectinload(PlayerMapStats.team),
                    selectinload(Match.team_a),
                    selectinload(Match.team_b),
                )
            )
            if match is None:
                report.skipped.append(f"match_id={match_id}: not in database")
                continue
            report.matches_compared += 1
            self._compare_match(report, match, payload)
        return report

    def format_report(self, report: SampleValidationReport) -> str:
        lines = [
            f"matches_compared: {report.matches_compared}",
            f"player_rows_compared: {report.player_rows_compared}",
            f"discrepancy_count: {len(report.discrepancies)}",
        ]
        if report.skipped:
            lines.append("skipped:")
            for skipped in report.skipped:
                lines.append(f"  {skipped}")
        if report.discrepancies:
            lines.append("discrepancies:")
            for discrepancy in report.discrepancies[:100]:
                lines.append(
                    "  "
                    f"match={discrepancy.match_id} map={discrepancy.map_number} "
                    f"player={discrepancy.player} {discrepancy.field}: "
                    f"source={discrepancy.source_value} db={discrepancy.db_value}"
                )
        else:
            lines.append("discrepancies: none")
        return "\n".join(lines)

    def _compare_match(
        self,
        report: SampleValidationReport,
        match: Match,
        payload: dict[str, Any],
    ) -> None:
        payload = unwrap_match_payload(payload)
        performance = as_dict(payload.get("performance"))
        maps = as_list(payload.get("maps"))
        db_maps = {match_map.map_number: match_map for match_map in match.maps}
        for index, entry in enumerate(maps, start=1):
            row = as_dict(entry)
            match_map = db_maps.get(index)
            if match_map is None:
                report.discrepancies.append(
                    SampleDiscrepancy(
                        match_id=match.vlr_match_id,
                        map_number=index,
                        player="-",
                        field="map",
                        source_value=str(row.get("map_name") or ""),
                        db_value="missing",
                    )
                )
                continue
            players_payload = as_dict(row.get("players"))
            source_players = as_list(players_payload.get("team1")) + as_list(
                players_payload.get("team2")
            )
            db_by_handle = {
                (stats.player.handle or "").strip().lower(): stats
                for stats in match_map.player_stats
                if stats.player is not None
            }
            for player_row in source_players:
                source = as_dict(player_row)
                handle = str(source.get("name") or "").strip()
                if not handle:
                    continue
                report.player_rows_compared += 1
                db_stats = db_by_handle.get(handle.lower())
                if db_stats is None:
                    report.discrepancies.append(
                        SampleDiscrepancy(
                            match_id=match.vlr_match_id,
                            map_number=index,
                            player=handle,
                            field="player",
                            source_value=handle,
                            db_value="missing",
                        )
                    )
                    continue
                self._compare_player_row(
                    report,
                    match.vlr_match_id,
                    index,
                    handle,
                    source,
                    db_stats,
                    performance,
                )

    def _compare_player_row(
        self,
        report: SampleValidationReport,
        match_id: int,
        map_number: int,
        handle: str,
        source: dict[str, Any],
        db_stats: PlayerMapStats,
        performance: dict[str, Any],
    ) -> None:
        comparisons: list[tuple[str, object | None, object | None]] = [
            (
                "agent",
                normalize_agent_name(str(source.get("agent") or "Unknown")),
                db_stats.agent.name if db_stats.agent else None,
            ),
            ("rounds", parse_optional_int(source.get("rounds")), db_stats.rounds),
            ("kills", parse_optional_int(source.get("kills")), db_stats.kills),
            ("deaths", parse_optional_int(source.get("deaths")), db_stats.deaths),
            ("assists", parse_optional_int(source.get("assists")), db_stats.assists),
            ("adr", parse_optional_float(source.get("adr")), db_stats.adr),
            ("kast", parse_optional_float(source.get("kast")), db_stats.kast_pct),
            ("fk", parse_optional_int(source.get("fk")), db_stats.first_kills),
            ("fd", parse_optional_int(source.get("fd")), db_stats.first_deaths),
            ("acs", parse_optional_float(source.get("acs")), db_stats.acs),
            ("rating", parse_optional_float(source.get("rating")), db_stats.vlr_rating),
        ]
        clutch_wins, clutch_attempts = clutch_stats_from_advanced(performance, handle)
        comparisons.append(("clutch_wins", clutch_wins, db_stats.clutch_wins))
        comparisons.append(("clutch_attempts", clutch_attempts, db_stats.clutch_attempts))

        for field_name, source_value, db_value in comparisons:
            if _values_match(source_value, db_value):
                continue
            report.discrepancies.append(
                SampleDiscrepancy(
                    match_id=match_id,
                    map_number=map_number,
                    player=handle,
                    field=field_name,
                    source_value=str(source_value),
                    db_value=str(db_value),
                )
            )


def _values_match(source_value: object | None, db_value: object | None) -> bool:
    if source_value is None:
        return True
    if db_value is None:
        return False
    if isinstance(source_value, int | float) and isinstance(db_value, int | float):
        return abs(float(source_value) - float(db_value)) <= _FLOAT_TOLERANCE
    return source_value == db_value
