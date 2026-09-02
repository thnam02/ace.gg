from __future__ import annotations

import numpy as np

from app.metrics.cir_validation_config import CIR_ROLES
from app.metrics.cir_validation_metrics import distribution_summary, percentile
from app.metrics.context_v2 import RATE_FEATURE_NAMES
from app.metrics.context_v2_config import (
    CONTEXT_MODE_NONE,
    CONTEXT_MODE_V1,
    SELECTION_RMSE_RELATIVE_SLACK,
)
from app.schemas.context_features import ContextAdjustedFeatures
from app.schemas.context_v2 import (
    ContextExperimentResult,
    ControllerShiftDiagnosis,
    FeatureDisposition,
    FeatureRoleDiagnosis,
    FeatureStatSummary,
    RoleBiasMetrics,
)

_CIR_FEATURE_ORDER: tuple[str, ...] = (
    "kpr_residual",
    "negative_dpr_residual",
    "residual_adr",
    "opening_frequency_residual",
    "opening_efficiency_adjusted",
    "apr_residual",
    "kast_residual",
    "clutch_rate_adjusted",
)

_FEATURE_TO_ADJUSTED: dict[str, str] = {
    "kpr": "kpr_residual",
    "dpr": "dpr_residual",
    "apr": "apr_residual",
    "kast": "kast_residual",
    "opening_frequency": "opening_frequency_residual",
    "opening_efficiency": "opening_efficiency_adjusted",
    "residual_adr": "residual_adr",
}


def role_bias_metrics(
    role_values: dict[str, list[tuple[float, int]]],
) -> RoleBiasMetrics:
    medians: dict[str, float | None] = {}
    means: dict[str, float | None] = {}
    p10: dict[str, float | None] = {}
    p90: dict[str, float | None] = {}
    counts: dict[str, int] = {}
    rounds: dict[str, int] = {}
    for role in CIR_ROLES:
        rows = role_values.get(role, [])
        scores = [score for score, _ in rows]
        summary = distribution_summary(scores)
        medians[role] = summary["median"]
        means[role] = summary["mean"]
        p10[role] = summary["p10"]
        p90[role] = summary["p90"]
        counts[role] = int(summary["count"] or 0)
        rounds[role] = sum(weight for _, weight in rows)

    present = [value for value in medians.values() if value is not None]
    max_gap = (max(present) - min(present)) if len(present) >= 2 else None

    def _gap(left: str, right: str) -> float | None:
        left_value = medians[left]
        right_value = medians[right]
        if left_value is None or right_value is None:
            return None
        return float(left_value - right_value)

    return RoleBiasMetrics(
        medians=medians,
        means=means,
        p10=p10,
        p90=p90,
        counts=counts,
        rounds=rounds,
        max_role_median_gap=max_gap,
        controller_vs_duelist_gap=_gap("Controller", "Duelist"),
        controller_vs_initiator_gap=_gap("Controller", "Initiator"),
        controller_vs_sentinel_gap=_gap("Controller", "Sentinel"),
    )


def feature_stat_summary(
    feature_rows: list[dict[str, float | None]],
    coefficients: dict[str, float],
    feature_names: tuple[str, ...] = _CIR_FEATURE_ORDER,
) -> FeatureStatSummary:
    means: dict[str, float | None] = {}
    variances: dict[str, float | None] = {}
    columns: dict[str, list[float]] = {name: [] for name in feature_names}
    for row in feature_rows:
        for name in feature_names:
            value = row.get(name)
            if value is not None:
                columns[name].append(float(value))
    for name in feature_names:
        values = columns[name]
        if not values:
            means[name] = None
            variances[name] = None
            continue
        array = np.array(values, dtype=np.float64)
        means[name] = float(np.mean(array))
        variances[name] = float(np.var(array))

    correlations: dict[str, dict[str, float | None]] = {}
    for name_a in feature_names:
        correlations[name_a] = {}
        for name_b in feature_names:
            correlations[name_a][name_b] = _safe_corr(columns[name_a], columns[name_b])

    signs = {name: _sign(coefficients.get(name, 0.0)) for name in feature_names}
    magnitudes = {name: abs(float(coefficients.get(name, 0.0))) for name in feature_names}
    return FeatureStatSummary(
        means=means,
        variances=variances,
        correlations=correlations,
        coefficient_signs=signs,
        coefficient_magnitudes=magnitudes,
    )


