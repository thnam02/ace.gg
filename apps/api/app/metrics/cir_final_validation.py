from __future__ import annotations

from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from app.metrics.cir_final_validation_config import (
    CIR_V02_RECOMMENDED_VERSION,
    CROSS_TIER_RMSE_RATIO_LIMIT,
    FROZEN_COMBAT_FEATURES,
    FROZEN_SHRINKAGE_K,
    INCREMENTAL_FEATURE_SLACK,
    LATER_EVENT_RMSE_RATIO_LIMIT,
    RANKING_STABILITY_500_MIN,
    ROLE_GAP_FAILURE_THRESHOLD,
    SIGN_FLIP_FAILURE_RATE,
)
from app.metrics.cir_validation_metrics import (
    distribution_summary,
    kendall_tau_correlation,
    mae,
    percentile,
    spearman_correlation,
)
from app.metrics.ridge_regression import r2_score, rmse
from app.schemas.cir_final_validation import (
    CIRFinalValidationRecommendation,
    CoefficientSummary,
    FailureConditionAudit,
    NumericSummary,
    PublicRankingRecommendation,
)
from app.schemas.context_v2 import SplitMetrics


def numeric_summary(values: list[float]) -> NumericSummary:
    if not values:
        return NumericSummary()
    summary = distribution_summary(values)
    return NumericSummary(
        mean=summary["mean"],
        median=summary["median"],
        std=summary["std"],
        min=float(min(values)),
        max=float(max(values)),
        p05=percentile(values, 5),
        p25=summary["p25"],
        p75=summary["p75"],
        p95=percentile(values, 95),
        count=len(values),
    )


def coefficient_summary(
    values: list[float], *, expected_positive: bool = True
) -> CoefficientSummary:
    base = numeric_summary(values)
    if expected_positive:
        flips = sum(1 for value in values if value < 0)
    else:
        flips = sum(1 for value in values if value > 0)
    positive = sum(1 for value in values if value > 0)
    return CoefficientSummary(
        mean=base.mean,
        median=base.median,
        std=base.std,
        min=base.min,
        max=base.max,
        p05=base.p05,
        p25=base.p25,
        p75=base.p75,
        p95=base.p95,
        count=base.count,
        sign_flip_count=flips,
        positive_share=(positive / len(values)) if values else None,
    )


def chronological_two_way(
    map_ids: list[UUID],
    train_fraction: float = 0.85,
) -> tuple[set[UUID], set[UUID]]:
    total = len(map_ids)
    if total == 0:
        return set(), set()
    if total == 1:
        return {map_ids[0]}, set()
    train_end = max(1, min(total - 1, int(total * train_fraction)))
    return set(map_ids[:train_end]), set(map_ids[train_end:])


def top_n_retention(reference: list[str], candidate: list[str], top_n: int) -> float | None:
    if top_n <= 0 or not reference or not candidate:
        return None
    ref = set(reference[: min(top_n, len(reference))])
    cand = set(candidate[: min(top_n, len(candidate))])
    if not ref:
        return None
    return len(ref & cand) / len(ref)


def rank_map(ordered_ids: list[str]) -> dict[str, int]:
    return {player_id: index + 1 for index, player_id in enumerate(ordered_ids)}


def rank_movement(
    reference: dict[str, int],
    candidate: dict[str, int],
) -> tuple[float | None, float | None]:
    shared = [player_id for player_id in reference if player_id in candidate]
    if not shared:
        return None, None
    diffs = [abs(reference[player_id] - candidate[player_id]) for player_id in shared]
    return float(np.mean(diffs)), float(np.median(diffs))


def ranking_correlations(
    reference: dict[str, int],
    candidate: dict[str, int],
) -> tuple[float | None, float | None]:
    shared = [player_id for player_id in reference if player_id in candidate]
    if len(shared) < 2:
        return None, None
    left = np.array([reference[player_id] for player_id in shared], dtype=np.float64)
    right = np.array([candidate[player_id] for player_id in shared], dtype=np.float64)
    return spearman_correlation(left, right), kendall_tau_correlation(left, right)


