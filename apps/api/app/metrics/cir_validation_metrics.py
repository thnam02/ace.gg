from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.stats import kendalltau, spearmanr  # type: ignore[import-untyped]


def mae(targets: NDArray[np.float64], predictions: NDArray[np.float64]) -> float:
    if len(targets) == 0:
        return 0.0
    return float(np.mean(np.abs(targets - predictions)))


def spearman_correlation(
    x_values: NDArray[np.float64],
    y_values: NDArray[np.float64],
) -> float | None:
    if len(x_values) < 2 or len(y_values) < 2:
        return None
    if np.allclose(x_values, x_values[0]) or np.allclose(y_values, y_values[0]):
        return None
    result = spearmanr(x_values, y_values)
    return float(result.correlation) if result.correlation is not None else None


def kendall_tau_correlation(
    x_values: NDArray[np.float64],
    y_values: NDArray[np.float64],
) -> float | None:
    if len(x_values) < 2 or len(y_values) < 2:
        return None
    if np.allclose(x_values, x_values[0]) or np.allclose(y_values, y_values[0]):
        return None
    result = kendalltau(x_values, y_values)
    return float(result.correlation) if result.correlation is not None else None


def percentile(values: list[float] | list[int], pct: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.array(values, dtype=np.float64), pct))


def distribution_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "std": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
        }
    array = np.array(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "std": float(np.std(array)),
        "p10": percentile(values, 10),
        "p25": percentile(values, 25),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
    }


def rank_stability(rank_a: dict[str, int], rank_b: dict[str, int]) -> float | None:
    shared = [player_id for player_id in rank_a if player_id in rank_b]
    if len(shared) < 2:
        return None
    a_ranks = np.array([rank_a[player_id] for player_id in shared], dtype=np.float64)
    b_ranks = np.array([rank_b[player_id] for player_id in shared], dtype=np.float64)
    return spearman_correlation(a_ranks, b_ranks)
