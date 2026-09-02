from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from app.metrics.cir_feature_pruning_config import (
    COMBAT_FEATURES,
    CORRELATION_FLAG_THRESHOLD,
    MATERIAL_ROLE_GAP_IMPROVEMENT,
    MATERIAL_SPEARMAN_IMPROVEMENT,
    NEGLIGIBLE_RMSE_RELATIVE,
    PRUNING_CANDIDATE_FEATURES,
    SELECTION_RMSE_RELATIVE_SLACK,
)
from app.metrics.cir_validation_config import CIR_ROLES
from app.metrics.cir_validation_metrics import (
    distribution_summary,
    spearman_correlation,
)
from app.metrics.ridge_regression import r2_score
from app.schemas.cir_feature_pruning import (
    CirV02FeatureRecommendation,
    FeatureCorrelationPair,
    FeatureDistribution,
    FeaturePruningDisposition,
    FeatureSubsetResult,
    IncrementalFeatureDiagnosis,
    ResidualAdrBin,
    ResidualAdrDiagnosis,
    ResidualAdrModelFit,
)
from app.schemas.context_v2 import RoleBiasMetrics


@dataclass(frozen=True)
class PlayerFeatureRow:
    values: dict[str, float | None]
    role: str
    tier: str
    split: str
    signed_outcome: float | None


@dataclass(frozen=True)
class TeamFeatureRow:
    deltas: dict[str, float]
    outcome_residual: float
    split: str


def pearson_correlation(left: list[float], right: list[float]) -> float | None:
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


def feature_distribution(
    feature: str,
    values: list[float | None],
    *,
    outcomes: list[float | None] | None = None,
    group_type: str = "overall",
    group_value: str = "all",
) -> FeatureDistribution:
    present = [float(value) for value in values if value is not None]
    missing = len(values) - len(present)
    neutralized = sum(1 for value in values if value is None or abs(float(value)) < 1e-12)
    summary = distribution_summary(present)
    paired_feature: list[float] = []
    paired_outcome: list[float] = []
    if outcomes is not None:
        for value, outcome in zip(values, outcomes, strict=True):
            if value is None or outcome is None:
                continue
            paired_feature.append(float(value))
            paired_outcome.append(float(outcome))
    return FeatureDistribution(
        feature=feature,
        group_type=group_type,
        group_value=group_value,
        count=int(summary["count"] or 0),
        mean=summary["mean"],
        std=summary["std"],
        p10=summary["p10"],
        p25=summary["p25"],
        median=summary["median"],
        p75=summary["p75"],
        p90=summary["p90"],
        missing_pct=(missing / len(values) * 100.0) if values else 0.0,
        zero_or_neutralized_pct=(neutralized / len(values) * 100.0) if values else 0.0,
        correlation_with_outcome_residual=pearson_correlation(paired_feature, paired_outcome),
    )


def diagnose_feature_distributions(
    rows: list[PlayerFeatureRow],
    *,
    features: tuple[str, ...] = PRUNING_CANDIDATE_FEATURES,
) -> list[FeatureDistribution]:
    reports: list[FeatureDistribution] = []
    for name in features:
        values = [row.values.get(name) for row in rows]
        outcomes = [row.signed_outcome for row in rows]
        reports.append(feature_distribution(name, values, outcomes=outcomes))
        by_role: dict[str, list[PlayerFeatureRow]] = defaultdict(list)
        by_tier: dict[str, list[PlayerFeatureRow]] = defaultdict(list)
        for row in rows:
            by_role[row.role].append(row)
            by_tier[row.tier].append(row)
        for role in CIR_ROLES:
            role_rows = by_role.get(role, [])
            reports.append(
                feature_distribution(
                    name,
                    [row.values.get(name) for row in role_rows],
                    outcomes=[row.signed_outcome for row in role_rows],
                    group_type="role",
                    group_value=role,
                )
            )
        for tier in sorted(by_tier):
            tier_rows = by_tier[tier]
            reports.append(
                feature_distribution(
                    name,
                    [row.values.get(name) for row in tier_rows],
                    outcomes=[row.signed_outcome for row in tier_rows],
                    group_type="tier",
                    group_value=tier,
                )
            )
    return reports


