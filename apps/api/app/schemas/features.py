from pydantic import BaseModel, Field


class CIRFeatures(BaseModel):
    kpr: float | None = None
    dpr: float | None = None
    apr: float | None = None
    fkpr: float | None = None
    fdpr: float | None = None
    opening_frequency: float | None = None
    opening_efficiency: float | None = None
    adr: float | None = None
    expected_adr: float | None = None
    residual_adr: float | None = None
    kast: float | None = None
    raw_clutch_rate: float | None = None
    bayesian_clutch_rate: float | None = None
    clutch_attempts: int | None = None
    clutch_effective_sample_size: float | None = None


class MapCIRFeatures(BaseModel):
    match_map_id: str | None = None
    features: CIRFeatures


class PlayerCIRFeatures(BaseModel):
    player_id: str
    aggregate: CIRFeatures
    maps: list[MapCIRFeatures] = Field(default_factory=list)
