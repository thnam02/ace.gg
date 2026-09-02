from __future__ import annotations

from dataclasses import dataclass, field

from app.parsers.agents import UNKNOWN_AGENT_NAME
from app.services.dataset_audit_service import DatasetAuditReport

NOT_READY = "NOT_READY"
READY_TO_TRAIN = "READY_TO_TRAIN"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"

TrainingReadinessStatus = str

_CORE_ROLES = {"Duelist", "Initiator", "Controller", "Sentinel"}

HARD_MIN_COMPLETE_MAP_PCT = 80.0
PREFERRED_MIN_COMPLETE_MAP_PCT = 90.0
HARD_MAX_UNRESOLVED_SLOT_PCT = 5.0
PREFERRED_MAX_UNRESOLVED_SLOT_PCT = 2.0
HARD_MIN_CIR_MAPS = 120
PREFERRED_MIN_CIR_MAPS = 300
MAX_INVALID_AGENT_VALUES = 0
MAX_UNKNOWN_AGENT_PCT = 5.0
MAX_MISSING_ROUNDS_PCT = 5.0
MAX_MISSING_ADR_PCT = 20.0
MAX_MISSING_KAST_PCT = 20.0


@dataclass
class TrainingReadinessReport:
    status: TrainingReadinessStatus
    can_train: bool
    recommended_next_step: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class DatasetTrainingReadinessService:
    """Hard/preferred gates before retraining CIR on a real corpus."""

    def assess(self, audit: DatasetAuditReport) -> TrainingReadinessReport:
        blockers: list[str] = []
        warnings: list[str] = []
        notes: list[str] = []

        roles = {role for role in audit.observations_by_role if role != UNKNOWN_AGENT_NAME}
        missing_roles = sorted(_CORE_ROLES - roles)
        stats_total = audit.player_map_stats or 1
        unknown_agent_pct = 100.0 * audit.unknown_agent_rows / stats_total
        missing_rounds_pct = 100.0 * audit.missing_rounds / stats_total
        missing_adr_pct = 100.0 * audit.missing_adr / stats_total
        missing_kast_pct = 100.0 * audit.missing_kast / stats_total
        tiers = {tier for tier in audit.observations_by_tier if tier not in {"Unknown", None}}

        if audit.complete_map_pct < HARD_MIN_COMPLETE_MAP_PCT:
            blockers.append(
                f"complete maps are {audit.complete_map_pct:.1f}% "
                f"(hard gate >= {HARD_MIN_COMPLETE_MAP_PCT:.0f}%)"
            )
        elif audit.complete_map_pct < PREFERRED_MIN_COMPLETE_MAP_PCT:
            warnings.append(
                f"complete maps are {audit.complete_map_pct:.1f}% "
                f"(preferred >= {PREFERRED_MIN_COMPLETE_MAP_PCT:.0f}%)"
            )

        if audit.unresolved_identity_slots_pct > HARD_MAX_UNRESOLVED_SLOT_PCT:
            blockers.append(
                f"unresolved identity slots are {audit.unresolved_identity_slots_pct:.1f}% "
                f"(hard gate <= {HARD_MAX_UNRESOLVED_SLOT_PCT:.0f}%)"
            )
        elif audit.unresolved_identity_slots_pct > PREFERRED_MAX_UNRESOLVED_SLOT_PCT:
            warnings.append(
                f"unresolved identity slots are {audit.unresolved_identity_slots_pct:.1f}% "
                f"(preferred <= {PREFERRED_MAX_UNRESOLVED_SLOT_PCT:.0f}%)"
            )

        if audit.maps_eligible_for_cir < HARD_MIN_CIR_MAPS:
            blockers.append(
                f"only {audit.maps_eligible_for_cir} CIR-eligible maps "
                f"(hard gate >= {HARD_MIN_CIR_MAPS})"
            )
        elif audit.maps_eligible_for_cir < PREFERRED_MIN_CIR_MAPS:
            warnings.append(
                f"{audit.maps_eligible_for_cir} CIR-eligible maps "
                f"(preferred >= {PREFERRED_MIN_CIR_MAPS})"
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
            warnings.append(
                f"tier coverage is {sorted(tiers) or ['none']}; preferred both T1 and T2"
            )

        notes.append(
            f"complete_maps={audit.maps_complete}/"
            f"{audit.maps_complete + audit.maps_incomplete + audit.maps_empty} "
            f"({audit.complete_map_pct:.1f}%)"
        )
        notes.append(
            f"cir_eligible_maps={audit.maps_eligible_for_cir} "
            f"cir_eligible_rows={audit.player_map_stats_eligible_for_cir}"
        )
        notes.append(f"identity_slots_unresolved={audit.unresolved_identity_slots_pct:.1f}%")
        notes.append(
            f"missingness rounds={missing_rounds_pct:.1f}% adr={missing_adr_pct:.1f}% "
            f"kast={missing_kast_pct:.1f}% clutch={100.0 * audit.missing_clutch / stats_total:.1f}%"
        )

        if blockers:
            return TrainingReadinessReport(
                status=NOT_READY,
                can_train=False,
                recommended_next_step=(
                    "Stop before CIR training. Fix dataset quality blockers first."
                ),
                blockers=blockers,
                warnings=warnings,
                notes=notes,
            )
        if warnings:
            return TrainingReadinessReport(
                status=READY_WITH_WARNINGS,
                can_train=True,
                recommended_next_step=(
                    "Dataset is usable but below preferred gates. Train CIR v0.1 "
                    "and treat results as provisional."
                ),
                blockers=[],
                warnings=warnings,
                notes=notes,
            )
        return TrainingReadinessReport(
            status=READY_TO_TRAIN,
            can_train=True,
            recommended_next_step="Rebuild Team Elo, retrain CIR v0.1, then validate.",
            blockers=[],
            warnings=[],
            notes=notes,
        )

    def format_report(self, report: TrainingReadinessReport) -> str:
        lines = [
            f"training_readiness: {report.status}",
            f"can_train: {report.can_train}",
            f"recommended_next_step: {report.recommended_next_step}",
        ]
        if report.notes:
            lines.append("notes:")
            for note in report.notes:
                lines.append(f"  - {note}")
        if report.warnings:
            lines.append("warnings:")
            for warning in report.warnings:
                lines.append(f"  - {warning}")
        if report.blockers:
            lines.append("blockers:")
            for blocker in report.blockers:
                lines.append(f"  - {blocker}")
        return "\n".join(lines)