def _safe_corr(left: list[float], right: list[float]) -> float | None:
    n = min(len(left), len(right))
    if n < 2:
        return None
    a = np.array(left[:n], dtype=np.float64)
    b = np.array(right[:n], dtype=np.float64)
    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return None
    corr = np.corrcoef(a, b)[0, 1]
    if np.isnan(corr):
        return None
    return float(corr)


def _sign(value: float) -> str:
    if value > 0:
        return "+"
    if value < 0:
        return "-"
    return "0"


def diagnose_controller_shift(
    rows: list[tuple[str, int, ContextAdjustedFeatures]],
    coefficients: dict[str, float],
) -> ControllerShiftDiagnosis:
    """rows: (role, rounds, adjusted features)."""
    diagnoses: list[FeatureRoleDiagnosis] = []
    feature_gaps: list[tuple[str, float]] = []
    for feature in (*RATE_FEATURE_NAMES, "residual_adr"):
        if feature == "clutch":
            continue
        raw_attr, expected_attr, adjusted_attr = _feature_attrs(feature)
        by_role: dict[str, list[tuple[float | None, float | None, float | None, int]]] = {}
        for role, rounds, adjusted in rows:
            raw = getattr(adjusted, raw_attr)
            expected = getattr(adjusted, expected_attr)
            residual = getattr(adjusted, adjusted_attr)
            if residual is None and raw is None:
                continue
            by_role.setdefault(role, []).append(
                (
                    float(raw) if raw is not None else None,
                    float(expected) if expected is not None else None,
                    float(residual) if residual is not None else None,
                    rounds,
                )
            )
        controller_adjusted: float | None = None
        for role in CIR_ROLES:
            samples = by_role.get(role, [])
            if not samples:
                diagnoses.append(FeatureRoleDiagnosis(feature=feature, role=role, sample_size=0))
                continue
            exposure = float(sum(item[3] for item in samples))
            raw_pairs = [(item[0], item[3]) for item in samples if item[0] is not None]
            baseline_pairs = [(item[1], item[3]) for item in samples if item[1] is not None]
            adjusted_pairs = [(item[2], item[3]) for item in samples if item[2] is not None]
            raw_mean = _weighted_mean(raw_pairs)
            baseline_mean = _weighted_mean(baseline_pairs)
            adjusted_mean = _weighted_mean(adjusted_pairs)
            adjusted_median = percentile([item[2] for item in samples if item[2] is not None], 50)
            diagnoses.append(
                FeatureRoleDiagnosis(
                    feature=feature,
                    role=role,
                    raw_role_mean=raw_mean,
                    context_baseline_mean=baseline_mean,
                    adjusted_role_mean=adjusted_mean,
                    adjusted_role_median=adjusted_median,
                    sample_size=len(samples),
                    exposure=exposure,
                )
            )
            if role == "Controller":
                controller_adjusted = adjusted_mean
        others = [
            item.adjusted_role_mean
            for item in diagnoses
            if item.feature == feature
            and item.role != "Controller"
            and item.adjusted_role_mean is not None
        ]
        if controller_adjusted is not None and others:
            gap = controller_adjusted - (sum(others) / len(others))
            feature_gaps.append((feature, gap))

    evidence: list[str] = []
    driving: list[str] = []
    feature_gaps.sort(key=lambda item: abs(item[1]), reverse=True)
    for feature, gap in feature_gaps:
        if abs(gap) < 1e-6:
            continue
        direction = "above" if gap > 0 else "below"
        coef_name = _FEATURE_TO_ADJUSTED.get(feature, feature)
        coef = coefficients.get(coef_name, 0.0)
        if feature == "dpr":
            coef = coefficients.get("negative_dpr_residual", 0.0)
            evidence.append(
                f"Controller {feature} residual is {gap:+.4f} vs other roles "
                f"(negative_dpr coefficient={coef:+.3f}); "
                + (
                    "agent/role baselines may over-correct deaths."
                    if gap < 0
                    else "Controllers still die less than their context after adjustment."
                )
            )
        else:
            evidence.append(
                f"Controller {feature} residual remains {gap:+.4f} vs other-role mean "
                f"after adjustment (coefficient {coef_name}={coef:+.3f}); "
                f"Controller sits {direction} other roles on this feature."
            )
        if abs(gap) >= 0.01 and abs(coef) >= 0.01:
            driving.append(feature)

    if not evidence:
        evidence.append(
            "No Controller residual gap exceeded the reporting threshold after adjustment."
        )
    return ControllerShiftDiagnosis(
        features=diagnoses,
        evidence=evidence,
        driving_features=driving,
    )


