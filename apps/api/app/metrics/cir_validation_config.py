from __future__ import annotations

CIR_ROLES: tuple[str, ...] = ("Duelist", "Initiator", "Controller", "Sentinel")

SHRINKAGE_K_VALUES: tuple[float, ...] = (100.0, 250.0, 500.0, 750.0, 1000.0)

STABILITY_ROUND_THRESHOLDS: tuple[int, ...] = (100, 250, 500, 1000)

ABLATION_VARIANTS: dict[str, tuple[str, ...] | None] = {
    "full_model": tuple(),  # sentinel: use full feature set
    "without_clutch": ("clutch_rate_adjusted",),
    "without_kast": ("kast_residual",),
    "without_residual_adr": ("residual_adr",),
    "without_opening": ("opening_frequency_residual", "opening_efficiency_adjusted"),
    "without_team_features": ("apr_residual", "kast_residual"),
    "without_context_adjustment": None,  # special handling
}
