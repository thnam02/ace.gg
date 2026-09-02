from __future__ import annotations

from pydantic import BaseModel, Field


class CirTrainingGateResult(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    regression_failures: list[str] = Field(default_factory=list)


def _empty_gates() -> CirTrainingGateResult:
    return CirTrainingGateResult(passed=False)


class CirV02TrainingResult(BaseModel):
    metric_version_id: str | None = None
    name: str
    version: str
    status: str
    dry_run: bool = False
    maps_used: int = 0
    player_snapshots: int = 0
    reference_size: int = 0
    reference_mean: float = 0.0
    shrinkage_k: float = 50.0
    mu_kpr: float | None = None
    sigma_kpr: float | None = None
    mu_negative_dpr: float | None = None
    sigma_negative_dpr: float | None = None
    val_rmse: float | None = None
    test_rmse: float | None = None
    role_gap: float | None = None
    bootstrap_sign_flips: int | None = None
    sample_counts: dict[str, int] = Field(default_factory=dict)
    gates: CirTrainingGateResult = Field(default_factory=_empty_gates)
    context_expectations: list[dict[str, object]] = Field(default_factory=list)
    top_established: list[dict[str, object]] = Field(default_factory=list)
    cir_summary: dict[str, float | None] = Field(default_factory=dict)


class CirSnapshotRefreshResult(BaseModel):
    metric_version_id: str
    version: str
    player_snapshots: int
    sample_counts: dict[str, int] = Field(default_factory=dict)
    gates: CirTrainingGateResult = Field(default_factory=_empty_gates)