def feature_correlations(
    rows: list[TeamFeatureRow],
    *,
    features: tuple[str, ...] = PRUNING_CANDIDATE_FEATURES,
    threshold: float = CORRELATION_FLAG_THRESHOLD,
) -> list[FeatureCorrelationPair]:
    pairs: list[FeatureCorrelationPair] = []
    for index, left in enumerate(features):
        for right in features[index + 1 :]:
            left_values = [row.deltas.get(left, 0.0) for row in rows]
            right_values = [row.deltas.get(right, 0.0) for row in rows]
            corr = pearson_correlation(left_values, right_values)
            if corr is None:
                continue
            pairs.append(
                FeatureCorrelationPair(
                    left=left,
                    right=right,
                    correlation=corr,
                    flagged=abs(corr) >= threshold,
                )
            )
    return pairs


def fit_named_ols(
    columns: dict[str, list[float]],
    target: list[float],
    names: tuple[str, ...],
    *,
    model_name: str | None = None,
) -> ResidualAdrModelFit:
    if not target or not names:
        return ResidualAdrModelFit(name=model_name or "", sample_size=len(target))
    n = len(target)
    design = np.column_stack(
        [np.ones(n, dtype=np.float64)]
        + [np.asarray(columns[name], dtype=np.float64) for name in names]
    )
    y = np.array(target, dtype=np.float64)
    coeffs, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    predictions = design @ coeffs
    coefficient_map = {"intercept": float(coeffs[0])}
    for index, name in enumerate(names):
        coefficient_map[name] = float(coeffs[index + 1])
    return ResidualAdrModelFit(
        name=model_name or "+".join(names),
        coefficients=coefficient_map,
        r2=r2_score(y, predictions),
        spearman=spearman_correlation(y, predictions),
        sample_size=n,
    )


def quantile_bins(
    feature_values: list[float],
    outcomes: list[float],
    *,
    n_bins: int = 5,
) -> list[ResidualAdrBin]:
    if len(feature_values) < n_bins:
        return []
    x = np.array(feature_values, dtype=np.float64)
    y = np.array(outcomes, dtype=np.float64)
    quantiles = np.linspace(0.0, 100.0, n_bins + 1)
    edges = np.unique(np.percentile(x, quantiles))
    if len(edges) < 3:
        return []
    bins: list[ResidualAdrBin] = []
    for index in range(len(edges) - 1):
        lower = float(edges[index])
        upper = float(edges[index + 1])
        if index == len(edges) - 2:
            mask = (x >= lower) & (x <= upper)
        else:
            mask = (x >= lower) & (x < upper)
        if not np.any(mask):
            continue
        bins.append(
            ResidualAdrBin(
                bin_index=index,
                lower=lower,
                upper=upper,
                mean_feature=float(np.mean(x[mask])),
                mean_outcome=float(np.mean(y[mask])),
                count=int(np.sum(mask)),
            )
        )
    return bins


def _paired_columns(
    rows: list[TeamFeatureRow],
    names: tuple[str, ...],
) -> tuple[dict[str, list[float]], list[float]]:
    columns: dict[str, list[float]] = {name: [] for name in names}
    target: list[float] = []
    for row in rows:
        target.append(row.outcome_residual)
        for name in names:
            columns[name].append(row.deltas.get(name, 0.0))
    return columns, target


def diagnose_residual_adr(rows: list[TeamFeatureRow]) -> ResidualAdrDiagnosis:
    adr = "residual_adr"
    combat_and_adr = (*COMBAT_FEATURES, adr)
    columns, target = _paired_columns(rows, combat_and_adr)
    univariate = fit_named_ols(
        {adr: columns[adr]},
        target,
        (adr,),
        model_name="outcome ~ residual_adr",
    )
    controlled = fit_named_ols(
        columns,
        target,
        combat_and_adr,
        model_name="outcome ~ kpr + dpr + residual_adr",
    )
    squared = [value * value for value in columns[adr]]
    quadratic = fit_named_ols(
        {adr: columns[adr], "residual_adr_sq": squared},
        target,
        (adr, "residual_adr_sq"),
        model_name="outcome ~ residual_adr + residual_adr^2",
    )
    bins = quantile_bins(columns[adr], target)
    correlations = {
        name: pearson_correlation(columns[name], columns[adr]) for name in COMBAT_FEATURES
    }
    interpretation, evidence = interpret_residual_adr(
        univariate_slope=univariate.coefficients.get(adr),
        controlled_slope=controlled.coefficients.get(adr),
        combat_correlations=correlations,
        quadratic_coef=quadratic.coefficients.get("residual_adr_sq"),
        role_slopes={},
        bins=bins,
    )
    return ResidualAdrDiagnosis(
        univariate=univariate,
        controlling_for_combat=controlled,
        quadratic=quadratic,
        bins=bins,
        correlations_with_combat=correlations,
        interpretation=interpretation,
        evidence=evidence,
    )


