from pydantic import BaseModel, Field

from app.schemas.cir_final_validation import (
    CoefficientSummary,
    LeakageAuditItem,
    NumericSummary,
    PlayerScoreUncertainty,
)
from app.schemas.context_v2 import RoleBiasMetrics, SplitMetrics


class CombatCandidatePrimary(BaseModel):
    kind: str
    display_name: str = ""
    interpretation: str = ""
    n_combat_dimensions: int = 1
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    ridge_alpha: float | None = None
    combat_coefficient: float | None = None
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    role_median_gap: float | None = None
    role_medians: dict[str, float | None] = Field(default_factory=dict)
    controller_vs_duelist: float | None = None
    controller_vs_initiator: float | None = None
    controller_vs_sentinel: float | None = None
    role_bias: RoleBiasMetrics = Field(default_factory=RoleBiasMetrics)
    competitive_rmse: bool = False


class PCALoadings(BaseModel):
    kpr_loading_pc1: float | None = None
    ndpr_loading_pc1: float | None = None
    kpr_loading_pc2: float | None = None
    ndpr_loading_pc2: float | None = None
    explained_pc1: float | None = None
    explained_pc2: float | None = None
    oriented: bool = False
    pc1_dominates: bool = False


class PC2Diagnostic(BaseModel):
    pc1_validation: SplitMetrics = Field(default_factory=SplitMetrics)
    pc1_pc2_validation: SplitMetrics = Field(default_factory=SplitMetrics)
    pc1_test: SplitMetrics = Field(default_factory=SplitMetrics)
    pc1_pc2_test: SplitMetrics = Field(default_factory=SplitMetrics)
    pc2_adds_value: bool = False
    discard_pc2: bool = True
    note: str = ""


class CombatTemporalResult(BaseModel):
    kind: str
    name: str
    train_fraction: float = 0.7
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    n_train_maps: int = 0
    n_val_maps: int = 0
    n_test_maps: int = 0
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    combat_coefficient: float | None = None
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    ridge_alpha: float | None = None
    role_median_gap: float | None = None
    kpr_loading_pc1: float | None = None
    ndpr_loading_pc1: float | None = None


class CombatRollingFold(BaseModel):
    kind: str
    train_events: list[str] = Field(default_factory=list)
    validation_event: str
    n_train_maps: int = 0
    n_val_maps: int = 0
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    combat_coefficient: float | None = None
    kpr_loading_pc1: float | None = None
    ndpr_loading_pc1: float | None = None
    role_median_gap: float | None = None


class CombatRollingSummary(BaseModel):
    kind: str
    folds: list[CombatRollingFold] = Field(default_factory=list)
    rmse: NumericSummary = Field(default_factory=NumericSummary)
    r2: NumericSummary = Field(default_factory=NumericSummary)
    spearman: NumericSummary = Field(default_factory=NumericSummary)


class CombatEventHoldout(BaseModel):
    kind: str
    event_id: str
    event_name: str
    vlr_event_id: int | None = None
    tier: str | None = None
    region: str | None = None
    n_train_maps: int = 0
    n_holdout_maps: int = 0
    holdout_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    combat_coefficient: float | None = None
    role_median_gap: float | None = None


class CombatTierResult(BaseModel):
    kind: str
    name: str
    n_train_maps: int = 0
    n_eval_maps: int = 0
    evaluation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    combat_coefficient: float | None = None
    coefficient_sign: str = "missing"
    kpr_coefficient: float | None = None
    negative_dpr_coefficient: float | None = None
    role_median_gap: float | None = None


