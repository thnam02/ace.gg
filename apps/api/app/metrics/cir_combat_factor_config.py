from __future__ import annotations

from app.metrics.cir_feature_pruning_config import SELECTION_RMSE_RELATIVE_SLACK
from app.metrics.cir_final_validation_config import (
    BOOTSTRAP_SEED,
    DEFAULT_BOOTSTRAP_ITERATIONS,
    FROZEN_COMBAT_FEATURES,
    FROZEN_LAMBDA,
    FROZEN_SHRINKAGE_K,
    FROZEN_TAU,
    KPR_FEATURE,
    LATER_EVENT_RMSE_RATIO_LIMIT,
    MIN_TRAIN_TEAM_MAPS,
    NEGATIVE_DPR_FEATURE,
    NESTED_TRAIN_FRACTION,
    PRIMARY_TRAIN_FRACTION,
    PRIMARY_VALIDATION_FRACTION,
    RANKING_ROUND_THRESHOLDS,
    RANKING_STABILITY_500_MIN,
    ROLE_GAP_FAILURE_THRESHOLD,
    SIGN_FLIP_FAILURE_RATE,
    TEMPORAL_SPLIT_GRID,
    frozen_context_spec,
)

TWO_FEATURE = "two_feature"
NEGATIVE_DPR_ONLY = "negative_dpr_only"
KPR_ONLY = "kpr_only"
NET_COMBAT_RATE = "net_combat_rate"
PCA_COMBAT_FACTOR = "pca_combat_factor"
EQUAL_WEIGHT = "equal_weight_combat"

NET_COMBAT_FEATURE = "net_combat_rate"
COMBAT_FACTOR_FEATURE = "combat_factor"
EQUAL_WEIGHT_FEATURE = "equal_weight_combat"
PC2_FEATURE = "combat_factor_pc2"

CANDIDATE_KINDS: tuple[str, ...] = (
    TWO_FEATURE,
    NEGATIVE_DPR_ONLY,
    KPR_ONLY,
    NET_COMBAT_RATE,
    PCA_COMBAT_FACTOR,
    EQUAL_WEIGHT,
)

LOEO_KINDS: tuple[str, ...] = (
    TWO_FEATURE,
    NEGATIVE_DPR_ONLY,
    NET_COMBAT_RATE,
    PCA_COMBAT_FACTOR,
    EQUAL_WEIGHT,
)

FEATURES_BY_KIND: dict[str, tuple[str, ...]] = {
    TWO_FEATURE: FROZEN_COMBAT_FEATURES,
    NEGATIVE_DPR_ONLY: (NEGATIVE_DPR_FEATURE,),
    KPR_ONLY: (KPR_FEATURE,),
    NET_COMBAT_RATE: (NET_COMBAT_FEATURE,),
    PCA_COMBAT_FACTOR: (COMBAT_FACTOR_FEATURE,),
    EQUAL_WEIGHT: (EQUAL_WEIGHT_FEATURE,),
}

SIMPLICITY_RANK: dict[str, int] = {
    NET_COMBAT_RATE: 0,
    EQUAL_WEIGHT: 1,
    PCA_COMBAT_FACTOR: 2,
    NEGATIVE_DPR_ONLY: 3,
    KPR_ONLY: 4,
    TWO_FEATURE: 5,
}

SELECTION_KEEP_TWO = "KEEP_TWO_FEATURE_COMBAT"
SELECTION_NDPR = "USE_NEGATIVE_DPR_ONLY"
SELECTION_NCR = "USE_NET_COMBAT_RATE"
SELECTION_PCA = "USE_PCA_COMBAT_FACTOR"
SELECTION_EQUAL = "USE_EQUAL_WEIGHT_COMBAT"
SELECTION_RETHINK = "RETHINK_COMBAT_MODEL"

SELECTION_BY_KIND: dict[str, str] = {
    TWO_FEATURE: SELECTION_KEEP_TWO,
    NEGATIVE_DPR_ONLY: SELECTION_NDPR,
    KPR_ONLY: SELECTION_RETHINK,
    NET_COMBAT_RATE: SELECTION_NCR,
    PCA_COMBAT_FACTOR: SELECTION_PCA,
    EQUAL_WEIGHT: SELECTION_EQUAL,
}

