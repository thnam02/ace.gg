from pydantic import BaseModel, Field


class ContextAdjustedFeatures(BaseModel):
    kpr: float | None = None
    kpr_expected: float | None = None
    kpr_residual: float | None = None

    dpr: float | None = None
    dpr_expected: float | None = None
    dpr_residual: float | None = None

    apr: float | None = None
    apr_expected: float | None = None
    apr_residual: float | None = None

    opening_frequency: float | None = None
    opening_frequency_expected: float | None = None
    opening_frequency_residual: float | None = None

    opening_efficiency_raw: float | None = None
    opening_efficiency_adjusted: float | None = None

    kast: float | None = None
    kast_expected: float | None = None
    kast_residual: float | None = None

    residual_adr: float | None = None

    clutch_rate_raw: float | None = None
    clutch_rate_adjusted: float | None = None

    baseline_level: str | None = None
    reference_rounds: int | None = None
    reference_observations: int | None = None
    feature_baseline_levels: dict[str, str] = Field(default_factory=dict)


class MapContextFeatures(BaseModel):
    match_map_id: str | None = None
    features: ContextAdjustedFeatures


class PlayerContextFeatures(BaseModel):
    player_id: str
    maps: list[MapContextFeatures] = Field(default_factory=list)
