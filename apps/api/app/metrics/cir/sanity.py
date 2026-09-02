from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from uuid import UUID

from app.metrics.cir.config import (
    MIN_TEAM_MAPS_FOR_REGRESSION_GATE,
    REGRESSION_RMSE_ABS_TOLERANCE,
    REGRESSION_ROLE_GAP_ABS_TOLERANCE,
    ROLE_GAP_TARGET,
    TEST_RMSE_TARGET,
    VAL_RMSE_TARGET,
)
from app.metrics.cir.reliability import sample_status_for_rounds
from app.metrics.cir.scoring import CirPlayerScore
from app.metrics.cir_standardization import StandardizationParams


def sanity_failures(
    *,
    players: Sequence[CirPlayerScore],
    standardization: StandardizationParams,
    reference_population: Sequence[float],
    context_rows: Sequence[dict[str, object]],
) -> list[str]:
    failures: list[str] = []
    if not reference_population:
        failures.append("reference distribution is empty")
    seen: set[UUID] = set()
    for player in players:
        if player.player_id in seen:
            failures.append(f"duplicate snapshot for player {player.player_id}")
        seen.add(player.player_id)
        if player.cir < 0 or player.cir > 100:
            failures.append(f"CIR out of bounds for {player.handle}: {player.cir}")
        if player.rounds <= 0:
            failures.append(f"non-positive rounds for {player.handle}")
        if player.maps <= 0:
            failures.append(f"non-positive maps for {player.handle}")
        expected_status = sample_status_for_rounds(player.rounds).value
        if player.sample_status != expected_status:
            failures.append(
                f"sample_status mismatch for {player.handle}: "
                f"{player.sample_status} != {expected_status}"
            )
        if not isfinite(player.raw_cir) or not isfinite(player.shrunk_raw_cir):
            failures.append(f"non-finite CIR latent for {player.handle}")
    for name, value in standardization.stds.items():
        if value <= 0:
            failures.append(f"standardization sigma for {name} is not positive")
        if not isfinite(value):
            failures.append(f"standardization sigma for {name} is not finite")
    for name, value in standardization.means.items():
        if not isfinite(value):
            failures.append(f"standardization mean for {name} is not finite")
    for row in context_rows:
        for key in ("shrunk_expected_kpr", "shrunk_expected_dpr", "exposure"):
            field_value = row.get(key)
            if isinstance(field_value, int | float) and not isfinite(float(field_value)):
                failures.append(f"non-finite context field {key} in {row.get('context')}")
    return failures


def regression_failures(
    *,
    val_rmse: float | None,
    test_rmse: float | None,
    role_gap: float | None,
    bootstrap_sign_flips: int | None,
    team_map_count: int,
) -> list[str]:
    if team_map_count < MIN_TEAM_MAPS_FOR_REGRESSION_GATE:
        return []
    failures: list[str] = []
    if val_rmse is None or abs(val_rmse - VAL_RMSE_TARGET) > REGRESSION_RMSE_ABS_TOLERANCE:
        failures.append(f"val RMSE {val_rmse} diverges from {VAL_RMSE_TARGET}")
    if test_rmse is None or abs(test_rmse - TEST_RMSE_TARGET) > REGRESSION_RMSE_ABS_TOLERANCE:
        failures.append(f"test RMSE {test_rmse} diverges from {TEST_RMSE_TARGET}")
    if role_gap is None or abs(role_gap - ROLE_GAP_TARGET) > REGRESSION_ROLE_GAP_ABS_TOLERANCE:
        failures.append(f"role median gap {role_gap} diverges from {ROLE_GAP_TARGET}")
    if bootstrap_sign_flips is not None and bootstrap_sign_flips != 0:
        failures.append(f"bootstrap sign flips = {bootstrap_sign_flips}, expected 0")
    return failures
