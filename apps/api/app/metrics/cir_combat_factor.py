from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.metrics.cir_combat_factor_config import (
    CONSTRAINED_REGRESSION_FALLBACK,
    EQUAL_WEIGHT,
    INTERPRETATIONS,
    KPR_ONLY,
    MATERIAL_ROLE_GAP_IMPROVEMENT,
    NEGATIVE_DPR_ONLY,
    NET_COMBAT_RATE,
    PC1_DOMINANCE_THRESHOLD,
    PCA_COMBAT_FACTOR,
    RANKING_STABILITY_500_MIN,
    RMSE_SLACK,
    ROLE_GAP_FAILURE_THRESHOLD,
    ROLE_GAP_VS_TWO_FEATURE_SLACK,
    SELECTION_BY_KIND,
    SELECTION_KEEP_TWO,
    SELECTION_RETHINK,
    SIGN_FLIP_FAILURE_RATE,
    SIMPLICITY_RANK,
    TWO_FEATURE,
)
from app.metrics.cir_final_validation import relative_rmse_increase
from app.metrics.cir_final_validation_config import CIR_V02_RECOMMENDED_VERSION


@dataclass(frozen=True)
class CombatPCA:
    kpr_loading_pc1: float
    ndpr_loading_pc1: float
    kpr_loading_pc2: float
    ndpr_loading_pc2: float
    explained_pc1: float
    explained_pc2: float
    oriented: bool
    mean_kpr: float = 0.0
    mean_ndpr: float = 0.0


@dataclass(frozen=True)
class CombatCandidateSnapshot:
    kind: str
    val_rmse: float | None
    role_gap: float | None
    bootstrap_p025: float | None
    bootstrap_sign_flips: int
    bootstrap_draws: int
    ranking_spearman_250: float | None
    ranking_spearman_500: float | None
    coefficient_positive: bool
    temporal_collapse: bool
    tier_sign_stable: bool
    baseline_advantage: bool


def net_combat_rate(
    kpr_residual: float | None,
    negative_dpr_residual: float | None,
) -> float | None:
    """KPR residual plus already-negated DPR residual. Do not subtract twice."""
    if kpr_residual is None or negative_dpr_residual is None:
        return None
    return float(kpr_residual) + float(negative_dpr_residual)


def equal_weight_combat(z_kpr: float, z_negative_dpr: float) -> float:
    return 0.5 * float(z_kpr) + 0.5 * float(z_negative_dpr)


def orient_loadings(loadings: NDArray[np.float64]) -> tuple[NDArray[np.float64], bool]:
    """Flip so higher KPR and higher -DPR (lower DPR) raise the factor."""
    oriented = np.array(loadings, dtype=np.float64, copy=True)
    flipped = False
    if float(np.sum(oriented)) < 0.0:
        oriented *= -1.0
        flipped = True
    return oriented, flipped


def _default_pca() -> CombatPCA:
    unit = 1.0 / np.sqrt(2)
    return CombatPCA(unit, unit, unit, -unit, 1.0, 0.0, False)


