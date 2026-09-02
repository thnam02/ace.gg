from __future__ import annotations

from app.metrics.cir_feature_pruning_config import COMBAT_FEATURES, SELECTION_RMSE_RELATIVE_SLACK
from app.metrics.cir_v01 import TRAIN_FRACTION, VALIDATION_FRACTION
from app.metrics.context_v2_config import ContextExperimentSpec, recommended_context_v2_spec

CIR_V02_RECOMMENDED_VERSION = "v0.2-real-2026"
FROZEN_COMBAT_FEATURES: tuple[str, ...] = COMBAT_FEATURES
KPR_FEATURE = "kpr_residual"
NEGATIVE_DPR_FEATURE = "negative_dpr_residual"

FROZEN_LAMBDA = 1.0
FROZEN_TAU = 500.0
FROZEN_SHRINKAGE_K = 50.0

TEMPORAL_SPLIT_GRID: tuple[tuple[float, float], ...] = (
    (0.60, 0.20),
    (0.65, 0.175),
    (0.70, 0.15),
    (0.75, 0.125),
    (0.80, 0.10),
)

NESTED_TRAIN_FRACTION = 0.85
DEFAULT_BOOTSTRAP_ITERATIONS = 200
BOOTSTRAP_SEED = 42
MIN_TRAIN_TEAM_MAPS = 2
SMALL_REGION_MAPS = 20
ROLE_GAP_FAILURE_THRESHOLD = 15.0
SIGN_FLIP_FAILURE_RATE = 0.10
CROSS_TIER_RMSE_RATIO_LIMIT = 1.5
LATER_EVENT_RMSE_RATIO_LIMIT = 1.5
RANKING_STABILITY_500_MIN = 0.85
INCREMENTAL_FEATURE_SLACK = SELECTION_RMSE_RELATIVE_SLACK
SAMPLE_SIZE_THRESHOLDS: tuple[int, ...] = (50, 100, 250, 500)
RANKING_ROUND_THRESHOLDS: tuple[int, ...] = (100, 250, 500)
TOP_N_RETENTION: tuple[int, ...] = (10, 25, 50)
REGION_LABELS: tuple[str, ...] = ("Americas", "EMEA", "Pacific", "China", "NA", "INTL")

PRIMARY_TRAIN_FRACTION = TRAIN_FRACTION
PRIMARY_VALIDATION_FRACTION = VALIDATION_FRACTION


def frozen_context_spec() -> ContextExperimentSpec:
    return recommended_context_v2_spec()
