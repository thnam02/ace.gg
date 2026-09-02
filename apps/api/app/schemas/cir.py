from pydantic import BaseModel, Field


class CIRSplitCounts(BaseModel):
    train_maps: int = 0
    validation_maps: int = 0
    test_maps: int = 0
    train_players: int = 0
    validation_players: int = 0
    test_players: int = 0


class CIRBaselineEvaluation(BaseModel):
    name: str
    rmse: float | None = None
    r2: float | None = None


class CIRTrainingEvaluation(BaseModel):
    train_rmse: float | None = None
    train_r2: float | None = None
    validation_rmse: float | None = None
    validation_r2: float | None = None
    test_rmse: float | None = None
    test_r2: float | None = None
    baselines: list[CIRBaselineEvaluation] = Field(default_factory=list)


class CIRPlayerScoreExample(BaseModel):
    player_id: str
    handle: str | None = None
    raw_cir: float | None = None
    shrunk_raw_cir: float | None = None
    cir: float | None = None
    rounds: int = 0
    maps_played: int = 0


class CIRTrainingResult(BaseModel):
    metric_version_id: str
    name: str
    version: str
    split_counts: CIRSplitCounts
    ridge_alpha: float
    intercept: float
    coefficients: dict[str, float]
    shrinkage_k: float
    reference_mean: float
    evaluation: CIRTrainingEvaluation
    example_scores: list[CIRPlayerScoreExample] = Field(default_factory=list)