RMSE_SLACK = SELECTION_RMSE_RELATIVE_SLACK
PC1_DOMINANCE_THRESHOLD = 0.95
ROLE_GAP_VS_TWO_FEATURE_SLACK = 3.0
MATERIAL_ROLE_GAP_IMPROVEMENT = 2.0
CONSTRAINED_REGRESSION_FALLBACK = (
    "If no single-factor representation is both competitive and role-balanced, "
    "constrained regression (beta_KPR >= 0, beta_-DPR >= 0) remains a fallback "
    "research option. It is not implemented in this phase."
)

INTERPRETATIONS: dict[str, str] = {
    TWO_FEATURE: (
        "Reward context-adjusted kill production and context-adjusted death "
        "avoidance with independently learned weights."
    ),
    NEGATIVE_DPR_ONLY: (
        "Context-adjusted death avoidance / survival efficiency only. CIR would "
        "become a survival-only score."
    ),
    KPR_ONLY: "Context-adjusted kill production only.",
    NET_COMBAT_RATE: (
        "Net context-adjusted combat exchange per round: KPR residual plus "
        "negative-DPR residual (kills minus deaths, after context)."
    ),
    PCA_COMBAT_FACTOR: (
        "Dominant shared latent combat-performance axis formed from "
        "context-adjusted KPR and death avoidance. Sign is oriented so higher "
        "KPR and lower DPR raise CombatFactor."
    ),
    EQUAL_WEIGHT: (
        "Equal-weight average of standardized context-adjusted KPR and "
        "death-avoidance. Interpretable non-PCA single-factor baseline."
    ),
}

__all__ = [
    "BOOTSTRAP_SEED",
    "CANDIDATE_KINDS",
    "COMBAT_FACTOR_FEATURE",
    "CONSTRAINED_REGRESSION_FALLBACK",
    "DEFAULT_BOOTSTRAP_ITERATIONS",
    "EQUAL_WEIGHT",
    "EQUAL_WEIGHT_FEATURE",
    "FEATURES_BY_KIND",
    "FROZEN_COMBAT_FEATURES",
    "FROZEN_LAMBDA",
    "FROZEN_SHRINKAGE_K",
    "FROZEN_TAU",
    "INTERPRETATIONS",
    "KPR_FEATURE",
    "KPR_ONLY",
    "LATER_EVENT_RMSE_RATIO_LIMIT",
    "LOEO_KINDS",
    "MATERIAL_ROLE_GAP_IMPROVEMENT",
    "MIN_TRAIN_TEAM_MAPS",
    "NEGATIVE_DPR_FEATURE",
    "NEGATIVE_DPR_ONLY",
    "NESTED_TRAIN_FRACTION",
    "NET_COMBAT_FEATURE",
    "NET_COMBAT_RATE",
    "PC1_DOMINANCE_THRESHOLD",
    "PC2_FEATURE",
    "PCA_COMBAT_FACTOR",
    "PRIMARY_TRAIN_FRACTION",
    "PRIMARY_VALIDATION_FRACTION",
    "RANKING_ROUND_THRESHOLDS",
    "RANKING_STABILITY_500_MIN",
    "RMSE_SLACK",
    "ROLE_GAP_FAILURE_THRESHOLD",
    "ROLE_GAP_VS_TWO_FEATURE_SLACK",
    "SELECTION_BY_KIND",
    "SELECTION_EQUAL",
    "SELECTION_KEEP_TWO",
    "SELECTION_NCR",
    "SELECTION_NDPR",
    "SELECTION_PCA",
    "SELECTION_RETHINK",
    "SIGN_FLIP_FAILURE_RATE",
    "SIMPLICITY_RANK",
    "TEMPORAL_SPLIT_GRID",
    "TWO_FEATURE",
    "frozen_context_spec",
]
