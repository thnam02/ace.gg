from __future__ import annotations

CIR_METRIC_NAME = "CIR"
CIR_V01_VERSION = "v0.1"

CIR_V01_FEATURE_NAMES: tuple[str, ...] = (
    "kpr_residual",
    "negative_dpr_residual",
    "residual_adr",
    "opening_frequency_residual",
    "opening_efficiency_adjusted",
    "apr_residual",
    "kast_residual",
    "clutch_rate_adjusted",
)

CIR_V01_COMPONENTS: dict[str, tuple[str, ...]] = {
    "combat": ("kpr_residual", "negative_dpr_residual", "residual_adr"),
    "opening": ("opening_frequency_residual", "opening_efficiency_adjusted"),
    "team": ("apr_residual", "kast_residual"),
    "clutch": ("clutch_rate_adjusted",),
}

DEFAULT_RIDGE_ALPHAS: tuple[float, ...] = (
    0.01,
    0.1,
    1.0,
    10.0,
    100.0,
    1000.0,
)

DEFAULT_SHRINKAGE_K = 500.0
TRAIN_FRACTION = 0.7
VALIDATION_FRACTION = 0.15
