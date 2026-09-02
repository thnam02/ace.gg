from pydantic import BaseModel, Field


class SplitMetrics(BaseModel):
    rmse: float | None = None
    mae: float | None = None
    r2: float | None = None
    spearman: float | None = None


class RoleBiasMetrics(BaseModel):
    medians: dict[str, float | None] = Field(default_factory=dict)
    means: dict[str, float | None] = Field(default_factory=dict)
    p10: dict[str, float | None] = Field(default_factory=dict)
    p90: dict[str, float | None] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    rounds: dict[str, int] = Field(default_factory=dict)
    max_role_median_gap: float | None = None
    controller_vs_duelist_gap: float | None = None
    controller_vs_initiator_gap: float | None = None
    controller_vs_sentinel_gap: float | None = None


class FeatureRoleDiagnosis(BaseModel):
    feature: str
    role: str
    raw_role_mean: float | None = None
    context_baseline_mean: float | None = None
    adjusted_role_mean: float | None = None
    adjusted_role_median: float | None = None
    sample_size: int = 0
    exposure: float = 0.0


class ControllerShiftDiagnosis(BaseModel):
    features: list[FeatureRoleDiagnosis] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    driving_features: list[str] = Field(default_factory=list)


class FeatureStatSummary(BaseModel):
    means: dict[str, float | None] = Field(default_factory=dict)
    variances: dict[str, float | None] = Field(default_factory=dict)
    correlations: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    coefficient_signs: dict[str, str] = Field(default_factory=dict)
    coefficient_magnitudes: dict[str, float] = Field(default_factory=dict)


class ContextExperimentResult(BaseModel):
    name: str
    configuration: dict[str, object] = Field(default_factory=dict)
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    role_bias_metrics: RoleBiasMetrics = Field(default_factory=RoleBiasMetrics)
    coefficients: dict[str, float] = Field(default_factory=dict)
    feature_stats: FeatureStatSummary = Field(default_factory=FeatureStatSummary)
    context_usage: dict[str, int] = Field(default_factory=dict)
    selected_lambda: float | None = None
    selected_tau: float | None = None
    selected_shrinkage_k: float | None = None
    ridge_alpha: float | None = None


class FeatureDisposition(BaseModel):
    feature: str
    disposition: str
    reason: str


class ContextV2Recommendation(BaseModel):
    decision: str = ""
    feature_rules: dict[str, str] = Field(default_factory=dict)
    selected_lambda: float | None = None
    selected_tau: float | None = None
    selected_shrinkage_k: float | None = None
    feature_dispositions: list[FeatureDisposition] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ContextV2ExperimentReport(BaseModel):
    experiments: list[ContextExperimentResult] = Field(default_factory=list)
    best_validation_configuration: str | None = None
    final_test_result: SplitMetrics = Field(default_factory=SplitMetrics)
    controller_diagnosis: ControllerShiftDiagnosis = Field(default_factory=ControllerShiftDiagnosis)
    shrinkage_k_results: list[dict[str, float | None]] = Field(default_factory=list)
    recommendations: ContextV2Recommendation = Field(
        default_factory=lambda: ContextV2Recommendation()
    )
    preserved_metric_version: str = "v0.1-real-2026"
