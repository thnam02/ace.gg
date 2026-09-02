from __future__ import annotations

import pytest

from app.metrics.cir_features import extract_cir_input_features
from app.metrics.cir_round_diff import (
    actual_round_diff,
    expected_round_diff_team_a,
    outcome_residual,
)
from app.metrics.cir_scoring import (
    CIRModelCoefficients,
    apply_shrinkage,
    build_team_delta_vector,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_standardization import fit_standardization, standardize_features
from app.metrics.cir_v01 import CIR_V01_FEATURE_NAMES
from app.schemas.context_features import ContextAdjustedFeatures


def test_training_only_standardization_uses_train_stats() -> None:
    train_row = {name: 0.0 for name in CIR_V01_FEATURE_NAMES}
    train_row["kpr_residual"] = 0.1
    params = fit_standardization([train_row])
    eval_row = {name: None for name in CIR_V01_FEATURE_NAMES}
    eval_row["kpr_residual"] = 0.3
    standardized = standardize_features(eval_row, params)
    assert standardized["kpr_residual"] != 0.0


def test_negative_dpr_residual_sign() -> None:
    adjusted = ContextAdjustedFeatures(dpr_residual=0.2)
    features = extract_cir_input_features(adjusted)
    assert features["negative_dpr_residual"] == pytest.approx(-0.2)


def test_expected_round_diff_model() -> None:
    expected = expected_round_diff_team_a(0.75, 24)
    assert expected == pytest.approx(6.0)
    assert expected_round_diff_team_a(0.5, 24) == pytest.approx(0.0)


def test_outcome_residual() -> None:
    assert outcome_residual(13, 6.0) == pytest.approx(7.0)


def test_team_delta_aggregation() -> None:
    team_a = [{"kpr_residual": 1.0, "apr_residual": 0.5}]
    team_b = [{"kpr_residual": 0.5, "apr_residual": 0.2}]
    for name in CIR_V01_FEATURE_NAMES:
        team_a[0].setdefault(name, 0.0)
        team_b[0].setdefault(name, 0.0)
    deltas = build_team_delta_vector(team_a, team_b)
    assert deltas["kpr_residual"] == pytest.approx(0.5)


def test_raw_cir_and_components() -> None:
    coefficients = CIRModelCoefficients(
        intercept=0.0,
        coefficients={name: 1.0 for name in CIR_V01_FEATURE_NAMES},
    )
    standardized = {name: 0.1 for name in CIR_V01_FEATURE_NAMES}
    raw = compute_raw_cir(standardized, coefficients)
    assert raw == pytest.approx(0.8)


def test_round_weighted_player_aggregation() -> None:
    value = round_weighted_mean([(1.0, 10), (3.0, 30)])
    assert value == pytest.approx(2.5)


def test_shrinkage_moves_toward_reference_mean() -> None:
    shrunk = apply_shrinkage(2.0, 10, reference_mean=0.0, shrinkage_k=500.0)
    assert shrunk < 2.0
    assert shrunk > 0.0


def test_empirical_cdf_percentile() -> None:
    reference = [-1.0, 0.0, 1.0, 2.0]
    assert empirical_cdf(0.0, reference) == pytest.approx(50.0)


def test_missing_features_standardize_to_zero() -> None:
    params = fit_standardization([{name: 1.0 for name in CIR_V01_FEATURE_NAMES}])
    standardized = standardize_features({name: None for name in CIR_V01_FEATURE_NAMES}, params)
    assert all(value == 0.0 for value in standardized.values())


def test_actual_round_diff_from_scores() -> None:
    assert actual_round_diff(13, 8) == 5
    assert actual_round_diff(None, 8) is None
