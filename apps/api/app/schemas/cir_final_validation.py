from pydantic import BaseModel, Field

from app.schemas.context_v2 import SplitMetrics


class NumericSummary(BaseModel):
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    p05: float | None = None
    p25: float | None = None
    p75: float | None = None
    p95: float | None = None
    count: int = 0


class CoefficientSummary(NumericSummary):
    sign_flip_count: int = 0
    positive_share: float | None = None


class TemporalSplitResult(BaseModel):
    name: str
    train_fraction: float = 0.7
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    train_period_start: str | None = None
    train_period_end: str | None = None
    validation_period_start: str | None = None
    validation_period_end: str | None = None
    test_period_start: str | None = None
    test_period_end: str | None = None
    n_train_maps: int = 0
    n_val_maps: int = 0
    n_test_maps: int = 0
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    ridge_alpha: float | None = None
    role_median_gap: float | None = None
    flagged: bool = False
    flag_reason: str | None = None


class RollingFoldResult(BaseModel):
    train_events: list[str] = Field(default_factory=list)
    validation_event: str
    n_train_maps: int = 0
    n_val_maps: int = 0
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    ridge_alpha: float | None = None
    role_median_gap: float | None = None


class RollingValidationSummary(BaseModel):
    folds: list[RollingFoldResult] = Field(default_factory=list)
    rmse: NumericSummary = Field(default_factory=NumericSummary)
    mae: NumericSummary = Field(default_factory=NumericSummary)
    r2: NumericSummary = Field(default_factory=NumericSummary)
    spearman: NumericSummary = Field(default_factory=NumericSummary)


class EventHoldoutResult(BaseModel):
    event_id: str
    event_name: str
    vlr_event_id: int | None = None
    tier: str | None = None
    region: str | None = None
    n_train_maps: int = 0
    n_holdout_maps: int = 0
    holdout_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    ridge_alpha: float | None = None
    role_median_gap: float | None = None
    degraded: bool = False
    best_baseline: str | None = None


class TierResult(BaseModel):
    name: str
    n_train_maps: int = 0
    n_eval_maps: int = 0
    evaluation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    coefficient_signs: dict[str, str] = Field(default_factory=dict)
    ridge_alpha: float | None = None
    role_median_gap: float | None = None


class RegionResult(BaseModel):
    region: str
    maps: int = 0
    players: int = 0
    rounds: int = 0
    evaluation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    mean_cir: float | None = None
    median_cir: float | None = None
    role_median_gap: float | None = None
    small_sample: bool = False


class RoleResult(BaseModel):
    role: str
    players: int = 0
    maps: int = 0
    rounds: int = 0
    mean_cir: float | None = None
    median_cir: float | None = None
    std: float | None = None
    p10: float | None = None
    p25: float | None = None
    p75: float | None = None
    p90: float | None = None
    outcome_correlation: float | None = None


class BootstrapResult(BaseModel):
    iterations: int = 0
    block: str = "match"
    kpr: CoefficientSummary = Field(default_factory=CoefficientSummary)
    negative_dpr: CoefficientSummary = Field(default_factory=CoefficientSummary)
    rmse: NumericSummary = Field(default_factory=NumericSummary)
    r2: NumericSummary = Field(default_factory=NumericSummary)
    spearman: NumericSummary = Field(default_factory=NumericSummary)
    kpr_interval_2_5: float | None = None
    kpr_interval_97_5: float | None = None
    negative_dpr_interval_2_5: float | None = None
    negative_dpr_interval_97_5: float | None = None
    note: str = "Empirical model-stability intervals, not causal confidence intervals."


class RankingStabilityResult(BaseModel):
    comparison: str
    round_threshold: int
    eligible_players: int = 0
    spearman: float | None = None
    kendall_tau: float | None = None
    mean_absolute_rank_movement: float | None = None
    median_absolute_rank_movement: float | None = None
    top_10_retention: float | None = None
    top_25_retention: float | None = None
    top_50_retention: float | None = None


class PlayerScoreUncertainty(BaseModel):
    player_id: str
    handle: str | None = None
    rounds: int = 0
    cir_median: float | None = None
    cir_p05: float | None = None
    cir_p95: float | None = None
    rank_median: float | None = None
    rank_p05: float | None = None
    rank_p95: float | None = None


class SampleSizeResult(BaseModel):
    round_threshold: int
    eligible_players: int = 0
    spearman_vs_full: float | None = None
    mean_absolute_cir_difference: float | None = None
    median_absolute_cir_difference: float | None = None
    mean_absolute_rank_movement: float | None = None


class CoefficientStabilityResult(BaseModel):
    kpr: CoefficientSummary = Field(default_factory=CoefficientSummary)
    negative_dpr: CoefficientSummary = Field(default_factory=CoefficientSummary)
    ridge_alpha: NumericSummary = Field(default_factory=NumericSummary)
    fold_count: int = 0


class LeakageAuditItem(BaseModel):
    name: str
    fit_scope: str
    earliest_date: str | None = None
    latest_date: str | None = None
    notes: str = ""


