from pydantic import BaseModel, Field


class DatasetQualityReport(BaseModel):
    total_players: int = 0
    total_maps: int = 0
    total_player_map_observations: int = 0
    total_rounds: int = 0
    players_by_role: dict[str, int] = Field(default_factory=dict)
    observations_by_role: dict[str, int] = Field(default_factory=dict)
    observations_by_agent: dict[str, int] = Field(default_factory=dict)
    observations_by_tier: dict[str, int] = Field(default_factory=dict)
    median_rounds_per_player: float | None = None
    p25_rounds_per_player: float | None = None
    p75_rounds_per_player: float | None = None
    missing_kast: int = 0
    missing_clutch: int = 0
    missing_opening: int = 0
    missing_adr: int = 0
    context_fallback_counts: dict[str, int] = Field(default_factory=dict)
    context_fallback_percentages: dict[str, float] = Field(default_factory=dict)
    neutralized_missing_feature_counts: dict[str, int] = Field(default_factory=dict)


class RoleDistributionSummary(BaseModel):
    role: str
    count: int = 0
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    p10: float | None = None
    p25: float | None = None
    p75: float | None = None
    p90: float | None = None


class RoleBiasReport(BaseModel):
    distributions: list[RoleDistributionSummary] = Field(default_factory=list)
    pairwise_median_differences: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BaselineMetricReport(BaseModel):
    name: str
    split: str
    rmse: float | None = None
    mae: float | None = None
    r2: float | None = None
    spearman: float | None = None


class BaselineComparisonReport(BaseModel):
    metrics: list[BaselineMetricReport] = Field(default_factory=list)


class AblationResult(BaseModel):
    variant: str
    features_used: list[str] = Field(default_factory=list)
    ridge_alpha: float | None = None
    validation_rmse: float | None = None
    test_rmse: float | None = None
    validation_r2: float | None = None
    test_r2: float | None = None
    coefficient_changes: dict[str, float] = Field(default_factory=dict)
    rmse_delta_vs_full_validation: float | None = None
    rmse_delta_vs_full_test: float | None = None
    impact: str | None = None


class AblationReport(BaseModel):
    full_model_validation_rmse: float | None = None
    full_model_test_rmse: float | None = None
    results: list[AblationResult] = Field(default_factory=list)


class ShrinkageKReport(BaseModel):
    k: float
    score_std: float | None = None
    rank_stability_vs_reference: float | None = None
    validation_outcome_spearman: float | None = None


class ShrinkageAnalysisReport(BaseModel):
    reference_k: float
    recommended_k: float | None = None
    results: list[ShrinkageKReport] = Field(default_factory=list)


class StabilityThresholdReport(BaseModel):
    round_threshold: int
    eligible_players: int = 0
    spearman_rank_correlation: float | None = None
    mean_absolute_cir_difference: float | None = None
    median_absolute_cir_difference: float | None = None


class StabilityAnalysisReport(BaseModel):
    thresholds: list[StabilityThresholdReport] = Field(default_factory=list)


class MissingFeatureSplitReport(BaseModel):
    split: str
    complete_count: int = 0
    missing_count: int = 0
    validation_rmse_complete: float | None = None
    validation_rmse_missing: float | None = None


class MissingFeatureByGroupReport(BaseModel):
    group_type: str
    group_value: str
    feature: str
    missing_rate: float


class MissingFeatureAnalysisReport(BaseModel):
    missing_rates_by_feature: dict[str, float] = Field(default_factory=dict)
    splits: list[MissingFeatureSplitReport] = Field(default_factory=list)
    systematic_by_group: list[MissingFeatureByGroupReport] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CIRValidationResult(BaseModel):
    dataset_quality: DatasetQualityReport
    role_bias: RoleBiasReport
    baseline_comparison: BaselineComparisonReport
    ablation_results: AblationReport
    shrinkage_analysis: ShrinkageAnalysisReport
    stability_analysis: StabilityAnalysisReport
    missing_feature_analysis: MissingFeatureAnalysisReport
    recommendations: list[str] = Field(default_factory=list)
