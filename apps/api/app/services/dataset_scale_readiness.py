from __future__ import annotations

from dataclasses import dataclass, field

from app.parsers.agents import UNKNOWN_AGENT_NAME
from app.services.dataset_audit_service import DatasetAuditReport

NOT_READY = "NOT_READY"
READY_TO_SCALE = "READY_TO_SCALE"

ScaleReadinessStatus = str

_CORE_ROLES = {"Duelist", "Initiator", "Controller", "Sentinel"}

MIN_COMPLETE_MAP_PCT = 70.0
MIN_CIR_ELIGIBLE_MAPS = 80
MAX_UNRESOLVED_SLOT_RATE = 0.15
MAX_UNKNOWN_AGENT_PCT = 5.0
MAX_INVALID_AGENT_VALUES = 0
MAX_MISSING_ROUNDS_PCT = 5.0
MAX_MISSING_ADR_PCT = 20.0
MAX_MISSING_KAST_PCT = 20.0
RECOMMENDED_EVENT_RANGE = "6–10 total events"


@dataclass
class ScaleReadinessReport:
    status: ScaleReadinessStatus
    recommended_next_step: str
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


class DatasetScaleReadinessService:
    """Decide whether the canonical dataset is ready to expand beyond the 2-event pilot."""

    def assess(self, audit: DatasetAuditReport) -> ScaleReadinessReport:
        blockers: list[str] = []
        notes: list[str] = []

        roles = {role for role in audit.observations_by_role if role != UNKNOWN_AGENT_NAME}
        missing_roles = sorted(_CORE_ROLES - roles)
        played = audit.maps_complete + audit.maps_incomplete + audit.maps_empty
        stats_total = audit.player_map_stats or 1
        unknown_agent_pct = 100.0 * audit.unknown_agent_rows / stats_total
        missing_rounds_pct = 100.0 * audit.missing_rounds / stats_total
        missing_adr_pct = 100.0 * audit.missing_adr / stats_total
        missing_kast_pct = 100.0 * audit.missing_kast / stats_total
        expected_slots = played * 10
        unresolved_slot_rate = (
            (expected_slots - audit.player_map_stats) / expected_slots if expected_slots else 1.0
        )
        unresolved_slot_rate = max(0.0, unresolved_slot_rate)
        tiers = {tier for tier in audit.observations_by_tier if tier not in {"Unknown", None}}

        if audit.complete_map_pct < MIN_COMPLETE_MAP_PCT:
            blockers.append(
                f"complete maps are {audit.complete_map_pct:.1f}% "
                f"(need >= {MIN_COMPLETE_MAP_PCT:.0f}%)"
            )
        if audit.maps_eligible_for_cir < MIN_CIR_ELIGIBLE_MAPS:
            blockers.append(
                f"only {audit.maps_eligible_for_cir} CIR-eligible maps "
                f"(need >= {MIN_CIR_ELIGIBLE_MAPS})"
            )
        if unresolved_slot_rate > MAX_UNRESOLVED_SLOT_RATE:
            blockers.append(
                f"unresolved identity slots are {100.0 * unresolved_slot_rate:.1f}% "
                f"(need <= {100.0 * MAX_UNRESOLVED_SLOT_RATE:.0f}%)"
            )
        if missing_roles:
            blockers.append(f"missing core roles: {missing_roles}")
        if len(audit.invalid_agent_values) > MAX_INVALID_AGENT_VALUES:
            blockers.append(f"invalid agent values remain: {sorted(audit.invalid_agent_values)}")
        if unknown_agent_pct > MAX_UNKNOWN_AGENT_PCT:
            blockers.append(
                f"unknown agents on {unknown_agent_pct:.1f}% of rows "
                f"(need <= {MAX_UNKNOWN_AGENT_PCT:.0f}%)"
            )
        if missing_rounds_pct > MAX_MISSING_ROUNDS_PCT:
            blockers.append(f"missing rounds on {missing_rounds_pct:.1f}% of rows")
        if missing_adr_pct > MAX_MISSING_ADR_PCT:
            blockers.append(f"missing ADR on {missing_adr_pct:.1f}% of rows")
        if missing_kast_pct > MAX_MISSING_KAST_PCT:
            blockers.append(f"missing KAST on {missing_kast_pct:.1f}% of rows")
        if "T1" not in tiers or "T2" not in tiers:
            blockers.append(f"tier coverage is {sorted(tiers) or ['none']}; need both T1 and T2")

        notes.append(
            f"complete_maps={audit.maps_complete}/{played or audit.maps} "
            f"({audit.complete_map_pct:.1f}%)"
        )
        notes.append(
            f"cir_eligible_maps={audit.maps_eligible_for_cir} "
            f"cir_eligible_rows={audit.player_map_stats_eligible_for_cir}"
        )
        notes.append(
            f"identity_slots_unresolved={100.0 * unresolved_slot_rate:.1f}% "
            f"ingest_unresolved={audit.unresolved}"
        )
        notes.append(
            f"agents unknown={audit.unknown_agent_rows} invalid={audit.invalid_agent_values}"
        )
        notes.append(
            f"missingness rounds={missing_rounds_pct:.1f}% adr={missing_adr_pct:.1f}% "
            f"kast={missing_kast_pct:.1f}% clutch={100.0 * audit.missing_clutch / stats_total:.1f}%"
        )

        if blockers:
            return ScaleReadinessReport(
                status=NOT_READY,
                recommended_next_step=(
                    "Fix identity/completeness blockers on the current 2-event pilot "
                    "before expanding the dataset."
                ),
                reasons=notes + blockers,
                blockers=blockers,
            )

        return ScaleReadinessReport(
            status=READY_TO_SCALE,
            recommended_next_step=(
                f"Expand to {RECOMMENDED_EVENT_RANGE} across T1 international, "
                "T1 regional, T2 Challengers, and multiple regions. Do not retrain CIR yet "
                "until that expanded dataset is ingested and audited."
            ),
            reasons=notes,
            blockers=[],
        )

    def format_report(self, report: ScaleReadinessReport) -> str:
        lines = [
            f"scale_readiness: {report.status}",
            f"recommended_next_step: {report.recommended_next_step}",
            "reasons:",
        ]
        for reason in report.reasons:
            lines.append(f"  - {reason}")
        return "\n".join(lines)