class BaselineExactComparison(BaseModel):
    name: str
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    role_median_gap: float | None = None
    source: str = ""


class CombatRedundancyResult(BaseModel):
    kpr_only: SplitMetrics = Field(default_factory=SplitMetrics)
    negative_dpr_only: SplitMetrics = Field(default_factory=SplitMetrics)
    both: SplitMetrics = Field(default_factory=SplitMetrics)
    kpr_only_test: SplitMetrics = Field(default_factory=SplitMetrics)
    negative_dpr_only_test: SplitMetrics = Field(default_factory=SplitMetrics)
    both_test: SplitMetrics = Field(default_factory=SplitMetrics)
    ranking_correlation_kpr_vs_both: float | None = None
    ranking_correlation_dpr_vs_both: float | None = None
    role_gap_kpr_only: float | None = None
    role_gap_dpr_only: float | None = None
    role_gap_both: float | None = None
    incremental_value: bool = False
    conclusion: str = ""


class AggregationSanityResult(BaseModel):
    sum_validation: SplitMetrics = Field(default_factory=SplitMetrics)
    mean_validation: SplitMetrics = Field(default_factory=SplitMetrics)
    ranking_spearman: float | None = None
    conclusion: str = ""


class ContextSensitivityResult(BaseModel):
    name: str
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    role_median_gap: float | None = None
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None


class TargetSensitivityResult(BaseModel):
    elo_residual: SplitMetrics = Field(default_factory=SplitMetrics)
    raw_round_diff: SplitMetrics = Field(default_factory=SplitMetrics)
    ranking_spearman: float | None = None
    kpr_coefficient_elo: float | None = None
    kpr_coefficient_raw: float | None = None
    role_gap_elo: float | None = None
    role_gap_raw: float | None = None
    flagged: bool = False
    conclusion: str = ""


class FailureConditionAudit(BaseModel):
    passed: bool = True
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PublicRankingRecommendation(BaseModel):
    minimum_rounds: int = 250
    low_sample_max_rounds: int = 99
    provisional_max_rounds: int = 249
    established_min_rounds: int = 250
    labels: dict[str, str] = Field(default_factory=dict)
    reliability: str = ""
    reasons: list[str] = Field(default_factory=list)


class CIRFinalValidationRecommendation(BaseModel):
    readiness: str = "NOT_READY"
    persist: bool = False
    metric_name: str = "CIR"
    version: str = "v0.2-real-2026"
    features: list[str] = Field(default_factory=list)
    context: str = ""
    shrinkage_k: float = 50.0
    scale: str = "empirical percentile"
    ranking: PublicRankingRecommendation = Field(default_factory=PublicRankingRecommendation)
    reasons: list[str] = Field(default_factory=list)


class CIRFinalValidationReport(BaseModel):
    frozen_features: list[str] = Field(default_factory=list)
    context_configuration: dict[str, object] = Field(default_factory=dict)
    shrinkage_k: float = 50.0
    primary: TemporalSplitResult = Field(
        default_factory=lambda: TemporalSplitResult(name="primary")
    )
    temporal_splits: list[TemporalSplitResult] = Field(default_factory=list)
    rolling: RollingValidationSummary = Field(default_factory=RollingValidationSummary)
    event_holdouts: list[EventHoldoutResult] = Field(default_factory=list)
    best_generalized_event: str | None = None
    worst_generalized_event: str | None = None
    tier_results: list[TierResult] = Field(default_factory=list)
    tier_generalization: str = "TIER_GENERALIZATION_UNSTABLE"
    region_results: list[RegionResult] = Field(default_factory=list)
    role_results: list[RoleResult] = Field(default_factory=list)
    role_median_gap: float | None = None
    coefficient_stability: CoefficientStabilityResult = Field(
        default_factory=CoefficientStabilityResult
    )
    bootstrap: BootstrapResult = Field(default_factory=BootstrapResult)
    ranking_stability: list[RankingStabilityResult] = Field(default_factory=list)
    player_uncertainty: list[PlayerScoreUncertainty] = Field(default_factory=list)
    sample_size: list[SampleSizeResult] = Field(default_factory=list)
    target_sensitivity: TargetSensitivityResult = Field(default_factory=TargetSensitivityResult)
    context_sensitivity: list[ContextSensitivityResult] = Field(default_factory=list)
    combat_redundancy: CombatRedundancyResult = Field(default_factory=CombatRedundancyResult)
    aggregation_sanity: AggregationSanityResult = Field(default_factory=AggregationSanityResult)
    baselines: list[BaselineExactComparison] = Field(default_factory=list)
    events_won_by_cir: int = 0
    events_won_by_kd: int = 0
    events_won_by_acs: int = 0
    events_won_by_vlr: int = 0
    leakage_audit: list[LeakageAuditItem] = Field(default_factory=list)
    failure_audit: FailureConditionAudit = Field(default_factory=FailureConditionAudit)
    recommendation: CIRFinalValidationRecommendation = Field(
        default_factory=CIRFinalValidationRecommendation
    )
    preserved_metric_version: str = "v0.1-real-2026"
    persisted_version: str | None = None
