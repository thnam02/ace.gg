from __future__ import annotations

from app.metrics.cir_v01 import CIR_V01_FEATURE_NAMES
from app.metrics.derived import safe_ratio
from app.metrics.stats_engine import player_map_stats_to_raw
from app.models import PlayerMapStats
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


def missing_feature_names(features: dict[str, float | None]) -> list[str]:
    return [name for name in CIR_V01_FEATURE_NAMES if features.get(name) is None]


def extract_non_context_features(stats: PlayerMapStats) -> dict[str, float | None]:
    raw = player_map_stats_to_raw(stats)
    rounds = raw.rounds
    opening_duels = raw.first_kills + raw.first_deaths
    dpr = safe_ratio(raw.deaths, rounds)
    return {
        "kpr_residual": safe_ratio(raw.kills, rounds),
        "negative_dpr_residual": -dpr if dpr is not None else None,
        "residual_adr": raw.adr,
        "opening_frequency_residual": safe_ratio(opening_duels, rounds),
        "opening_efficiency_adjusted": safe_ratio(raw.first_kills, opening_duels),
        "apr_residual": safe_ratio(raw.assists, rounds),
        "kast_residual": raw.kast_pct,
        "clutch_rate_adjusted": (
            safe_ratio(raw.clutch_wins or 0, raw.clutch_attempts)
            if raw.clutch_attempts is not None and raw.clutch_attempts > 0
            else None
        ),
    }


def feature_vector(
    features: dict[str, float | None],
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> list[float | None]:
    return [features.get(name) for name in feature_names]
