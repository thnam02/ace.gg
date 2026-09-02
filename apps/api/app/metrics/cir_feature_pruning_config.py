from __future__ import annotations

COMBAT_FEATURES: tuple[str, ...] = ("kpr_residual", "negative_dpr_residual")

PRUNING_CANDIDATE_FEATURES: tuple[str, ...] = (
    "kpr_residual",
    "negative_dpr_residual",
    "residual_adr",
    "apr_residual",
    "kast_residual",
    "opening_frequency_residual",
    "opening_efficiency_adjusted",
)

OPENING_FEATURES: tuple[str, ...] = (
    "opening_frequency_residual",
    "opening_efficiency_adjusted",
)

CORRELATION_FLAG_THRESHOLD = 0.7
NEGLIGIBLE_RMSE_RELATIVE = 0.002
SELECTION_RMSE_RELATIVE_SLACK = 0.01
MATERIAL_ROLE_GAP_IMPROVEMENT = 2.0
MATERIAL_SPEARMAN_IMPROVEMENT = 0.01
STABILITY_ROUND_THRESHOLDS: tuple[int, ...] = (100, 250, 500)
DEFAULT_PRUNING_SHRINKAGE_K = 50.0


def default_feature_subset_matrix() -> dict[str, tuple[str, ...]]:
    combat = COMBAT_FEATURES
    adr = ("residual_adr",)
    apr = ("apr_residual",)
    kast = ("kast_residual",)
    opening = OPENING_FEATURES
    full = combat + adr + apr + kast + opening
    return {
        "full_candidate": full,
        "combat_only": combat,
        "combat_plus_residual_adr": combat + adr,
        "combat_plus_apr": combat + apr,
        "combat_plus_kast": combat + kast,
        "combat_plus_apr_kast": combat + apr + kast,
        "combat_plus_opening": combat + opening,
        "combat_plus_opening_frequency": combat + ("opening_frequency_residual",),
        "combat_plus_opening_efficiency": combat + ("opening_efficiency_adjusted",),
        "combat_plus_apr_residual_adr": combat + apr + adr,
        "combat_plus_apr_kast_residual_adr": combat + apr + kast + adr,
        "full_without_opening": combat + adr + apr + kast,
        "full_without_kast": combat + adr + apr + opening,
        "full_without_residual_adr": combat + apr + kast + opening,
    }


def register_feature_subset(
    matrix: dict[str, tuple[str, ...]],
    name: str,
    features: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    updated = dict(matrix)
    updated[name] = features
    return updated