def fit_combat_pca(standardized_train: NDArray[np.float64]) -> CombatPCA:
    if standardized_train.size == 0 or standardized_train.shape[0] < 1:
        return _default_pca()
    matrix = np.asarray(standardized_train, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != 2:
        raise ValueError("Combat PCA expects an (n, 2) standardized matrix")
    mean = np.mean(matrix, axis=0)
    centered = matrix - mean
    _u, singular, vt = np.linalg.svd(centered, full_matrices=False)
    energy = singular**2
    total = float(np.sum(energy))
    explained = energy / total if total > 0 else np.array([1.0, 0.0])
    pc1, flipped = orient_loadings(vt[0])
    pc2 = vt[1] if len(vt) > 1 else np.array([1.0 / np.sqrt(2), -1.0 / np.sqrt(2)])
    if flipped:
        pc2 = -pc2
    explained_pc1 = float(explained[0]) if len(explained) else 1.0
    explained_pc2 = float(explained[1]) if len(explained) > 1 else 0.0
    return CombatPCA(
        kpr_loading_pc1=float(pc1[0]),
        ndpr_loading_pc1=float(pc1[1]),
        kpr_loading_pc2=float(pc2[0]),
        ndpr_loading_pc2=float(pc2[1]),
        explained_pc1=explained_pc1,
        explained_pc2=explained_pc2,
        oriented=flipped,
        mean_kpr=float(mean[0]),
        mean_ndpr=float(mean[1]),
    )


def transform_combat_pca(
    standardized: NDArray[np.float64],
    pca: CombatPCA,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    matrix = np.asarray(standardized, dtype=np.float64)
    if matrix.size == 0:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty
    centered = matrix - np.array([pca.mean_kpr, pca.mean_ndpr], dtype=np.float64)
    pc1 = np.array([pca.kpr_loading_pc1, pca.ndpr_loading_pc1], dtype=np.float64)
    pc2 = np.array([pca.kpr_loading_pc2, pca.ndpr_loading_pc2], dtype=np.float64)
    return centered @ pc1, centered @ pc2


def pc1_captures_shared_combat(
    explained_pc1: float, threshold: float = PC1_DOMINANCE_THRESHOLD
) -> bool:
    return explained_pc1 >= threshold


def pc2_adds_validation_value(
    pc1_rmse: float | None,
    pc1_pc2_rmse: float | None,
    slack: float = RMSE_SLACK,
) -> bool:
    if pc1_rmse is None or pc1_pc2_rmse is None or pc1_rmse == 0:
        return False
    return (pc1_rmse - pc1_pc2_rmse) / pc1_rmse >= slack


def competitive_rmse(
    candidate_rmse: float | None,
    reference_rmse: float | None,
    slack: float = RMSE_SLACK,
) -> bool:
    if candidate_rmse is None or reference_rmse is None:
        return False
    increase = relative_rmse_increase(reference_rmse, candidate_rmse)
    return increase is not None and increase <= slack


def bootstrap_coefficient_stable(
    p025: float | None,
    sign_flips: int,
    draws: int,
    rate: float = SIGN_FLIP_FAILURE_RATE,
) -> bool:
    if p025 is None or draws <= 0:
        return False
    return p025 > 0 and (sign_flips / draws) < rate


def role_gap_acceptable(
    gap: float | None,
    two_feature_gap: float | None,
    *,
    failure_threshold: float = ROLE_GAP_FAILURE_THRESHOLD,
    slack: float = ROLE_GAP_VS_TWO_FEATURE_SLACK,
) -> bool:
    if gap is None:
        return False
    if gap > failure_threshold:
        return False
    if two_feature_gap is not None and gap > two_feature_gap + slack:
        return False
    return True


def pca_materially_better(
    pca: CombatCandidateSnapshot,
    alternative: CombatCandidateSnapshot,
) -> bool:
    rmse_gain = relative_rmse_increase(alternative.val_rmse, pca.val_rmse)
    better_rmse = rmse_gain is not None and rmse_gain <= -RMSE_SLACK
    better_role = (
        pca.role_gap is not None
        and alternative.role_gap is not None
        and (alternative.role_gap - pca.role_gap) >= MATERIAL_ROLE_GAP_IMPROVEMENT
    )
    tighter = (
        pca.bootstrap_p025 is not None
        and alternative.bootstrap_p025 is not None
        and pca.bootstrap_p025 > alternative.bootstrap_p025 + 0.05
    )
    return bool(better_rmse or better_role or tighter)


def interpretation(kind: str) -> str:
    return INTERPRETATIONS.get(kind, "")


def select_combat_parameterization(
    candidates: list[CombatCandidateSnapshot],
) -> tuple[str, str, list[str]]:
    """Return (selection token, winning kind, reasons). Test set is not used."""
    by_kind = {item.kind: item for item in candidates}
    two = by_kind.get(TWO_FEATURE)
    reasons: list[str] = []
    if two is None:
        return SELECTION_RETHINK, TWO_FEATURE, ["Missing two-feature reference."]

    eligible: list[CombatCandidateSnapshot] = []
    for item in candidates:
        if item.kind == TWO_FEATURE:
            continue
        rmse_ok = competitive_rmse(item.val_rmse, two.val_rmse)
        stable = bootstrap_coefficient_stable(
            item.bootstrap_p025, item.bootstrap_sign_flips, item.bootstrap_draws
        )
        role_ok = role_gap_acceptable(item.role_gap, two.role_gap)
        if rmse_ok and stable and role_ok and item.coefficient_positive:
            eligible.append(item)
        else:
            reasons.append(
                f"{item.kind}: competitive={rmse_ok} bootstrap_stable={stable} "
                f"role_ok={role_ok} coef_positive={item.coefficient_positive}"
            )

    if eligible:
        ncr = next((item for item in eligible if item.kind == NET_COMBAT_RATE), None)
        pca = next((item for item in eligible if item.kind == PCA_COMBAT_FACTOR), None)
        if pca is not None and ncr is not None and pca_materially_better(pca, ncr):
            winner = pca
            reasons.append("PCA materially improved RMSE, role gap, or bootstrap tightness vs NCR.")
        elif ncr is not None and pca is not None:
            winner = ncr
            reasons.append(
                "NetCombatRate and PCA are tied; prefer NetCombatRate for interpretability."
            )
        else:
            winner = min(
                eligible,
                key=lambda item: (
                    item.val_rmse if item.val_rmse is not None else 1e9,
                    item.role_gap if item.role_gap is not None else 1e9,
                    SIMPLICITY_RANK.get(item.kind, 99),
                ),
            )
        reasons.append(f"Selected {winner.kind} as the stable single combat signal.")
        return SELECTION_BY_KIND.get(winner.kind, SELECTION_RETHINK), winner.kind, reasons

    two_stable = bootstrap_coefficient_stable(
        two.bootstrap_p025, two.bootstrap_sign_flips, two.bootstrap_draws
    )
    two_role = role_gap_acceptable(two.role_gap, two.role_gap)
    if two_stable and two_role:
        reasons.append("No single-factor candidate cleared the gates; keep two-feature combat.")
        return SELECTION_KEEP_TWO, TWO_FEATURE, reasons
    reasons.append(
        "No single-factor representation is competitive, stable, and role-balanced. "
        + CONSTRAINED_REGRESSION_FALLBACK
    )
    if not two_stable:
        return SELECTION_RETHINK, TWO_FEATURE, reasons
    return SELECTION_KEEP_TWO, TWO_FEATURE, reasons


def combat_factor_readiness(
    *,
    selection: str,
    winning_kind: str,
    snapshot: CombatCandidateSnapshot | None,
    persisted: bool = False,
    snapshots_exist: bool = False,
    ranking_policy_defined: bool = False,
    reliability_policy_defined: bool = False,
    api_contract_ready: bool = False,
) -> str:
    frontend = (
        persisted
        and snapshots_exist
        and ranking_policy_defined
        and reliability_policy_defined
        and api_contract_ready
    )
    if selection in {SELECTION_KEEP_TWO, SELECTION_RETHINK}:
        return "NOT_READY"
    if snapshot is None or snapshot.kind != winning_kind:
        return "NOT_READY"
    ranking_ok = (
        snapshot.ranking_spearman_500 is None
        or snapshot.ranking_spearman_500 >= RANKING_STABILITY_500_MIN
        or (
            snapshot.ranking_spearman_250 is not None
            and snapshot.ranking_spearman_250 >= RANKING_STABILITY_500_MIN
        )
    )
    gates = (
        bootstrap_coefficient_stable(
            snapshot.bootstrap_p025, snapshot.bootstrap_sign_flips, snapshot.bootstrap_draws
        )
        and snapshot.coefficient_positive
        and not snapshot.temporal_collapse
        and snapshot.tier_sign_stable
        and role_gap_acceptable(snapshot.role_gap, snapshot.role_gap)
        and ranking_ok
        and snapshot.baseline_advantage
    )
    if not gates:
        return "NOT_READY"
    if frontend:
        return "READY_FOR_FRONTEND"
    return "READY_FOR_FINAL_METRIC_VERSION"


def recommended_spec(kind: str) -> dict[str, object]:
    combat: dict[str, object]
    if kind == NET_COMBAT_RATE:
        combat = {
            "representation": "NetCombatRate",
            "definition": "kpr_residual + negative_dpr_residual",
            "features": ["net_combat_rate"],
        }
    elif kind == PCA_COMBAT_FACTOR:
        combat = {
            "representation": "PCACombatFactor",
            "definition": "oriented PC1 of z(kpr_residual), z(negative_dpr_residual)",
            "features": ["combat_factor"],
        }
    elif kind == EQUAL_WEIGHT:
        combat = {
            "representation": "EqualWeightCombat",
            "definition": "0.5 * z(kpr_residual) + 0.5 * z(negative_dpr_residual)",
            "features": ["equal_weight_combat"],
        }
    elif kind == NEGATIVE_DPR_ONLY:
        combat = {
            "representation": "negative_dpr_residual",
            "definition": "negative_dpr_residual",
            "features": ["negative_dpr_residual"],
        }
    elif kind == KPR_ONLY:
        combat = {
            "representation": "kpr_residual",
            "definition": "kpr_residual",
            "features": ["kpr_residual"],
        }
    else:
        combat = {
            "representation": "two_feature",
            "definition": "kpr_residual + negative_dpr_residual with independent weights",
            "features": ["kpr_residual", "negative_dpr_residual"],
        }
    return {
        "metric_name": "CIR",
        "version": CIR_V02_RECOMMENDED_VERSION,
        "combat": combat,
        "context": "Context v2; KPR/DPR=role+tier; lambda=1; tau=500",
        "shrinkage_k": 50.0,
        "scale": "empirical percentile",
        "minimum_established_sample": ">=250 rounds",
        "persist": False,
    }
