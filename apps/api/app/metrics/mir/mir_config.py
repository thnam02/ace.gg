from __future__ import annotations

from app.metrics.cir_v01 import DEFAULT_RIDGE_ALPHAS, TRAIN_FRACTION, VALIDATION_FRACTION
from app.metrics.context_v2 import ContextV2Level, FeatureContextRule
from app.metrics.context_v2_config import CONTEXT_MODE_V2, ContextExperimentSpec

MIR_METRIC_NAME = "MIR"
MIR_V01_EXPERIMENTAL_VERSION = "v0.1-experimental-2026"

KPR_CONTEXT = "kpr_context_residual"
DPR_CONTEXT = "negative_dpr_context_residual"
SUPPORT_ASSIST = "support_assist_residual"
ROUND_PARTICIPATION = "round_participation_residual"
OPENING_FREQUENCY_UNIQUE = "opening_frequency_unique"
OPENING_EFFICIENCY_UNIQUE = "opening_efficiency_unique"

APR_CONTEXT = "apr_context_residual"
KAST_CONTEXT = "kast_context_residual"
OPENING_FREQUENCY_CONTEXT = "opening_frequency_context"
OPENING_EFFICIENCY_CONTEXT = "opening_efficiency_context"

COMBAT_FEATURES: tuple[str, ...] = (KPR_CONTEXT, DPR_CONTEXT)
SUPPORT_FEATURES: tuple[str, ...] = (SUPPORT_ASSIST, ROUND_PARTICIPATION)
OPENING_FEATURES: tuple[str, ...] = (OPENING_FREQUENCY_UNIQUE, OPENING_EFFICIENCY_UNIQUE)

MIR_CANDIDATE_FEATURES: tuple[str, ...] = COMBAT_FEATURES + SUPPORT_FEATURES + OPENING_FEATURES

ALL_MODEL_FEATURES: tuple[str, ...] = MIR_CANDIDATE_FEATURES + (
    APR_CONTEXT,
    KAST_CONTEXT,
    OPENING_FREQUENCY_CONTEXT,
    OPENING_EFFICIENCY_CONTEXT,
)

CIR_TO_MIR_COMBAT: dict[str, str] = {
    "kpr_residual": KPR_CONTEXT,
    "negative_dpr_residual": DPR_CONTEXT,
    "apr_residual": APR_CONTEXT,
    "kast_residual": KAST_CONTEXT,
    "opening_frequency_residual": OPENING_FREQUENCY_CONTEXT,
    "opening_efficiency_adjusted": OPENING_EFFICIENCY_CONTEXT,
}

DEFAULT_MIR_SHRINKAGE_K = 50.0
OPENING_EFFICIENCY_PRIOR_K = 8.0
SELECTION_RMSE_RELATIVE_SLACK = 0.01
MATERIAL_ROLE_GAP_DELTA = 2.0
MATERIAL_SPEARMAN_DELTA = 0.01
STABILITY_ROUND_THRESHOLDS: tuple[int, ...] = (100, 250, 500)
TIER_LABELS: tuple[str, ...] = ("T1", "T2")

MIR_RIDGE_ALPHAS = DEFAULT_RIDGE_ALPHAS
MIR_TRAIN_FRACTION = TRAIN_FRACTION
MIR_VALIDATION_FRACTION = VALIDATION_FRACTION


def combat_features() -> tuple[str, ...]:
    return COMBAT_FEATURES


def mir_context_rules() -> dict[str, FeatureContextRule]:
    """Role/agent/tier expectations. Hierarchy supplies parent shrinkage."""
    return {
        "kpr": FeatureContextRule("kpr", ContextV2Level.ROLE_TIER),
        "dpr": FeatureContextRule("dpr", ContextV2Level.ROLE_TIER),
        "apr": FeatureContextRule("apr", ContextV2Level.AGENT_TIER),
        "kast": FeatureContextRule("kast", ContextV2Level.ROLE_TIER),
        "opening_frequency": FeatureContextRule("opening_frequency", ContextV2Level.AGENT_TIER),
        "opening_efficiency": FeatureContextRule("opening_efficiency", ContextV2Level.AGENT_TIER),
        "residual_adr": FeatureContextRule("residual_adr", ContextV2Level.NONE),
        "clutch": FeatureContextRule("clutch", ContextV2Level.NONE),
    }


def mir_context_spec() -> ContextExperimentSpec:
    return ContextExperimentSpec(
        name="mir_context_v2",
        mode=CONTEXT_MODE_V2,
        lam=1.0,
        tau=500.0,
        hierarchical=True,
        rules=mir_context_rules(),
        simplicity_rank=5,
    )


def default_mir_subset_matrix(*, economy_enabled: bool = False) -> dict[str, tuple[str, ...]]:
    combat = COMBAT_FEATURES
    apr_u = (SUPPORT_ASSIST,)
    kast_u = (ROUND_PARTICIPATION,)
    of_u = (OPENING_FREQUENCY_UNIQUE,)
    oe_u = (OPENING_EFFICIENCY_UNIQUE,)
    support = SUPPORT_FEATURES
    opening = OPENING_FEATURES
    matrix: dict[str, tuple[str, ...]] = {
        "combat_only": combat,
        "combat_plus_apr_unique": combat + apr_u,
        "combat_plus_kast_unique": combat + kast_u,
        "combat_plus_support_unique": combat + support,
        "combat_plus_of_unique": combat + of_u,
        "combat_plus_oe_unique": combat + oe_u,
        "combat_plus_opening_unique": combat + opening,
        "combat_plus_support_opening_unique": combat + support + opening,
        "full_mir_candidate": combat + support + opening,
        "combat_plus_raw_apr": combat + (APR_CONTEXT,),
        "combat_plus_raw_kast": combat + (KAST_CONTEXT,),
        "combat_plus_raw_opening": combat + (OPENING_FREQUENCY_CONTEXT, OPENING_EFFICIENCY_CONTEXT),
    }
    if economy_enabled:
        matrix["combat_plus_economy_unique"] = combat
        matrix["full_mir_candidate"] = combat + support + opening
    return matrix