def diagnose_residual_adr_grouped(
    team_rows: list[TeamFeatureRow],
    player_rows: list[PlayerFeatureRow],
) -> ResidualAdrDiagnosis:
    diagnosis = diagnose_residual_adr(team_rows)
    by_role: dict[str, ResidualAdrModelFit] = {}
    by_tier: dict[str, ResidualAdrModelFit] = {}
    for role in CIR_ROLES:
        role_rows = [row for row in player_rows if row.role == role]
        fit = _player_univariate_fit(role_rows, "residual_adr", model_name=f"role:{role}")
        if fit.sample_size:
            by_role[role] = fit
    tiers = sorted({row.tier for row in player_rows})
    for tier in tiers:
        tier_rows = [row for row in player_rows if row.tier == tier]
        fit = _player_univariate_fit(tier_rows, "residual_adr", model_name=f"tier:{tier}")
        if fit.sample_size:
            by_tier[tier] = fit
    role_slopes = {role: fit.coefficients.get("residual_adr") for role, fit in by_role.items()}
    interpretation, evidence = interpret_residual_adr(
        univariate_slope=diagnosis.univariate.coefficients.get("residual_adr"),
        controlled_slope=diagnosis.controlling_for_combat.coefficients.get("residual_adr"),
        combat_correlations=diagnosis.correlations_with_combat,
        quadratic_coef=diagnosis.quadratic.coefficients.get("residual_adr_sq"),
        role_slopes=role_slopes,
        bins=diagnosis.bins,
    )
    return ResidualAdrDiagnosis(
        univariate=diagnosis.univariate,
        controlling_for_combat=diagnosis.controlling_for_combat,
        quadratic=diagnosis.quadratic,
        by_role=by_role,
        by_tier=by_tier,
        bins=diagnosis.bins,
        correlations_with_combat=diagnosis.correlations_with_combat,
        interpretation=interpretation,
        evidence=evidence,
    )


def _player_univariate_fit(
    rows: list[PlayerFeatureRow],
    feature: str,
    *,
    model_name: str,
) -> ResidualAdrModelFit:
    values: list[float] = []
    outcomes: list[float] = []
    for row in rows:
        value = row.values.get(feature)
        if value is None or row.signed_outcome is None:
            continue
        values.append(float(value))
        outcomes.append(float(row.signed_outcome))
    if len(values) < 2:
        return ResidualAdrModelFit(name=model_name, sample_size=len(values))
    return fit_named_ols(
        {feature: values},
        outcomes,
        (feature,),
        model_name=model_name,
    )


