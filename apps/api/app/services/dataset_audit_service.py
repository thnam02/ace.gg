from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.metrics.context_baselines import (
    BASELINE_HIERARCHY,
    BaselineThresholds,
    ContextObservation,
    build_baseline_registry,
    select_baseline_level,
)
from app.models import Event, Match, MatchMap, Player, PlayerMapStats, Team
from app.services.context_baseline_service import observation_from_player_map_stats


@dataclass
class DatasetAuditReport:
    players: int = 0
    teams: int = 0
    events: int = 0
    matches: int = 0
    maps: int = 0
    player_map_stats: int = 0
    total_rounds: int = 0
    observations_by_role: dict[str, int] = field(default_factory=dict)
    observations_by_agent: dict[str, int] = field(default_factory=dict)
    observations_by_map: dict[str, int] = field(default_factory=dict)
    observations_by_tier: dict[str, int] = field(default_factory=dict)
    observations_by_event: dict[str, int] = field(default_factory=dict)
    missing_rounds: int = 0
    missing_adr: int = 0
    missing_kast: int = 0
    missing_opening: int = 0
    missing_clutch: int = 0
    missing_player_ids: int = 0
    unresolved_identity_count: int = 0
    context_baseline_coverage: dict[str, int] = field(default_factory=dict)
    eligible_players_by_rounds: dict[int, int] = field(default_factory=dict)
    rounds_per_player: dict[str, int] = field(default_factory=dict)


class DatasetAuditService:
    """Summarize canonical PostgreSQL dataset quality."""

    ROUND_THRESHOLDS: tuple[int, ...] = (100, 250, 500, 1000)

    def audit(self, session: Session) -> DatasetAuditReport:
        report = DatasetAuditReport(
            players=int(session.scalar(select(func.count()).select_from(Player)) or 0),
            teams=int(session.scalar(select(func.count()).select_from(Team)) or 0),
            events=int(session.scalar(select(func.count()).select_from(Event)) or 0),
            matches=int(session.scalar(select(func.count()).select_from(Match)) or 0),
            maps=int(session.scalar(select(func.count()).select_from(MatchMap)) or 0),
            player_map_stats=int(
                session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0
            ),
            total_rounds=int(
                session.scalar(select(func.coalesce(func.sum(PlayerMapStats.rounds), 0))) or 0
            ),
        )

        stats_rows = session.scalars(
            select(PlayerMapStats)
            .options(
                selectinload(PlayerMapStats.agent),
                selectinload(PlayerMapStats.player),
                selectinload(PlayerMapStats.match_map)
                .selectinload(MatchMap.match)
                .selectinload(Match.event),
            )
        ).all()

        observations: list[ContextObservation] = []
        player_rounds: dict[str, int] = {}
        for row in stats_rows:
            role = row.agent.role if row.agent else "Unknown"
            agent_name = row.agent.name if row.agent else "Unknown"
            map_name = row.match_map.map_name if row.match_map else "Unknown"
            report.observations_by_role[role] = report.observations_by_role.get(role, 0) + 1
            report.observations_by_agent[agent_name] = (
                report.observations_by_agent.get(agent_name, 0) + 1
            )
            report.observations_by_map[map_name] = report.observations_by_map.get(map_name, 0) + 1

            if row.rounds <= 0:
                report.missing_rounds += 1
            if row.adr is None:
                report.missing_adr += 1
            if row.kast_pct is None:
                report.missing_kast += 1
            if row.first_kills == 0 and row.first_deaths == 0:
                report.missing_opening += 1
            if row.clutch_attempts is None:
                report.missing_clutch += 1
            if row.player is None or row.player.vlr_player_id is None:
                report.missing_player_ids += 1

            event = (
                row.match_map.match.event
                if row.match_map and row.match_map.match
                else None
            )
            if event is not None:
                tier = event.tier or "Unknown"
                report.observations_by_tier[tier] = report.observations_by_tier.get(tier, 0) + 1
                report.observations_by_event[event.name] = (
                    report.observations_by_event.get(event.name, 0) + 1
                )

            handle = row.player.handle if row.player else str(row.player_id)
            player_rounds[handle] = player_rounds.get(handle, 0) + row.rounds
            observations.append(observation_from_player_map_stats(row))

        report.rounds_per_player = player_rounds
        for threshold in self.ROUND_THRESHOLDS:
            report.eligible_players_by_rounds[threshold] = sum(
                1 for total in player_rounds.values() if total >= threshold
            )

        report.context_baseline_coverage = _context_coverage(observations)
        return report

    def format_report(self, report: DatasetAuditReport) -> str:
        lines = [
            f"players: {report.players}",
            f"teams: {report.teams}",
            f"events: {report.events}",
            f"matches: {report.matches}",
            f"maps: {report.maps}",
            f"player_map_stats: {report.player_map_stats}",
            f"total_rounds: {report.total_rounds}",
            "",
            "observations_by_role:",
        ]
        _append_counts(lines, report.observations_by_role)
        lines.append("observations_by_agent:")
        _append_counts(lines, report.observations_by_agent)
        lines.append("observations_by_map:")
        _append_counts(lines, report.observations_by_map)
        lines.append("observations_by_tier:")
        _append_counts(lines, report.observations_by_tier)
        lines.append("observations_by_event:")
        _append_counts(lines, report.observations_by_event)

        total = report.player_map_stats or 1
        lines.extend(
            [
                "",
                f"missing_rounds: {report.missing_rounds} ({_pct(report.missing_rounds, total)})",
                f"missing_adr: {report.missing_adr} ({_pct(report.missing_adr, total)})",
                f"missing_kast: {report.missing_kast} ({_pct(report.missing_kast, total)})",
                (
                    f"missing_opening: {report.missing_opening} "
                    f"({_pct(report.missing_opening, total)})"
                ),
                f"missing_clutch: {report.missing_clutch} ({_pct(report.missing_clutch, total)})",
                (
                    f"missing_player_ids: {report.missing_player_ids} "
                    f"({_pct(report.missing_player_ids, total)})"
                ),
                f"unresolved_identity_count: {report.unresolved_identity_count}",
                "",
                "context_baseline_coverage:",
            ]
        )
        coverage_total = report.context_baseline_coverage.get("total_observations", 0) or 1
        for key in (
            "agent_map_tier",
            "role_map_tier",
            "role_tier",
            "tier",
            "global",
            "total_observations",
        ):
            value = report.context_baseline_coverage.get(key, 0)
            if key == "total_observations":
                lines.append(f"  {key}: {value}")
            else:
                lines.append(f"  {key}: {value} ({_pct(value, coverage_total)})")

        lines.append("eligible_players_by_rounds:")
        for threshold in self.ROUND_THRESHOLDS:
            count = report.eligible_players_by_rounds.get(threshold, 0)
            denom = report.players or 1
            lines.append(f"  {threshold}: {count} ({_pct(count, denom)})")
        return "\n".join(lines)


def _context_coverage(observations: list[ContextObservation]) -> dict[str, int]:
    coverage = {level.value: 0 for level in BASELINE_HIERARCHY}
    coverage["total_observations"] = len(observations)
    if not observations:
        return coverage

    registry = build_baseline_registry(observations)
    thresholds = BaselineThresholds()
    for observation in observations:
        level, _ = select_baseline_level(registry, observation, thresholds)
        coverage[level.value] = coverage.get(level.value, 0) + 1
    return coverage


def _append_counts(lines: list[str], counts: dict[str, int]) -> None:
    if not counts:
        return
    for key, value in sorted(counts.items()):
        lines.append(f"  {key}: {value}")


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{100.0 * count / total:.1f}%"