class CombatBootstrapResult(BaseModel):
    kind: str
    iterations: int = 0
    block: str = "match"
    coefficient: CoefficientSummary = Field(default_factory=CoefficientSummary)
    interval_2_5: float | None = None
    interval_97_5: float | None = None
    rmse: NumericSummary = Field(default_factory=NumericSummary)
    r2: NumericSummary = Field(default_factory=NumericSummary)
    spearman: NumericSummary = Field(default_factory=NumericSummary)
    kpr_loading: CoefficientSummary = Field(default_factory=CoefficientSummary)
    ndpr_loading: CoefficientSummary = Field(default_factory=CoefficientSummary)
    explained_pc1: NumericSummary = Field(default_factory=NumericSummary)
    note: str = "Empirical model-stability intervals, not causal confidence intervals."


class CombatCoefficientStability(BaseModel):
    kind: str
    coefficient: CoefficientSummary = Field(default_factory=CoefficientSummary)
    kpr_loading: CoefficientSummary = Field(default_factory=CoefficientSummary)
    ndpr_loading: CoefficientSummary = Field(default_factory=CoefficientSummary)
    fold_count: int = 0


class CombatRankingComparison(BaseModel):
    kind: str
    round_threshold: int
    eligible_players: int = 0
    spearman_vs_full: float | None = None
    kendall_tau: float | None = None
    mean_absolute_rank_movement: float | None = None
    median_absolute_rank_movement: float | None = None
    top_10_retention: float | None = None
    top_25_retention: float | None = None
    top_50_retention: float | None = None
    spearman_vs_two_feature: float | None = None


class CombatPlayerUncertainty(PlayerScoreUncertainty):
    kind: str = ""
    mean_kpr_residual: float | None = None
    mean_negative_dpr_residual: float | None = None
    profile: str | None = None


class CombatBaselineRow(BaseModel):
    name: str
    validation_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    test_metrics: SplitMetrics = Field(default_factory=SplitMetrics)
    source: str = ""


class CombatFactorRecommendation(BaseModel):
    selection: str = "RETHINK_COMBAT_MODEL"
    winning_kind: str = "two_feature"
    readiness: str = "NOT_READY"
    persist: bool = False
    metric_name: str = "CIR"
    version: str = "v0.2-real-2026"
    specification: dict[str, object] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    constrained_regression_fallback: str = ""


class CombatFactorReport(BaseModel):
    frozen_context: dict[str, object] = Field(default_factory=dict)
    shrinkage_k: float = 50.0
    candidates: list[CombatCandidatePrimary] = Field(default_factory=list)
    pca: PCALoadings = Field(default_factory=PCALoadings)
    pc2_diagnostic: PC2Diagnostic = Field(default_factory=PC2Diagnostic)
    kpr_ndpr_train_correlation: float | None = None
    temporal: list[CombatTemporalResult] = Field(default_factory=list)
    rolling: list[CombatRollingSummary] = Field(default_factory=list)
    event_holdouts: list[CombatEventHoldout] = Field(default_factory=list)
    events_won_by_kind: dict[str, int] = Field(default_factory=dict)
    best_holdout: dict[str, str] = Field(default_factory=dict)
    worst_holdout: dict[str, str] = Field(default_factory=dict)
    events_won_by_single_factor: int = 0
    events_won_by_two_feature: int = 0
    events_won_by_vlr: int = 0
    events_won_by_kd: int = 0
    events_won_by_acs: int = 0
    tier_results: list[CombatTierResult] = Field(default_factory=list)
    coefficient_stability: list[CombatCoefficientStability] = Field(default_factory=list)
    bootstrap: list[CombatBootstrapResult] = Field(default_factory=list)
    ranking: list[CombatRankingComparison] = Field(default_factory=list)
    player_uncertainty: list[CombatPlayerUncertainty] = Field(default_factory=list)
    sensitive_profiles: list[CombatPlayerUncertainty] = Field(default_factory=list)
    baselines: list[CombatBaselineRow] = Field(default_factory=list)
    leakage_audit: list[LeakageAuditItem] = Field(default_factory=list)
    recommendation: CombatFactorRecommendation = Field(default_factory=CombatFactorRecommendation)
    preserved_metric_version: str = "v0.1-real-2026"
    persisted_version: str | None = None
