from __future__ import annotations

from app.metrics.cir_v01 import CIR_V01_FEATURE_NAMES
from app.schemas.context_features import ContextAdjustedFeatures


def extract_cir_input_features(adjusted: ContextAdjustedFeatures) -> dict[str, float | None]:
    negative_dpr: float | None = None
    if adjusted.dpr_residual is not None:
        negative_dpr = -adjusted.dpr_residual

    return {
        "kpr_residual": adjusted.kpr_residual,
        "negative_dpr_residual": negative_dpr,
        "residual_adr": adjusted.residual_adr,
        "opening_frequency_residual": adjusted.opening_frequency_residual,
        "opening_efficiency_adjusted": adjusted.opening_efficiency_adjusted,
        "apr_residual": adjusted.apr_residual,
        "kast_residual": adjusted.kast_residual,
        "clutch_rate_adjusted": adjusted.clutch_rate_adjusted,
    }


def feature_vector(
    features: dict[str, float | None],
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> list[float | None]:
    return [features.get(name) for name in feature_names]