def interpret_residual_adr(
    *,
    univariate_slope: float | None,
    controlled_slope: float | None,
    combat_correlations: dict[str, float | None],
    quadratic_coef: float | None,
    role_slopes: dict[str, float | None],
    bins: list[ResidualAdrBin],
) -> tuple[str, list[str]]:
    evidence: list[str] = []
    flags: list[str] = []
    max_corr = 0.0
    for name, corr in combat_correlations.items():
        if corr is None:
            continue
        evidence.append(f"corr(residual_adr, {name})={corr:+.3f}")
        max_corr = max(max_corr, abs(corr))
    if univariate_slope is not None:
        evidence.append(f"univariate slope={univariate_slope:+.4f}")
    if controlled_slope is not None:
        evidence.append(f"slope after KPR/DPR={controlled_slope:+.4f}")
    if quadratic_coef is not None:
        evidence.append(f"quadratic coefficient={quadratic_coef:+.4f}")

    if max_corr >= CORRELATION_FLAG_THRESHOLD:
        flags.append("multicollinearity")
        evidence.append(
            f"|r| with combat features reaches {max_corr:.3f} (>= {CORRELATION_FLAG_THRESHOLD})"
        )
    uni = univariate_slope
    ctrl = controlled_slope
    if uni is not None and ctrl is not None and uni >= -1e-4 and ctrl < 0:
        flags.append("suppression effect")
        evidence.append(
            "Univariate association is non-negative while the conditional coefficient is negative."
        )
    if _nonlinear_bins(bins) or (
        quadratic_coef is not None
        and uni is not None
        and abs(quadratic_coef) > abs(uni) * 0.25
        and abs(quadratic_coef) > 1e-6
    ):
        flags.append("nonlinearity")
        evidence.append("Quadratic term or binned means indicate a nonlinear relationship.")
    present_role_slopes = [slope for slope in role_slopes.values() if slope is not None]
    if present_role_slopes:
        signs = {1 if slope > 1e-6 else -1 if slope < -1e-6 else 0 for slope in present_role_slopes}
        signs.discard(0)
        if len(signs) > 1:
            flags.append("role interaction")
            evidence.append("Role-specific residual ADR slopes have mixed signs.")
    if (
        uni is not None
        and ctrl is not None
        and uni < 0
        and ctrl < 0
        and max_corr < CORRELATION_FLAG_THRESHOLD
        and "nonlinearity" not in flags
        and "role interaction" not in flags
    ):
        flags.append("true negative conditional association")
        evidence.append(
            "Both univariate and combat-controlled slopes are negative without strong collinearity."
        )

    if not flags:
        return "unclear", evidence or [
            "Insufficient evidence to classify the negative coefficient."
        ]
    if len(flags) > 1:
        evidence.append("Multiple mechanisms are plausible; do not force a single cause.")
        return "unclear", evidence
    return flags[0], evidence