def ordered_player_ids(scores: dict[str, float]) -> list[str]:
    return [
        player_id for player_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]


def relative_rmse_increase(baseline: float | None, other: float | None) -> float | None:
    if baseline is None or other is None or baseline == 0:
        return None
    return (other - baseline) / baseline


def second_feature_adds_value(
    both_rmse: float | None,
    best_single_rmse: float | None,
    slack: float = INCREMENTAL_FEATURE_SLACK,
) -> bool:
    if both_rmse is None or best_single_rmse is None or best_single_rmse == 0:
        return False
    return (best_single_rmse - both_rmse) / best_single_rmse >= slack


def recommend_sample_threshold(results: list[tuple[int, int, float | None]]) -> int:
    """results: (threshold, eligible_players, spearman_vs_full)."""
    for threshold, eligible, spearman in results:
        if threshold < 100:
            continue
        if eligible >= 8 and spearman is not None and spearman >= 0.85:
            return threshold
    return 500


def reliability_band(rounds: int) -> str:
    if rounds < 100:
        return "LOW"
    if rounds < 250:
        return "MEDIUM"
    return "HIGH"


def sample_label(rounds: int) -> str:
    if rounds < 100:
        return "LOW_SAMPLE"
    if rounds < 250:
        return "PROVISIONAL"
    return "ESTABLISHED"


