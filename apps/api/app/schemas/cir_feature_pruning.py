from pydantic import BaseModel, Field

from app.schemas.context_v2 import RoleBiasMetrics, SplitMetrics


class FeatureDistribution(BaseModel):
    feature: str
    group_type: str = "overall"
    group_value: str = "all"
    count: int = 0
    mean: float | None = None
    std: float | None = None
    p10: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    p90: float | None = None
    missing_pct: float = 0.0
    zero_or_neutralized_pct: float = 0.0
    correlation_with_outcome_residual: float | None = None


class FeatureCorrelationPair(BaseModel):
    left: str
    right: str
    correlation: float
    flagged: bool = False


class ResidualAdrModelFit(BaseModel):
    name: str = ""
    coefficients: dict[str, float] = Field(default_factory=dict)
    r2: float | None = None
    spearman: float | None = None
    sample_size: int = 0


class ResidualAdrBin(BaseModel):
    bin_index: int
    lower: float | None = None
    upper: float | None = None
    mean_feature: float | None = None
    mean_outcome: float | None = None
    count: int = 0


class ResidualAdrDiagnosis(BaseModel):
    univariate: ResidualAdrModelFit = Field(default_factory=ResidualAdrModelFit)
    controlling_for_combat: ResidualAdrModelFit = Field(default_factory=ResidualAdrModelFit)
    quadratic: ResidualAdrModelFit = Field(default_factory=ResidualAdrModelFit)
    by_role: dict[str, ResidualAdrModelFit] = Field(default_factory=dict)
    by_tier: dict[str, ResidualAdrModelFit] = Field(default_factory=dict)
    bins: list[ResidualAdrBin] = Field(default_factory=list)
    correlations_with_combat: dict[str, float | None] = Field(default_factory=dict)
    interpretation: str = ""
    evidence: list[str] = Field(default_factory=list)


class IncrementalFeatureDiagnosis(BaseModel):
    feature: str
    overall_validation_rmse_delta: float | None = None
    overall_validation_spearman_delta: float | None = None
    by_role_outcome_correlation: dict[str, float | None] = Field(default_factory=dict)
    duelist_outcome_correlation: float | None = None
    non_duelist_outcome_correlation: float | None = None
    conclusion: str = ""
    evidence: list[str] = Field(default_factory=list)


class FeatureSubsetResult(BaseModel):
    name: str
    features: list[str] = Field(default_factory=list)
    number_of_features: int = 0
    ridge_alpha: float | None = None
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    coefficient_signs: dict[str, str] = Field(default_factory=dict)
    coefficient_magnitudes: dict[str, float] = Field(default_factory=dict)
    coefficients: dict[str, float] = Field(default_factory=dict)
    role_bias_metrics: RoleBiasMetrics = Field(default_factory=RoleBiasMetrics)


class StabilityThresholdResult(BaseModel):
    subset: str
    round_threshold: int
    eligible_players: int = 0
    spearman_vs_full: float | None = None
    mean_absolute_cir_difference: float | None = None
    median_absolute_cir_difference: float | None = None


class FeaturePruningDisposition(BaseModel):
    feature: str
    disposition: str
    reason: str


class CirV02FeatureRecommendation(BaseModel):
    combat: list[str] = Field(default_factory=list)
    damage: list[str] = Field(default_factory=list)
    team: list[str] = Field(default_factory=list)
    opening: list[str] = Field(default_factory=list)
    clutch: str = "disabled"
    context: str = ""
    shrinkage_k: float | None = None
    selected_subset: str | None = None
    reasons: list[str] = Field(default_factory=list)


class FeaturePruningReport(BaseModel):
    context_configuration: dict[str, object] = Field(default_factory=dict)
    shrinkage_k: float
    feature_diagnostics: list[FeatureDistribution] = Field(default_factory=list)
    feature_correlations: list[FeatureCorrelationPair] = Field(default_factory=list)
    residual_adr_diagnosis: ResidualAdrDiagnosis = Field(default_factory=ResidualAdrDiagnosis)
    kast_diagnosis: IncrementalFeatureDiagnosis = Field(
        default_factory=lambda: IncrementalFeatureDiagnosis(feature="kast_residual")
    )
    apr_diagnosis: IncrementalFeatureDiagnosis = Field(
        default_factory=lambda: IncrementalFeatureDiagnosis(feature="apr_residual")
    )
    opening_diagnosis: IncrementalFeatureDiagnosis = Field(
        default_factory=lambda: IncrementalFeatureDiagnosis(feature="opening")
    )
    subset_results: list[FeatureSubsetResult] = Field(default_factory=list)
    selected_subset: str | None = None
    stability: list[StabilityThresholdResult] = Field(default_factory=list)
    dispositions: list[FeaturePruningDisposition] = Field(default_factory=list)
    recommendation: CirV02FeatureRecommendation = Field(default_factory=CirV02FeatureRecommendation)
    preserved_metric_version: str = "v0.1-real-2026"
