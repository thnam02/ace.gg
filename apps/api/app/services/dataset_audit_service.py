from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Event, Match, MatchMap, Player, PlayerMapStats, Team


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
    unresolved_identity_count: int = 0
    context_baseline_coverage: dict[str, int] = field(default_factory=dict)


class DatasetAuditService:
    """Summarize canonical PostgreSQL dataset quality."""

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
                selectinload(PlayerMapStats.match_map)
                .selectinload(MatchMap.match)
                .selectinload(Match.event),
            )
        ).all()

        total = len(stats_rows)
        context_ready = 0
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
                if (
                    event.tier
                    and event.tier != "Unknown"
                    and row.agent
                    and row.match_map
                    and row.match_map.map_name
                ):
                    context_ready += 1

        report.context_baseline_coverage = {
            "eligible_observations": context_ready,
            "total_observations": total,
        }
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
        for key, value in sorted(report.observations_by_role.items()):
            lines.append(f"  {key}: {value}")
        lines.append("observations_by_agent:")
        for key, value in sorted(report.observations_by_agent.items()):
            lines.append(f"  {key}: {value}")
        lines.append("observations_by_map:")
        for key, value in sorted(report.observations_by_map.items()):
            lines.append(f"  {key}: {value}")
        lines.append("observations_by_tier:")
        for key, value in sorted(report.observations_by_tier.items()):
            lines.append(f"  {key}: {value}")
        lines.append("observations_by_event:")
        for key, value in sorted(report.observations_by_event.items()):
            lines.append(f"  {key}: {value}")

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
                f"unresolved_identity_count: {report.unresolved_identity_count}",
                "",
                "context_baseline_coverage:",
                (
                    "  eligible_observations: "
                    f"{report.context_baseline_coverage.get('eligible_observations', 0)}"
                ),
                (
                    "  total_observations: "
                    f"{report.context_baseline_coverage.get('total_observations', 0)}"
                ),
            ]
        )
        return "\n".join(lines)


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{100.0 * count / total:.1f}%"
