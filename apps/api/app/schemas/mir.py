from pydantic import BaseModel, Field


class MirComponentBreakdown(BaseModel):
    name: str
    raw_value: float | None = None
    standardized_value: float | None = None
    coefficient_contribution: float | None = None
    enabled: bool = False
    exposure_rounds: int = 0
    confidence: float | None = None


class MirScore(BaseModel):
    overall_mir: float | None = None
    raw_mir: float | None = None
    shrunk_mir: float | None = None
    percentile: float | None = None
    combat_component: float | None = None
    support_component: float | None = None
    opening_component: float | None = None
    economy_component: float | None = None
    rounds: int = 0
    maps: int = 0
    reliability: float | None = None
    sample_weight: float | None = None
    enabled_components: list[str] = Field(default_factory=list)
    metric_version: str | None = None


class EconomyFeatureAvailability(BaseModel):
    field: str
    source: str
    coverage: float = 0.0
    granularity: str = "unavailable"
    historical_availability: str = "none"
    missing_pct: float = 100.0
    usable_for_mir: bool = False
    notes: str = ""
