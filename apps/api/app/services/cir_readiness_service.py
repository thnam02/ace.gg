from __future__ import annotations

from dataclasses import dataclass, field

from app.metrics.context_baselines import BaselineLevel
from app.services.dataset_audit_service import DatasetAuditReport

CIRReadinessStatus = str

NOT_READY = "NOT_READY"
PARTIALLY_READY = "PARTIALLY_READY"
READY_FOR_PILOT_CIR = "READY_FOR_PILOT_CIR"

_CORE_ROLES = {"Duelist", "Initiator", "Controller", "Sentinel"}


@dataclass
class CirReadinessReport:
    status: CIRReadinessStatus
    reasons: list[str] = field(default_factory=list)


class CirReadinessService:
    """Judge whether a dataset is suitable for a CIR v0.1 pilot. Does not train."""

    def assess(self, audit: DatasetAuditReport) -> CirReadinessReport:
        reasons: list[str] = []
        blockers: list[str] = []
        partial: list[str] = []

        roles = {role for role in audit.observations_by_role if role != "Unknown"}
        agents = {name for name in audit.observations_by_agent if name != "Unknown"}
        maps = {name for name in audit.observations_by_map if name != "Unknown"}
        tiers = {tier for tier in audit.observations_by_tier if tier not in {"Unknown", None}}
        total = audit.player_map_stats or 1
        missing_rounds_pct = 100.0 * audit.missing_rounds / total
        missing_adr_pct = 100.0 * audit.missing_adr / total
        missing_kast_pct = 100.0 * audit.missing_kast / total
        missing_clutch_pct = 100.0 * audit.missing_clutch / total
        coverage = audit.context_baseline_coverage
        coverage_total = coverage.get("total_observations", 0) or 1
        agent_map_count = coverage.get(BaselineLevel.AGENT_MAP_TIER.value, 0)
        agent_map_tier_pct = 100.0 * agent_map_count / coverage_total
        global_pct = 100.0 * coverage.get(BaselineLevel.GLOBAL.value, 0) / coverage_total
        players_100 = audit.eligible_players_by_rounds.get(100, 0)
        players_250 = audit.eligible_players_by_rounds.get(250, 0)
        players_500 = audit.eligible_players_by_rounds.get(500, 0)

        if audit.player_map_stats < 200:
            blockers.append(
                f"only {audit.player_map_stats} PlayerMapStats rows (need >= 200 for a CIR pilot)"
            )
        if "T1" not in tiers or "T2" not in tiers:
            blockers.append(f"tier coverage is {sorted(tiers) or ['none']}; need both T1 and T2")
        if missing_rounds_pct > 5:
            blockers.append(f"missing/zero rounds on {missing_rounds_pct:.1f}% of rows")
        if len(_CORE_ROLES - roles) > 1:
            blockers.append(f"role coverage is {sorted(roles)}; need the four core roles")

        if len(agents) < 10:
            partial.append(f"only {len(agents)} agents observed")
        if len(maps) < 5:
            partial.append(f"only {len(maps)} maps observed")
        if missing_adr_pct > 15 or missing_kast_pct > 15:
            partial.append(
                f"missing ADR {missing_adr_pct:.1f}% / KAST {missing_kast_pct:.1f}%"
            )
        if missing_clutch_pct > 50:
            partial.append(
                f"clutch unavailable on {missing_clutch_pct:.1f}% of rows; "
                "clutch CIR terms will be sparse"
            )
        if agent_map_tier_pct < 20:
            partial.append(
                f"agent_map_tier baselines cover {agent_map_tier_pct:.1f}% of observations"
            )
        if global_pct > 40:
            partial.append(f"{global_pct:.1f}% of observations fall back to global baselines")
        if players_250 < 8:
            partial.append(
                f"only {players_250} players have >= 250 rounds "
                f"({players_100} at 100, {players_500} at 500)"
            )
        if audit.events < 4:
            partial.append(
                f"only {audit.events} events; CIR will be event-specific until the dataset grows"
            )

        reasons.append(
            f"roles={len(roles)} agents={len(agents)} maps={len(maps)} tiers={sorted(tiers)}"
        )
        reasons.append(
            f"eligible players: 100={players_100} 250={players_250} "
            f"500={players_500} 1000={audit.eligible_players_by_rounds.get(1000, 0)}"
        )
        reasons.extend(blockers)
        reasons.extend(partial)

        if blockers:
            status = NOT_READY
        elif partial:
            status = PARTIALLY_READY
        else:
            status = READY_FOR_PILOT_CIR
        return CirReadinessReport(status=status, reasons=reasons)

    def format_report(self, report: CirReadinessReport) -> str:
        lines = [f"cir_readiness: {report.status}", "reasons:"]
        for reason in report.reasons:
            lines.append(f"  - {reason}")
        return "\n".join(lines)
