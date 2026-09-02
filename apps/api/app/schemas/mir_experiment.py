from pydantic import BaseModel, Field

from app.schemas.context_v2 import RoleBiasMetrics, SplitMetrics
from app.schemas.mir import EconomyFeatureAvailability, MirScore


class MirSubsetResult(BaseModel):
    name: str
    features: list[str] = Field(default_factory=list)
    number_of_features: int = 0
    ridge_alpha: float | None = None
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    coefficients: dict[str, float] = Field(default_factory=dict)
    coefficient_signs: dict[str, str] = Field(default_factory=dict)
    role_bias_metrics: RoleBiasMetrics = Field(default_factory=RoleBiasMetrics)
    t1_extra_coefficients: dict[str, float | None] = Field(default_factory=dict)
    t2_extra_coefficients: dict[str, float | None] = Field(default_factory=dict)


class MirRawVsUniqueComparison(BaseModel):
    signal: str
    raw_subset: str
    unique_subset: str
    raw_validation_rmse: float | None = None
    unique_validation_rmse: float | None = None
    combat_validation_rmse: float | None = None
    unique_improves_on_raw: bool = False
    unique_improves_on_combat: bool = False
    conclusion: str = ""
    evidence: list[str] = Field(default_factory=list)


class MirRoleFeatureStats(BaseModel):
    role: str
    mean_raw: float | None = None
    median_raw: float | None = None
    mean_unique: float | None = None
    median_unique: float | None = None
    sample_size: int = 0


class MirComponentEvidence(BaseModel):
    component: str
    disposition: str
    enabled: bool = False
    conclusion: str = ""
    evidence: list[str] = Field(default_factory=list)


class MirStabilityRow(BaseModel):
    subset: str
    round_threshold: int
    eligible_players: int = 0
    spearman_vs_full: float | None = None
    mean_absolute_mir_difference: float | None = None
    median_absolute_mir_difference: float | None = None


class MirMarginalExample(BaseModel):
    player_handle: str | None = None
    role: str | None = None
    map_name: str | None = None
    split: str | None = None
    prediction_full: float | None = None
    prediction_without_player: float | None = None
    marginal_contribution: float | None = None
    note: str = "model-based marginal contribution; not causal"


class MirRecommendation(BaseModel):
    decision: str = ""
    combat: list[str] = Field(default_factory=list)
    support: list[str] = Field(default_factory=list)
    opening: list[str] = Field(default_factory=list)
    economy: str = "disabled"
    context: str = ""
    shrinkage_k: float | None = None
    selected_subset: str | None = None
    readiness: str = "NOT_READY"
    reasons: list[str] = Field(default_factory=list)


class MirBaselineComparison(BaseModel):
    name: str
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    role_median_gap: float | None = None
    source: str = ""


class MirExperimentReport(BaseModel):
    context_configuration: dict[str, object] = Field(default_factory=dict)
    shrinkage_k: float
    economy: list[EconomyFeatureAvailability] = Field(default_factory=list)
    economy_enabled: bool = False
    residualizers: dict[str, object] = Field(default_factory=dict)
    subset_results: list[MirSubsetResult] = Field(default_factory=list)
    selected_subset: str | None = None
    raw_vs_unique: list[MirRawVsUniqueComparison] = Field(default_factory=list)
    component_evidence: list[MirComponentEvidence] = Field(default_factory=list)
    role_analysis: dict[str, list[MirRoleFeatureStats]] = Field(default_factory=dict)
    t1_t2_consistency: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    stability: list[MirStabilityRow] = Field(default_factory=list)
    marginal_examples: list[MirMarginalExample] = Field(default_factory=list)
    baselines: list[MirBaselineComparison] = Field(default_factory=list)
    recommendation: MirRecommendation = Field(default_factory=MirRecommendation)
    example_scores: list[MirScore] = Field(default_factory=list)
    preserved_metric_version: str = "v0.1-real-2026"
    persisted_mir_version: str | None = None