def _nonlinear_bins(bins: list[ResidualAdrBin]) -> bool:
    means = [item.mean_outcome for item in bins if item.mean_outcome is not None]
    if len(means) < 4:
        return False
    increasing = all(left <= right for left, right in zip(means, means[1:], strict=False))
    decreasing = all(left >= right for left, right in zip(means, means[1:], strict=False))
    if increasing or decreasing:
        return False
    mid = means[len(means) // 2]
    return mid < min(means[0], means[-1]) or mid > max(means[0], means[-1])


def relative_rmse_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    if abs(baseline) < 1e-12:
        return None
    return (candidate - baseline) / baseline


def is_negligible_rmse_delta(delta: float | None) -> bool:
    return delta is None or abs(delta) < NEGLIGIBLE_RMSE_RELATIVE


def diagnose_incremental_feature(
    *,
    feature: str,
    combat_rmse: float | None,
    with_feature_rmse: float | None,
    combat_spearman: float | None,
    with_feature_spearman: float | None,
    by_role_outcome_correlation: dict[str, float | None],
    duelist_outcome_correlation: float | None = None,
    non_duelist_outcome_correlation: float | None = None,
    opening_style: bool = False,
) -> IncrementalFeatureDiagnosis:
    rmse_delta = relative_rmse_delta(combat_rmse, with_feature_rmse)
    spearman_delta = None
    if combat_spearman is not None and with_feature_spearman is not None:
        spearman_delta = with_feature_spearman - combat_spearman
    evidence: list[str] = []
    if rmse_delta is not None:
        evidence.append(f"validation RMSE relative change={rmse_delta:+.4%}")
    if spearman_delta is not None:
        evidence.append(f"validation Spearman change={spearman_delta:+.4f}")
    for role, corr in by_role_outcome_correlation.items():
        if corr is not None:
            evidence.append(f"{role} outcome correlation={corr:+.3f}")
    if duelist_outcome_correlation is not None:
        evidence.append(f"Duelist outcome correlation={duelist_outcome_correlation:+.3f}")
    if non_duelist_outcome_correlation is not None:
        evidence.append(f"non-Duelist outcome correlation={non_duelist_outcome_correlation:+.3f}")

    conclusion = "no meaningful incremental value"
    if opening_style:
        duelist_only = (
            duelist_outcome_correlation is not None
            and abs(duelist_outcome_correlation) >= 0.05
            and (
                non_duelist_outcome_correlation is None
                or abs(non_duelist_outcome_correlation) < 0.03
            )
        )
        if is_negligible_rmse_delta(rmse_delta) and duelist_only:
            conclusion = "useful only for Duelists"
        elif is_negligible_rmse_delta(rmse_delta):
            conclusion = "globally useless"
        elif rmse_delta is not None and rmse_delta < 0:
            conclusion = "adds global value"
    else:
        role_hits = [
            role
            for role, corr in by_role_outcome_correlation.items()
            if corr is not None and abs(corr) >= 0.05
        ]
        if rmse_delta is not None and rmse_delta < -NEGLIGIBLE_RMSE_RELATIVE:
            conclusion = "adds global value"
        elif is_negligible_rmse_delta(rmse_delta) and 0 < len(role_hits) < len(CIR_ROLES):
            conclusion = "adds role-specific value"

    return IncrementalFeatureDiagnosis(
        feature=feature,
        overall_validation_rmse_delta=rmse_delta,
        overall_validation_spearman_delta=spearman_delta,
        by_role_outcome_correlation=by_role_outcome_correlation,
        duelist_outcome_correlation=duelist_outcome_correlation,
        non_duelist_outcome_correlation=non_duelist_outcome_correlation,
        conclusion=conclusion,
        evidence=evidence,
    )


def materially_improves(candidate: FeatureSubsetResult, simpler: FeatureSubsetResult) -> bool:
    candidate_gap = candidate.role_bias_metrics.max_role_median_gap
    simpler_gap = simpler.role_bias_metrics.max_role_median_gap
    if (
        candidate_gap is not None
        and simpler_gap is not None
        and simpler_gap - candidate_gap >= MATERIAL_ROLE_GAP_IMPROVEMENT
    ):
        return True
    candidate_rho = candidate.validation_metrics.spearman
    simpler_rho = simpler.validation_metrics.spearman
    if (
        candidate_rho is not None
        and simpler_rho is not None
        and candidate_rho - simpler_rho >= MATERIAL_SPEARMAN_IMPROVEMENT
    ):
        return True
    return False


def within_rmse_slack(candidate_rmse: float | None, best_rmse: float | None) -> bool:
    if candidate_rmse is None or best_rmse is None:
        return False
    relative = abs(candidate_rmse - best_rmse) / max(best_rmse, 1e-9)
    return relative <= SELECTION_RMSE_RELATIVE_SLACK


def select_feature_subset(results: list[FeatureSubsetResult]) -> FeatureSubsetResult:
    """Pick a winner from validation RMSE only. Test metrics are ignored."""
    if not results:
        raise ValueError("No feature subsets to select from")

    def val_rmse(result: FeatureSubsetResult) -> float:
        return (
            result.validation_metrics.rmse
            if result.validation_metrics.rmse is not None
            else float("inf")
        )

    def val_r2(result: FeatureSubsetResult) -> float:
        return result.validation_metrics.r2 if result.validation_metrics.r2 is not None else -999.0

    def val_spearman(result: FeatureSubsetResult) -> float:
        return (
            result.validation_metrics.spearman
            if result.validation_metrics.spearman is not None
            else -999.0
        )

    ranked = sorted(
        results, key=lambda result: (val_rmse(result), -val_r2(result), -val_spearman(result))
    )
    best = ranked[0]
    similar = [result for result in ranked if within_rmse_slack(val_rmse(result), val_rmse(best))]
    simplest = min(similar, key=lambda result: result.number_of_features)
    if simplest.number_of_features < best.number_of_features and not materially_improves(
        best, simplest
    ):
        return simplest
    return best


def coefficient_signs(coefficients: dict[str, float]) -> dict[str, str]:
    signs: dict[str, str] = {}
    for name, value in coefficients.items():
        if value > 0:
            signs[name] = "+"
        elif value < 0:
            signs[name] = "-"
        else:
            signs[name] = "0"
    return signs


def decide_feature_dispositions(
    *,
    subset_by_name: dict[str, FeatureSubsetResult],
    residual_adr: ResidualAdrDiagnosis,
    kast: IncrementalFeatureDiagnosis,
    apr: IncrementalFeatureDiagnosis,
    opening: IncrementalFeatureDiagnosis,
    selected: FeatureSubsetResult,
) -> list[FeaturePruningDisposition]:
    combat = subset_by_name.get("combat_only")
    dispositions = [
        FeaturePruningDisposition(
            feature="kpr_residual",
            disposition="KEEP",
            reason="Core combat feature; retained in every serious candidate subset.",
        ),
        FeaturePruningDisposition(
            feature="negative_dpr_residual",
            disposition="KEEP",
            reason="Core combat feature; retained in every serious candidate subset.",
        ),
        _disposition_from_incremental(
            "residual_adr",
            selected,
            residual_adr_interpretation=residual_adr.interpretation,
            combat=combat,
            plus_name="combat_plus_residual_adr",
            subset_by_name=subset_by_name,
            incremental=None,
        ),
        _disposition_from_incremental(
            "apr_residual",
            selected,
            combat=combat,
            plus_name="combat_plus_apr",
            subset_by_name=subset_by_name,
            incremental=apr,
        ),
        _disposition_from_incremental(
            "kast_residual",
            selected,
            combat=combat,
            plus_name="combat_plus_kast",
            subset_by_name=subset_by_name,
            incremental=kast,
        ),
        _opening_disposition(opening, selected, combat, subset_by_name),
    ]
    return dispositions


def _opening_disposition(
    opening: IncrementalFeatureDiagnosis,
    selected: FeatureSubsetResult,
    combat: FeatureSubsetResult | None,
    subset_by_name: dict[str, FeatureSubsetResult],
) -> FeaturePruningDisposition:
    both = subset_by_name.get("combat_plus_opening")
    in_selected = any(
        name in selected.features
        for name in (
            "opening_frequency_residual",
            "opening_efficiency_adjusted",
        )
    )
    delta = None
    if combat is not None and both is not None:
        delta = relative_rmse_delta(
            combat.validation_metrics.rmse,
            both.validation_metrics.rmse,
        )
    role_gap_worse = _role_gap_worsens(combat, both)
    coef_text = ""
    if both is not None:
        parts = [
            f"{name}={both.coefficients.get(name, 0.0):+.4f}"
            for name in ("opening_frequency_residual", "opening_efficiency_adjusted")
        ]
        coef_text = " Coefficients: " + ", ".join(parts) + "."
    if in_selected:
        return FeaturePruningDisposition(
            feature="opening_frequency_residual / opening_efficiency_adjusted",
            disposition="KEEP",
            reason="; ".join(opening.evidence[:3]) or "Selected subset retains opening features.",
        )
    if opening.conclusion == "useful only for Duelists" and not role_gap_worse:
        return FeaturePruningDisposition(
            feature="opening_frequency_residual / opening_efficiency_adjusted",
            disposition="ROLE_SPECIFIC_CANDIDATE",
            reason=(
                "Opening features add little globally but retain a Duelist-only association. "
                + "; ".join(opening.evidence[:3])
            ),
        )
    if (
        role_gap_worse
        or is_negligible_rmse_delta(delta)
        or (delta is not None and abs(delta) <= SELECTION_RMSE_RELATIVE_SLACK)
    ):
        reason = "Opening features are not worth keeping after combat features."
        if delta is not None:
            reason = (
                f"{delta:+.2%} validation RMSE vs combat_only; "
                f"{opening.conclusion}; role-gap penalty={role_gap_worse}."
            )
        return FeaturePruningDisposition(
            feature="opening_frequency_residual / opening_efficiency_adjusted",
            disposition="REMOVE",
            reason=reason + coef_text,
        )
    return FeaturePruningDisposition(
        feature="opening_frequency_residual / opening_efficiency_adjusted",
        disposition="DIAGNOSE_FURTHER",
        reason="; ".join(opening.evidence[:3]) or opening.conclusion,
    )


def _role_gap_worsens(
    simpler: FeatureSubsetResult | None,
    larger: FeatureSubsetResult | None,
) -> bool:
    if simpler is None or larger is None:
        return False
    simple_gap = simpler.role_bias_metrics.max_role_median_gap
    large_gap = larger.role_bias_metrics.max_role_median_gap
    if simple_gap is None or large_gap is None:
        return False
    return large_gap - simple_gap >= MATERIAL_ROLE_GAP_IMPROVEMENT


def _disposition_from_incremental(
    feature: str,
    selected: FeatureSubsetResult,
    *,
    combat: FeatureSubsetResult | None,
    plus_name: str,
    subset_by_name: dict[str, FeatureSubsetResult],
    incremental: IncrementalFeatureDiagnosis | None,
    residual_adr_interpretation: str | None = None,
) -> FeaturePruningDisposition:
    plus = subset_by_name.get(plus_name)
    delta = None
    if combat is not None and plus is not None:
        delta = relative_rmse_delta(combat.validation_metrics.rmse, plus.validation_metrics.rmse)
    in_selected = feature in selected.features
    coef = plus.coefficients.get(feature, 0.0) if plus is not None else 0.0

    if feature == "residual_adr":
        if in_selected and residual_adr_interpretation == "unclear":
            return FeaturePruningDisposition(
                feature=feature,
                disposition="DIAGNOSE_FURTHER",
                reason=(
                    "Selected subset still includes residual ADR but the negative coefficient "
                    "mechanism is unclear."
                ),
            )
        if (
            not in_selected
            and residual_adr_interpretation in {"true negative conditional association", "unclear"}
        ) or (delta is not None and delta > 0):
            reason = f"Residual ADR diagnosis={residual_adr_interpretation}."
            if delta is not None:
                reason = f"{reason} Combat+ADR validation RMSE change={delta:+.2%}."
            return FeaturePruningDisposition(feature=feature, disposition="REMOVE", reason=reason)

    if incremental is not None and incremental.conclusion == "adds role-specific value":
        return FeaturePruningDisposition(
            feature=feature,
            disposition="ROLE_SPECIFIC_CANDIDATE",
            reason="; ".join(incremental.evidence[:3]) or incremental.conclusion,
        )
    if in_selected:
        reason = "Retained in the validation-selected subset."
        if incremental is not None and incremental.evidence:
            reason = "; ".join(incremental.evidence[:3])
        return FeaturePruningDisposition(feature=feature, disposition="KEEP", reason=reason)
    if (
        is_negligible_rmse_delta(delta)
        or (delta is not None and abs(delta) <= SELECTION_RMSE_RELATIVE_SLACK)
        or (incremental is not None and incremental.conclusion == "no meaningful incremental value")
    ):
        reason = "Within the 1% validation RMSE simplicity band after combat features."
        if delta is not None:
            reason = f"{delta:+.2%} validation RMSE vs combat_only; dropped by the simplicity rule."
        reason = f"{reason} Coefficient={coef:+.4f}."
        return FeaturePruningDisposition(feature=feature, disposition="REMOVE", reason=reason)
    return FeaturePruningDisposition(
        feature=feature,
        disposition="DIAGNOSE_FURTHER",
        reason="; ".join((incremental.evidence if incremental is not None else [])[:3])
        or "Evidence is mixed.",
    )


def recommend_cir_v02(
    selected: FeatureSubsetResult,
    *,
    shrinkage_k: float,
    context_label: str,
    reasons: list[str],
) -> CirV02FeatureRecommendation:
    features = set(selected.features)
    combat = [name for name in COMBAT_FEATURES if name in features]
    damage = ["residual_adr"] if "residual_adr" in features else []
    team = [name for name in ("apr_residual", "kast_residual") if name in features]
    opening = [
        name
        for name in ("opening_frequency_residual", "opening_efficiency_adjusted")
        if name in features
    ]
    return CirV02FeatureRecommendation(
        combat=combat,
        damage=damage,
        team=team,
        opening=opening,
        clutch="disabled",
        context=context_label,
        shrinkage_k=shrinkage_k,
        selected_subset=selected.name,
        reasons=reasons,
    )


def role_gap_summary(metrics: RoleBiasMetrics) -> dict[str, float | None]:
    return {
        "max_pairwise_role_median_gap": metrics.max_role_median_gap,
        "controller_vs_duelist": metrics.controller_vs_duelist_gap,
        "controller_vs_initiator": metrics.controller_vs_initiator_gap,
        "controller_vs_sentinel": metrics.controller_vs_sentinel_gap,
    }
