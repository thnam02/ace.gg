from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Match, MatchMap, Player, PlayerMapStats, Team
from app.services.map_completeness import EXPECTED_PLAYERS_PER_MAP


@dataclass
class IntegrityWarning:
    code: str
    message: str
    entity: str
    entity_id: str


@dataclass
class DatasetIntegrityReport:
    warnings: list[IntegrityWarning] = field(default_factory=list)

    def counts_by_code(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for warning in self.warnings:
            counts[warning.code] = counts.get(warning.code, 0) + 1
        return counts


class DatasetIntegrityService:
    """Warn about suspicious canonical data without rewriting source values."""

    def check(self, session: Session) -> DatasetIntegrityReport:
        report = DatasetIntegrityReport()
        self._check_duplicate_vlr_ids(session, report)
        self._check_duplicate_player_map_stats(session, report)
        self._check_maps_and_matches(session, report)
        self._check_stat_values(session, report)
        return report

    def format_report(self, report: DatasetIntegrityReport) -> str:
        counts = report.counts_by_code()
        lines = [
            f"integrity_warning_count: {len(report.warnings)}",
            "integrity_warning_counts:",
        ]
        if not counts:
            lines.append("  none")
        else:
            for code, count in sorted(counts.items()):
                lines.append(f"  {code}: {count}")
        if report.warnings:
            lines.append("integrity_warnings:")
            for warning in report.warnings[:200]:
                lines.append(
                    f"  [{warning.code}] {warning.entity}={warning.entity_id}: {warning.message}"
                )
            remaining = len(report.warnings) - 200
            if remaining > 0:
                lines.append(f"  ... {remaining} more")
        return "\n".join(lines)

    def _warn(
        self,
        report: DatasetIntegrityReport,
        *,
        code: str,
        message: str,
        entity: str,
        entity_id: str,
    ) -> None:
        report.warnings.append(
            IntegrityWarning(code=code, message=message, entity=entity, entity_id=entity_id)
        )

    def _check_duplicate_vlr_ids(self, session: Session, report: DatasetIntegrityReport) -> None:
        for model, field_name, code in (
            (Match, Match.vlr_match_id, "duplicate_vlr_match_id"),
            (Player, Player.vlr_player_id, "duplicate_vlr_player_id"),
            (Team, Team.vlr_team_id, "duplicate_vlr_team_id"),
        ):
            rows = session.execute(
                select(field_name, func.count())
                .select_from(model)
                .group_by(field_name)
                .having(func.count() > 1)
            ).all()
            for vlr_id, count in rows:
                self._warn(
                    report,
                    code=code,
                    message=f"VLR ID {vlr_id} appears {count} times",
                    entity=model.__tablename__,
                    entity_id=str(vlr_id),
                )

    def _check_duplicate_player_map_stats(
        self,
        session: Session,
        report: DatasetIntegrityReport,
    ) -> None:
        rows = session.execute(
            select(
                PlayerMapStats.match_map_id,
                PlayerMapStats.player_id,
                func.count(),
            )
            .group_by(PlayerMapStats.match_map_id, PlayerMapStats.player_id)
            .having(func.count() > 1)
        ).all()
        for match_map_id, player_id, count in rows:
            self._warn(
                report,
                code="duplicate_match_map_player",
                message=f"pair appears {count} times",
                entity="player_map_stats",
                entity_id=f"{match_map_id}:{player_id}",
            )

    def _check_maps_and_matches(self, session: Session, report: DatasetIntegrityReport) -> None:
        matches = session.scalars(
            select(Match).options(
                selectinload(Match.maps)
                .selectinload(MatchMap.player_stats)
                .selectinload(PlayerMapStats.team),
                selectinload(Match.maps)
                .selectinload(MatchMap.player_stats)
                .selectinload(PlayerMapStats.player),
                selectinload(Match.team_a),
                selectinload(Match.team_b),
                selectinload(Match.winner_team),
            )
        ).all()
        for match in matches:
            map_wins: Counter[object] = Counter()
            for match_map in match.maps:
                self._check_map_player_count(report, match, match_map)
                self._check_map_teams_and_rounds(report, match, match_map)
                if match_map.winner_team_id is not None:
                    map_wins[match_map.winner_team_id] += 1

            played_maps = [
                match_map
                for match_map in match.maps
                if match_map.team_a_score is not None and match_map.team_b_score is not None
            ]
            if not played_maps:
                continue
            team_a_maps = map_wins.get(match.team_a_id, 0)
            team_b_maps = map_wins.get(match.team_b_id, 0)
            implied_winner: object | None = None
            if team_a_maps > team_b_maps:
                implied_winner = match.team_a_id
            elif team_b_maps > team_a_maps:
                implied_winner = match.team_b_id
            if implied_winner is not None and match.winner_team_id != implied_winner:
                self._warn(
                    report,
                    code="match_winner_mismatch",
                    message=(
                        f"winner_team_id={match.winner_team_id} but map wins "
                        f"{team_a_maps}-{team_b_maps}"
                    ),
                    entity="match",
                    entity_id=str(match.vlr_match_id),
                )

    def _check_map_player_count(
        self,
        report: DatasetIntegrityReport,
        match: Match,
        match_map: MatchMap,
    ) -> None:
        played = match_map.team_a_score is not None and match_map.team_b_score is not None
        if not played:
            return
        count = len(match_map.player_stats)
        if count != EXPECTED_PLAYERS_PER_MAP:
            self._warn(
                report,
                code="unexpected_player_stat_count",
                message=(
                    f"map {match_map.map_number} {match_map.map_name} has {count} "
                    f"player stat rows (expected {EXPECTED_PLAYERS_PER_MAP})"
                ),
                entity="match_map",
                entity_id=f"{match.vlr_match_id}:{match_map.map_number}",
            )

    def _check_map_teams_and_rounds(
        self,
        report: DatasetIntegrityReport,
        match: Match,
        match_map: MatchMap,
    ) -> None:
        expected_rounds = None
        if match_map.team_a_score is not None and match_map.team_b_score is not None:
            expected_rounds = match_map.team_a_score + match_map.team_b_score
            if match_map.rounds_played is not None and match_map.rounds_played != expected_rounds:
                self._warn(
                    report,
                    code="map_rounds_mismatch",
                    message=(
                        f"rounds_played={match_map.rounds_played} != "
                        f"{match_map.team_a_score}+{match_map.team_b_score}"
                    ),
                    entity="match_map",
                    entity_id=f"{match.vlr_match_id}:{match_map.map_number}",
                )

        allowed_team_ids = {match.team_a_id, match.team_b_id}
        for stats in match_map.player_stats:
            if stats.team_id not in allowed_team_ids:
                self._warn(
                    report,
                    code="player_team_mismatch",
                    message=(
                        f"player {stats.player.handle} team_id={stats.team_id} "
                        "is not a match participant"
                    ),
                    entity="player_map_stats",
                    entity_id=str(stats.id),
                )
            if expected_rounds is not None and stats.rounds != expected_rounds:
                self._warn(
                    report,
                    code="player_rounds_mismatch",
                    message=(
                        f"player {stats.player.handle} rounds={stats.rounds} "
                        f"!= map score sum {expected_rounds}"
                    ),
                    entity="player_map_stats",
                    entity_id=str(stats.id),
                )

    def _check_stat_values(self, session: Session, report: DatasetIntegrityReport) -> None:
        rows = session.scalars(
            select(PlayerMapStats).options(selectinload(PlayerMapStats.player))
        ).all()
        for stats in rows:
            handle = stats.player.handle if stats.player else str(stats.player_id)
            entity_id = str(stats.id)
            if stats.kills < 0 or stats.deaths < 0 or stats.assists < 0:
                self._warn(
                    report,
                    code="negative_combat_stat",
                    message=(
                        f"{handle} has negative K/D/A {stats.kills}/{stats.deaths}/{stats.assists}"
                    ),
                    entity="player_map_stats",
                    entity_id=entity_id,
                )
            if stats.kast_pct is not None and not 0 <= stats.kast_pct <= 100:
                self._warn(
                    report,
                    code="kast_out_of_range",
                    message=f"{handle} kast_pct={stats.kast_pct}",
                    entity="player_map_stats",
                    entity_id=entity_id,
                )
            if stats.adr is not None and stats.adr < 0:
                self._warn(
                    report,
                    code="negative_adr",
                    message=f"{handle} adr={stats.adr}",
                    entity="player_map_stats",
                    entity_id=entity_id,
                )
            if (
                stats.clutch_wins is not None
                and stats.clutch_attempts is not None
                and stats.clutch_wins > stats.clutch_attempts
            ):
                self._warn(
                    report,
                    code="clutch_wins_gt_attempts",
                    message=(
                        f"{handle} clutch_wins={stats.clutch_wins} > "
                        f"clutch_attempts={stats.clutch_attempts}"
                    ),
                    entity="player_map_stats",
                    entity_id=entity_id,
                )
            if stats.first_kills > stats.rounds:
                self._warn(
                    report,
                    code="first_kills_gt_rounds",
                    message=f"{handle} first_kills={stats.first_kills} > rounds={stats.rounds}",
                    entity="player_map_stats",
                    entity_id=entity_id,
                )
            if stats.first_deaths > stats.rounds:
                self._warn(
                    report,
                    code="first_deaths_gt_rounds",
                    message=(f"{handle} first_deaths={stats.first_deaths} > rounds={stats.rounds}"),
                    entity="player_map_stats",
                    entity_id=entity_id,
                )
