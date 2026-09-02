from __future__ import annotations

from app.metrics.cir_feature_diagnostics import relative_rmse_delta, within_rmse_slack
from app.metrics.cir_feature_pruning_config import SELECTION_RMSE_RELATIVE_SLACK
from app.metrics.mir.mir_config import MATERIAL_ROLE_GAP_DELTA, MATERIAL_SPEARMAN_DELTA
from app.schemas.mir_experiment import MirSubsetResult


def evidence_gate(
    combat: MirSubsetResult,
    candidate: MirSubsetResult,
    *,
    extra_features: tuple[str, ...],
    t1_coefficients: dict[str, float | None] | None = None,
    t2_coefficients: dict[str, float | None] | None = None,
    stability_spearman_delta: float | None = None,
) -> tuple[bool, list[str]]:
    """Return (passes, evidence). Test metrics are ignored."""
    reasons: list[str] = []
    combat_rmse = combat.validation_metrics.rmse
    cand_rmse = candidate.validation_metrics.rmse
    delta = relative_rmse_delta(combat_rmse, cand_rmse)
    if delta is None:
        return False, ["Missing validation RMSE."]
    rmse_ok = delta < -SELECTION_RMSE_RELATIVE_SLACK
    similar = within_rmse_slack(cand_rmse, combat_rmse)
    reasons.append(f"validation RMSE relative change={delta:+.4%}")

    combat_r2 = combat.validation_metrics.r2
    cand_r2 = candidate.validation_metrics.r2
    r2_ok = True
    if combat_r2 is not None and cand_r2 is not None:
        r2_ok = cand_r2 >= combat_r2 - 1e-4
        reasons.append(f"validation R² {cand_r2:.4f} vs combat {combat_r2:.4f}")

    combat_rho = combat.validation_metrics.spearman
    cand_rho = candidate.validation_metrics.spearman
    spearman_ok = True
    if combat_rho is not None and cand_rho is not None:
        spearman_ok = cand_rho >= combat_rho - MATERIAL_SPEARMAN_DELTA
        reasons.append(f"validation Spearman {cand_rho:.4f} vs combat {combat_rho:.4f}")

    combat_gap = combat.role_bias_metrics.max_role_median_gap
    cand_gap = candidate.role_bias_metrics.max_role_median_gap
    gap_ok = True
    if combat_gap is not None and cand_gap is not None:
        gap_ok = cand_gap - combat_gap < MATERIAL_ROLE_GAP_DELTA
        reasons.append(f"role median gap {cand_gap:.2f} vs combat {combat_gap:.2f}")

    sign_ok = True
    for name in extra_features:
        coef = candidate.coefficients.get(name)
        if coef is None:
            continue
        reasons.append(f"{name} coefficient={coef:+.4f}")
        t1 = (t1_coefficients or {}).get(name)
        t2 = (t2_coefficients or {}).get(name)
        if t1 is not None and t2 is not None and t1 * t2 < 0:
            sign_ok = False
            reasons.append(f"{name} T1/T2 coefficient signs disagree ({t1:+.3f} vs {t2:+.3f})")

    stability_ok = True
    if stability_spearman_delta is not None and stability_spearman_delta < -MATERIAL_SPEARMAN_DELTA:
        stability_ok = False
        reasons.append(f"stability Spearman delta={stability_spearman_delta:+.3f}")

    role_or_spearman_gain = False
    if combat_gap is not None and cand_gap is not None:
        role_or_spearman_gain = combat_gap - cand_gap >= MATERIAL_ROLE_GAP_DELTA
    if combat_rho is not None and cand_rho is not None:
        role_or_spearman_gain = role_or_spearman_gain or (
            cand_rho - combat_rho >= MATERIAL_SPEARMAN_DELTA
        )
    meaningful = rmse_ok or (similar and role_or_spearman_gain)
    passes = bool(meaningful and r2_ok and spearman_ok and gap_ok and sign_ok and stability_ok)
    if not meaningful:
        reasons.append("Improvement is inside the 1% RMSE simplicity band without material extras.")
    return passes, reasons


def classify_signal(
    *,
    unique_vs_combat_delta: float | None,
    unique_vs_raw_delta: float | None,
    unique_coef: float | None,
    gate_passed: bool,
    role_specific: bool,
    harmful_rmse: bool,
    insufficient: bool = False,
) -> str:
    if insufficient:
        return "INSUFFICIENT_DATA"
    if harmful_rmse or (unique_vs_combat_delta is not None and unique_vs_combat_delta > 0.002):
        return "HARMFUL"
    if gate_passed and unique_vs_raw_delta is not None and unique_vs_raw_delta < 0:
        return "UNIQUE_VALUE_CONFIRMED"
    if role_specific:
        return "ROLE_SPECIFIC_ONLY"
    _ = unique_coef
    return "REDUNDANT_WITH_COMBAT"


def select_mir_subset(results: list[MirSubsetResult]) -> MirSubsetResult:
    """Pick a winner from validation RMSE only. Test metrics are ignored."""
    if not results:
        raise ValueError("No MIR subsets to select from")
    ranked = sorted(
        results,
        key=lambda result: (
            result.validation_metrics.rmse
            if result.validation_metrics.rmse is not None
            else float("inf"),
            -(result.validation_metrics.r2 if result.validation_metrics.r2 is not None else -999.0),
            -(
                result.validation_metrics.spearman
                if result.validation_metrics.spearman is not None
                else -999.0
            ),
        ),
    )
    best = ranked[0]
    similar = [
        result
        for result in ranked
        if within_rmse_slack(result.validation_metrics.rmse, best.validation_metrics.rmse)
    ]
    simplest = min(similar, key=lambda result: result.number_of_features)
    if simplest.number_of_features < best.number_of_features:
        gap_gain = False
        simple_gap = simplest.role_bias_metrics.max_role_median_gap
        best_gap = best.role_bias_metrics.max_role_median_gap
        if simple_gap is not None and best_gap is not None:
            gap_gain = simple_gap - best_gap >= MATERIAL_ROLE_GAP_DELTA
        rho_gain = False
        simple_rho = simplest.validation_metrics.spearman
        best_rho = best.validation_metrics.spearman
        if simple_rho is not None and best_rho is not None:
            rho_gain = best_rho - simple_rho >= MATERIAL_SPEARMAN_DELTA
        if not (gap_gain or rho_gain):
            return simplest
    return best


def select_mir_decision(
    selected_name: str,
    *,
    support_enabled: bool,
    opening_enabled: bool,
    economy_enabled: bool,
) -> str:
    if economy_enabled and selected_name in {"combat_plus_economy_unique", "full_mir_candidate"}:
        if not support_enabled and not opening_enabled:
            return "MIR_ECONOMY_ADDS_VALUE"
    if support_enabled and opening_enabled:
        return "MIR_MULTI_COMPONENT"
    if support_enabled:
        return "MIR_SUPPORT_ADDS_VALUE"
    if opening_enabled:
        return "MIR_OPENING_ADDS_VALUE"
    if economy_enabled:
        return "MIR_ECONOMY_ADDS_VALUE"
    return "COMBAT_ONLY_REMAINS_BEST"


def mir_readiness(decision: str, rmse_delta: float | None) -> str:
    if decision == "COMBAT_ONLY_REMAINS_BEST":
        return "NOT_READY"
    if rmse_delta is not None and rmse_delta <= -SELECTION_RMSE_RELATIVE_SLACK:
        return "READY_FOR_FINAL_VALIDATION"
    return "NOT_READY"