def coefficient_sign(value: float | None) -> str:
    if value is None:
        return "missing"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def audit_failure_conditions(
    *,
    kpr_values: list[float],
    ndpr_values: list[float],
    primary_val_rmse: float | None,
    later_event_rmses: list[float],
    t1_rmse: float | None,
    t2_rmse: float | None,
    t1_kpr_sign: str,
    t2_kpr_sign: str,
    t1_ndpr_sign: str,
    t2_ndpr_sign: str,
    role_gaps: list[float],
    bootstrap_kpr_low: float | None,
    bootstrap_ndpr_low: float | None,
    ranking_spearman_500: float | None,
    cir_event_wins: int,
    kd_event_wins: int,
    acs_event_wins: int,
    vlr_event_wins: int,
    baseline_cir_better: bool,
) -> FailureConditionAudit:
    failures: list[str] = []
    warnings: list[str] = []
    fold_count = max(len(kpr_values), 1)
    kpr_flips = sum(1 for value in kpr_values if value < 0)
    ndpr_flips = sum(1 for value in ndpr_values if value < 0)
    if (
        kpr_flips / fold_count >= SIGN_FLIP_FAILURE_RATE
        or ndpr_flips / fold_count >= SIGN_FLIP_FAILURE_RATE
    ):
        failures.append(
            f"coefficient sign flips: KPR {kpr_flips}/{fold_count}, -DPR {ndpr_flips}/{fold_count}"
        )
    if primary_val_rmse is not None:
        degraded = [
            rmse
            for rmse in later_event_rmses
            if rmse > primary_val_rmse * LATER_EVENT_RMSE_RATIO_LIMIT
        ]
        if degraded:
            failures.append(
                f"{len(degraded)} later/holdout events exceeded "
                f"{LATER_EVENT_RMSE_RATIO_LIMIT:.1f}× primary val RMSE"
            )
    if (
        t1_rmse is not None
        and t2_rmse is not None
        and min(t1_rmse, t2_rmse) > 0
        and max(t1_rmse, t2_rmse) / min(t1_rmse, t2_rmse) > CROSS_TIER_RMSE_RATIO_LIMIT
        and (t1_kpr_sign != t2_kpr_sign or t1_ndpr_sign != t2_ndpr_sign)
    ):
        failures.append("large T1/T2 disagreement in RMSE and coefficient signs")
    elif t1_kpr_sign != t2_kpr_sign or t1_ndpr_sign != t2_ndpr_sign:
        warnings.append("T1/T2 coefficient signs disagree")
    high_gaps = [gap for gap in role_gaps if gap > ROLE_GAP_FAILURE_THRESHOLD]
    if high_gaps and len(high_gaps) >= max(1, len(role_gaps) // 2):
        failures.append(
            f"role median gap exceeded {ROLE_GAP_FAILURE_THRESHOLD} in {len(high_gaps)} folds"
        )
    elif any(gap > ROLE_GAP_FAILURE_THRESHOLD for gap in role_gaps):
        warnings.append("at least one fold has a role median gap above 15")
    if bootstrap_kpr_low is not None and bootstrap_kpr_low < 0:
        failures.append("bootstrap 2.5% interval for KPR includes a negative coefficient")
    if bootstrap_ndpr_low is not None and bootstrap_ndpr_low < 0:
        failures.append("bootstrap 2.5% interval for -DPR includes a negative coefficient")
    if ranking_spearman_500 is not None and ranking_spearman_500 < RANKING_STABILITY_500_MIN:
        failures.append(
            f"ranking Spearman at 500 rounds is {ranking_spearman_500:.3f} "
            f"(below {RANKING_STABILITY_500_MIN})"
        )
    baseline_wins = max(kd_event_wins, acs_event_wins, vlr_event_wins)
    if cir_event_wins + kd_event_wins + acs_event_wins + vlr_event_wins > 0:
        if cir_event_wins < baseline_wins:
            warnings.append(
                f"CIR won {cir_event_wins} events vs K/D {kd_event_wins}, "
                f"ACS {acs_event_wins}, VLR {vlr_event_wins}"
            )
            if not baseline_cir_better:
                failures.append("CIR does not consistently outperform simple baselines")
        if not baseline_cir_better:
            failures.append("CIR lost the apples-to-apples aggregate baseline comparison")
    return FailureConditionAudit(passed=not failures, failures=failures, warnings=warnings)


def decide_readiness(
    *,
    failure_audit: FailureConditionAudit,
    persisted: bool,
    snapshots_exist: bool,
    ranking_policy_defined: bool,
    reliability_policy_defined: bool,
    api_contract_ready: bool,
) -> str:
    if not failure_audit.passed:
        return "NOT_READY"
    frontend_ready = (
        persisted
        and snapshots_exist
        and ranking_policy_defined
        and reliability_policy_defined
        and api_contract_ready
    )
    if frontend_ready:
        return "READY_FOR_FRONTEND"
    return "READY_FOR_FINAL_METRIC_VERSION"


def build_recommendation(
    *,
    readiness: str,
    sample_threshold: int,
    reasons: list[str],
) -> CIRFinalValidationRecommendation:
    ranking = PublicRankingRecommendation(
        minimum_rounds=sample_threshold,
        low_sample_max_rounds=99,
        provisional_max_rounds=249,
        established_min_rounds=max(250, sample_threshold) if sample_threshold >= 250 else 250,
        labels={
            "<100 rounds": "LOW_SAMPLE",
            "100-249 rounds": "PROVISIONAL",
            ">=250 rounds": "ESTABLISHED",
        },
        reliability=(
            "Keep reliability separate from CIR. Band by rounds: "
            "<100 LOW, 100-249 MEDIUM, >=250 HIGH. "
            "Optionally display percent = min(100, rounds/250*100)."
        ),
        reasons=[
            f"Recommended public ranking floor is >={sample_threshold} rounds.",
            "Do not mix reliability into the CIR percentile.",
        ],
    )
    return CIRFinalValidationRecommendation(
        readiness=readiness,
        persist=False,
        metric_name="CIR",
        version=CIR_V02_RECOMMENDED_VERSION,
        features=list(FROZEN_COMBAT_FEATURES),
        context="Context v2; KPR/DPR=role+tier; lambda=1; tau=500",
        shrinkage_k=FROZEN_SHRINKAGE_K,
        scale="empirical percentile",
        ranking=ranking,
        reasons=reasons,
    )


def split_metrics_from_arrays(
    targets: NDArray[np.float64],
    predictions: NDArray[np.float64],
) -> SplitMetrics:
    if len(targets) == 0:
        return SplitMetrics()
    return SplitMetrics(
        rmse=rmse(targets, predictions),
        mae=mae(targets, predictions),
        r2=r2_score(targets, predictions),
        spearman=spearman_correlation(targets, predictions),
    )
