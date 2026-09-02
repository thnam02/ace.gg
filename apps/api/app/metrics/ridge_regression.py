from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def fit_ridge(
    design_matrix: NDArray[np.float64],
    targets: NDArray[np.float64],
    alpha: float,
) -> tuple[float, NDArray[np.float64]]:
    n_features = design_matrix.shape[1]
    penalty = alpha * np.eye(n_features)
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(
        design_matrix.T @ design_matrix + penalty,
        design_matrix.T @ targets,
    )
    intercept = float(coefficients[0])
    weights = np.asarray(coefficients[1:], dtype=np.float64)
    return intercept, weights


def predict_ridge(
    design_matrix: NDArray[np.float64],
    intercept: float,
    weights: NDArray[np.float64],
) -> NDArray[np.float64]:
    return intercept + design_matrix[:, 1:] @ weights


def rmse(targets: NDArray[np.float64], predictions: NDArray[np.float64]) -> float:
    if len(targets) == 0:
        return 0.0
    return float(np.sqrt(np.mean((targets - predictions) ** 2)))


def r2_score(targets: NDArray[np.float64], predictions: NDArray[np.float64]) -> float | None:
    if len(targets) == 0:
        return None
    target_mean = float(np.mean(targets))
    ss_res = float(np.sum((targets - predictions) ** 2))
    ss_tot = float(np.sum((targets - target_mean) ** 2))
    if ss_tot == 0.0:
        return None
    return 1.0 - ss_res / ss_tot


def select_ridge_alpha(
    train_design: NDArray[np.float64],
    train_targets: NDArray[np.float64],
    validation_design: NDArray[np.float64],
    validation_targets: NDArray[np.float64],
    alphas: tuple[float, ...],
) -> float:
    best_alpha = alphas[0]
    best_rmse = float("inf")
    for alpha in alphas:
        intercept, weights = fit_ridge(train_design, train_targets, alpha)
        predictions = predict_ridge(validation_design, intercept, weights)
        score = rmse(validation_targets, predictions)
        if score < best_rmse:
            best_rmse = score
            best_alpha = alpha
    return best_alpha