def _feature_attrs(feature: str) -> tuple[str, str, str]:
    if feature == "residual_adr":
        return "residual_adr", "residual_adr", "residual_adr"
    if feature == "opening_efficiency":
        return (
            "opening_efficiency_raw",
            "opening_efficiency_adjusted",
            "opening_efficiency_adjusted",
        )
    if feature == "opening_frequency":
        return "opening_frequency", "opening_frequency_expected", "opening_frequency_residual"
    if feature == "kast":
        return "kast", "kast_expected", "kast_residual"
    return feature, f"{feature}_expected", f"{feature}_residual"


def _weighted_mean(pairs: list[tuple[float, int]]) -> float | None:
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / total


def select_context_configuration(
    results: list[ContextExperimentResult],
) -> ContextExperimentResult:
    """Pick a winner from validation metrics only. Test fields are ignored."""
    if not results:
        raise ValueError("No context experiments to select from")
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
    return prefer_simpler_if_similar(ranked)


def _simplicity_rank(result: ContextExperimentResult) -> int:
    rank = result.configuration.get("simplicity_rank", 0)
    return rank if isinstance(rank, int) else 0


def prefer_simpler_if_similar(
    ranked: list[ContextExperimentResult],
) -> ContextExperimentResult:
    if not ranked:
        raise ValueError("No context experiments to select from")
    best = ranked[0]
    best_rmse = best.validation_metrics.rmse
    if best_rmse is None:
        return best
    candidates = [best]
    for result in ranked[1:]:
        rmse = result.validation_metrics.rmse
        if rmse is None:
            continue
        relative = abs(rmse - best_rmse) / max(best_rmse, 1e-9)
        if relative <= SELECTION_RMSE_RELATIVE_SLACK:
            candidates.append(result)
    return min(candidates, key=_simplicity_rank)


def decide_context_recommendation(
    winner: ContextExperimentResult,
) -> str:
    if winner.name == "context_v1" or winner.configuration.get("mode") == CONTEXT_MODE_V1:
        return "KEEP_CONTEXT_V1"
    if winner.name == "no_context" or winner.configuration.get("mode") == CONTEXT_MODE_NONE:
        return "USE_NO_CONTEXT"
    return "USE_CONTEXT_V2"


def feature_dispositions(
    coefficients: dict[str, float],
    feature_stats: FeatureStatSummary,
) -> list[FeatureDisposition]:
    unexpected_negative = {"residual_adr", "kast_residual", "opening_frequency_residual"}
    rows: list[FeatureDisposition] = []
    for name in _CIR_FEATURE_ORDER:
        if name == "clutch_rate_adjusted":
            rows.append(
                FeatureDisposition(
                    feature=name,
                    disposition="DIAGNOSE",
                    reason="Clutch remains coverage-gated; keep disabled until source data exists.",
                )
            )
            continue
        magnitude = abs(coefficients.get(name, 0.0))
        sign = feature_stats.coefficient_signs.get(name, "0")
        variance = feature_stats.variances.get(name)
        if magnitude < 0.01:
            rows.append(
                FeatureDisposition(
                    feature=name,
                    disposition="REMOVE_CANDIDATE",
                    reason=(
                        f"Coefficient magnitude {magnitude:.4f} is near zero"
                        + (f"; variance={variance:.4g}" if variance is not None else "")
                        + ". Do not remove automatically."
                    ),
                )
            )
            continue
        if name in unexpected_negative and sign == "-":
            rows.append(
                FeatureDisposition(
                    feature=name,
                    disposition="DIAGNOSE",
                    reason=(
                        f"Unexpected negative coefficient {coefficients.get(name, 0.0):+.4f} "
                        "after this context regime."
                    ),
                )
            )
            continue
        rows.append(
            FeatureDisposition(
                feature=name,
                disposition="KEEP",
                reason=f"Coefficient {coefficients.get(name, 0.0):+.4f} remains informative.",
            )
        )
    return rows
