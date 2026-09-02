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
RECOMMENDED_SCALE_EVENTS = [
    "T1 international: next completed VCT Masters or Champions",
    "T1 Americas: next completed VCT Americas stage",
    "T1 EMEA: next completed VCT EMEA stage",
    "T1 Pacific: next completed VCT Pacific stage",
    "T1 China: next completed VCT China stage",
    "T2 Challengers NA: next completed Challengers NA split (beyond ACE Stage 2)",
    "T2 Challengers EMEA: next completed Challengers EMEA split",
    "T2 Challengers Pacific: next completed Challengers Pacific split",
]


@dataclass
class ScaleReadinessReport:
    status: ScaleReadinessStatus
    recommended_next_step: str
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    t2_status: ScaleReadinessStatus = NOT_READY
    t2_blockers: list[str] = field(default_factory=list)
    recommended_events: list[str] = field(default_factory=list)


class DatasetScaleReadinessService:
    """Decide whether the canonical dataset is ready to expand beyond the 2-event pilot."""

    def assess(self, audit: DatasetAuditReport) -> ScaleReadinessReport:
        blockers: list[str] = []
        notes: list[str] = []
        t2_blockers: list[str] = []

        roles = {role for role in audit.observations_by_role if role != UNKNOWN_AGENT_NAME}
        missing_roles = sorted(_CORE_ROLES - roles)
        played = audit.maps_complete + audit.maps_incomplete + audit.maps_empty
        stats_total = audit.player_map_stats or 1
        unknown_agent_pct = 100.0 * audit.unknown_agent_rows / stats_total
        missing_rounds_pct = 100.0 * audit.missing_rounds / stats_total
        missing_adr_pct = 100.0 * audit.missing_adr / stats_total
        missing_kast_pct = 100.0 * audit.missing_kast / stats_total
        unresolved_slot_rate = audit.unresolved_identity_slots_pct / 100.0
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
                f"unresolved identity slots are {audit.unresolved_identity_slots_pct:.1f}% "
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

        if audit.t2_maps_played == 0:
            t2_blockers.append("no T2 maps in the dataset")
        elif audit.t2_complete_map_pct < MIN_COMPLETE_MAP_PCT:
            t2_blockers.append(
                f"T2 complete maps are {audit.t2_complete_map_pct:.1f}% "
                f"(need >= {MIN_COMPLETE_MAP_PCT:.0f}%)"
            )
        if t2_blockers:
            blockers.extend(item for item in t2_blockers if item not in blockers)

        notes.append(
            f"complete_maps={audit.maps_complete}/{played or audit.maps} "
            f"({audit.complete_map_pct:.1f}%)"
        )
        notes.append(
            f"t1_complete_maps={audit.t1_maps_complete}/{audit.t1_maps_played} "
            f"({audit.t1_complete_map_pct:.1f}%)"
        )
        notes.append(
            f"t2_complete_maps={audit.t2_maps_complete}/{audit.t2_maps_played} "
            f"({audit.t2_complete_map_pct:.1f}%)"
        )
        notes.append(
            f"cir_eligible_maps={audit.maps_eligible_for_cir} "
            f"cir_eligible_rows={audit.player_map_stats_eligible_for_cir}"
        )
        notes.append(
            f"identity_slots_unresolved={audit.unresolved_identity_slots_pct:.1f}% "
            f"ingest_unresolved={audit.unresolved}"
        )
        notes.append(
            f"agents unknown={audit.unknown_agent_rows} invalid={audit.invalid_agent_values}"
        )
        notes.append(
            f"missingness rounds={missing_rounds_pct:.1f}% adr={missing_adr_pct:.1f}% "
            f"kast={missing_kast_pct:.1f}% clutch={100.0 * audit.missing_clutch / stats_total:.1f}%"
        )

        t2_status = READY_TO_SCALE if not t2_blockers else NOT_READY
        if blockers:
            next_step = (
                "Fix identity/completeness blockers on the current 2-event pilot "
                "before expanding the dataset."
            )
            if t2_blockers and audit.complete_map_pct >= MIN_COMPLETE_MAP_PCT:
                next_step = (
                    "Overall completeness passed but T2 remains below the readiness gate. "
                    "Recover remaining Challengers identities before scaling."
                )
            return ScaleReadinessReport(
                status=NOT_READY,
                recommended_next_step=next_step,
                reasons=notes + blockers,
                blockers=blockers,
                t2_status=t2_status,
                t2_blockers=t2_blockers,
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
            t2_status=t2_status,
            t2_blockers=[],
            recommended_events=list(RECOMMENDED_SCALE_EVENTS),
        )

    def format_report(self, report: ScaleReadinessReport) -> str:
        lines = [
            f"scale_readiness: {report.status}",
            f"t2_readiness: {report.t2_status}",
            f"recommended_next_step: {report.recommended_next_step}",
            "reasons:",
        ]
        for reason in report.reasons:
            lines.append(f"  - {reason}")
        if report.t2_blockers:
            lines.append("t2_blockers:")
            for blocker in report.t2_blockers:
                lines.append(f"  - {blocker}")
        if report.recommended_events:
            lines.append("recommended_events:")
            for event in report.recommended_events:
                lines.append(f"  - {event}")
        return "\n".join(lines)
