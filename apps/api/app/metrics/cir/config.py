from __future__ import annotations

from enum import StrEnum

from app.metrics.cir_v01 import CIR_METRIC_NAME
from app.metrics.context_v2 import ContextV2Level, FeatureContextRule
from app.metrics.context_v2_config import CONTEXT_MODE_V2, ContextExperimentSpec

CIR_NAME = CIR_METRIC_NAME
CIR_V02_VERSION = "v0.2-real-2026"
CIR_V03_VERSION = "v0.3-vct-2026"
CIR_V02_FEATURE_NAMES: tuple[str, ...] = ("kpr_residual", "negative_dpr_residual")
KPR_FEATURE = "kpr_residual"
NEGATIVE_DPR_FEATURE = "negative_dpr_residual"

LAMBDA = 1.0
TAU = 500.0
SHRINKAGE_K = 50.0

COMBAT_FACTOR_TYPE = "equal_weight_standardized"
COMBAT_WEIGHT = 0.5
PCA_UNIT = 2.0**-0.5
VALIDATED_PC1_LOADINGS: tuple[float, float] = (PCA_UNIT, PCA_UNIT)

LOW_SAMPLE_ROUNDS = 100
ESTABLISHED_ROUNDS = 250
DEFAULT_PUBLIC_MIN_ROUNDS = ESTABLISHED_ROUNDS

CONTEXT_DIMENSIONS: tuple[str, ...] = ("role", "tier")
ELIGIBLE_MAP_DEFINITION = (
    "Complete maps only; empty and incomplete maps excluded; "
    "unknown-agent maps excluded; unresolved identity rows excluded."
)

PUBLIC_DESCRIPTION = (
    "CIR measures context-adjusted combat performance "
    "by combining a player's kill production and death avoidance "
    "relative to players in comparable roles and competitive tiers. "
    "Scores are adjusted for sample size "
    "and expressed as percentiles against the reference population."
)
PUBLIC_TOOLTIP = (
    "CIR 90 means the player's validated combat performance "
    "ranks around the 90th percentile of the reference population."
)
PUBLIC_INTERPRETATION = (
    "CIR combines context-adjusted kill production "
    "and death avoidance with equal weight after standardization."
)

# Scoring a MetricVersion is not retraining. Frozen v0.2 parameters stay immutable.
# New seasons require a new version such as CIR v0.3-2027.
SCORING_IS_NOT_RETRAINING = True

VAL_RMSE_TARGET = 2.239
TEST_RMSE_TARGET = 2.375
ROLE_GAP_TARGET = 1.07
REGRESSION_RMSE_ABS_TOLERANCE = 0.08
REGRESSION_ROLE_GAP_ABS_TOLERANCE = 0.35
MIN_TEAM_MAPS_FOR_REGRESSION_GATE = 50


class MetricVersionStatus(StrEnum):
    RESEARCH = "RESEARCH"
    VALIDATED = "VALIDATED"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"


class SampleStatus(StrEnum):
    LOW_SAMPLE = "LOW_SAMPLE"
    PROVISIONAL = "PROVISIONAL"
    ESTABLISHED = "ESTABLISHED"


class ReliabilityLabel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def production_context_spec() -> ContextExperimentSpec:
    """Frozen Context v2 for CIR v0.2: role+tier combat, lambda=1, tau=500."""
    return ContextExperimentSpec(
        name="cir_v02_context_v2",
        mode=CONTEXT_MODE_V2,
        lam=LAMBDA,
        tau=TAU,
        hierarchical=True,
        rules={
            "kpr": FeatureContextRule("kpr", ContextV2Level.ROLE_TIER),
            "dpr": FeatureContextRule("dpr", ContextV2Level.ROLE_TIER),
        },
        simplicity_rank=5,
    )
