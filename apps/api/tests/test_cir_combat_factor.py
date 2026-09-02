from __future__ import annotations

import numpy as np
import pytest

from app.metrics.cir_combat_factor import (
    CombatCandidateSnapshot,
    combat_factor_readiness,
    competitive_rmse,
    equal_weight_combat,
    fit_combat_pca,
    net_combat_rate,
    orient_loadings,
    pc1_captures_shared_combat,
    pc2_adds_validation_value,
    recommended_spec,
    role_gap_acceptable,
    select_combat_parameterization,
    transform_combat_pca,
)
from app.metrics.cir_combat_factor_config import (
    CANDIDATE_KINDS,
    EQUAL_WEIGHT,
    FROZEN_COMBAT_FEATURES,
    FROZEN_LAMBDA,
    FROZEN_SHRINKAGE_K,
    FROZEN_TAU,
    KPR_ONLY,
    NEGATIVE_DPR_ONLY,
    NET_COMBAT_RATE,
    PCA_COMBAT_FACTOR,
    SELECTION_KEEP_TWO,
    SELECTION_NCR,
    SELECTION_PCA,
    SELECTION_RETHINK,
    TWO_FEATURE,
    frozen_context_spec,
)
from app.metrics.cir_final_validation import top_n_retention
from app.metrics.cir_final_validation_config import CIR_V02_RECOMMENDED_VERSION
from app.metrics.cir_standardization import fit_standardization, standardize_features
from app.metrics.cir_v01 import CIR_V01_VERSION
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION


def _snap(**overrides: object) -> CombatCandidateSnapshot:
    base = CombatCandidateSnapshot(
        kind=TWO_FEATURE,
        val_rmse=2.235,
        role_gap=5.6,
        bootstrap_p025=-0.07,
        bootstrap_sign_flips=15,
        bootstrap_draws=200,
        ranking_spearman_250=0.87,
        ranking_spearman_500=0.93,
        coefficient_positive=True,
        temporal_collapse=False,
        tier_sign_stable=True,
        baseline_advantage=True,
    )
    data = base.__dict__.copy()
    data.update(overrides)
    return CombatCandidateSnapshot(**data)


def test_net_combat_rate_does_not_subtract_twice() -> None:
    kpr = 0.20
    dpr_residual = 0.05
    negative_dpr = -dpr_residual
    ncr = net_combat_rate(kpr, negative_dpr)
    assert ncr == pytest.approx(0.15)
    assert ncr != kpr - negative_dpr
    assert net_combat_rate(None, 0.1) is None
    assert net_combat_rate(0.1, None) is None


def test_equal_weight_is_average_of_standardized_signals() -> None:
    assert equal_weight_combat(2.0, 0.0) == 1.0
    assert equal_weight_combat(-1.0, 1.0) == 0.0


def test_standardization_is_train_only() -> None:
    train = [{"net_combat_rate": float(index)} for index in range(4)]
    val = [{"net_combat_rate": 100.0}]
    params = fit_standardization(train, feature_names=("net_combat_rate",))
    z_train = [standardize_features(row, params, ("net_combat_rate",)) for row in train]
    z_val = standardize_features(val[0], params, ("net_combat_rate",))
    assert abs(sum(row["net_combat_rate"] for row in z_train)) < 1e-9
    assert z_val["net_combat_rate"] > 10


def test_pca_train_only_and_frozen_transform() -> None:
    train = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]], dtype=np.float64)
    pca = fit_combat_pca(train)
    holdout = np.array([[10.0, 10.0]], dtype=np.float64)
    pc1, _pc2 = transform_combat_pca(holdout, pca)
    leaked = fit_combat_pca(np.vstack([train, holdout]))
    assert pca.mean_kpr != leaked.mean_kpr
    train_pc1, _ = transform_combat_pca(train, pca)
    assert abs(float(np.mean(train_pc1))) < 1e-9
    assert pc1[0] > max(train_pc1)
    assert pca.explained_pc1 + pca.explained_pc2 == 1.0 or pca.explained_pc1 >= 0.99


def test_pca_sign_orientation_is_deterministic() -> None:
    matrix = np.array([[-1.0, -1.0], [-2.0, -2.0], [-3.0, -3.0]], dtype=np.float64)
    pca = fit_combat_pca(matrix)
    assert pca.kpr_loading_pc1 > 0
    assert pca.ndpr_loading_pc1 > 0
    assert fit_combat_pca(matrix) == fit_combat_pca(matrix)
    flipped, did_flip = orient_loadings(np.array([-0.7, -0.7]))
    assert did_flip is True
    assert float(np.sum(flipped)) > 0


def test_pca_explained_variance_and_pc2_diagnostic() -> None:
    rng = np.random.default_rng(0)
    shared = rng.normal(size=200)
    noise = rng.normal(size=200) * 0.01
    matrix = np.column_stack([shared + noise, shared - noise])
    pca = fit_combat_pca(matrix)
    assert pca.explained_pc1 >= 0.95
    assert pc1_captures_shared_combat(pca.explained_pc1)
    assert pc2_adds_validation_value(2.235, 2.230) is False
    assert pc2_adds_validation_value(2.235, 2.100) is True


def test_bootstrap_reproducibility_of_pca_orientation() -> None:
    def draws(seed: int) -> list:
        rng = np.random.default_rng(seed)
        matrix = rng.normal(size=(80, 2))
        matrix[:, 1] = matrix[:, 0] + rng.normal(size=80) * 0.05
        return [fit_combat_pca(matrix[rng.integers(0, 80, size=80)]) for _ in range(5)]

    first = draws(42)
    second = draws(42)
    assert first == second
    assert all(item.kpr_loading_pc1 + item.ndpr_loading_pc1 > 0 for item in first)


def test_role_gap_and_ranking_helpers() -> None:
    assert role_gap_acceptable(5.6, 5.6) is True
    assert role_gap_acceptable(14.3, 5.6) is False
    assert role_gap_acceptable(16.0, 16.0) is False
    reference = [f"p{index}" for index in range(50)]
    shifted = ["p0", "p99"] + reference[1:10] + reference[12:]
    assert top_n_retention(reference, shifted, 10) == 0.9


def test_selection_prefers_net_combat_when_tied_with_pca() -> None:
    selection, kind, reasons = select_combat_parameterization(
        [
            _snap(),
            _snap(
                kind=NET_COMBAT_RATE,
                val_rmse=2.236,
                bootstrap_p025=0.4,
                bootstrap_sign_flips=0,
            ),
            _snap(
                kind=PCA_COMBAT_FACTOR,
                val_rmse=2.237,
                bootstrap_p025=0.41,
                bootstrap_sign_flips=0,
            ),
            _snap(kind=NEGATIVE_DPR_ONLY, val_rmse=2.236, role_gap=14.3, bootstrap_p025=0.5),
            _snap(kind=KPR_ONLY, val_rmse=2.29, bootstrap_p025=0.2, bootstrap_sign_flips=0),
            _snap(kind=EQUAL_WEIGHT, val_rmse=2.238, bootstrap_p025=0.4, bootstrap_sign_flips=0),
        ]
    )
    assert selection == SELECTION_NCR
    assert kind == NET_COMBAT_RATE
    assert any("interpretability" in reason for reason in reasons)


def test_selection_uses_pca_when_materially_better() -> None:
    selection, kind, _reasons = select_combat_parameterization(
        [
            _snap(),
            _snap(
                kind=NET_COMBAT_RATE,
                val_rmse=2.236,
                role_gap=8.5,
                bootstrap_p025=0.2,
                bootstrap_sign_flips=0,
            ),
            _snap(
                kind=PCA_COMBAT_FACTOR,
                val_rmse=2.200,
                role_gap=5.5,
                bootstrap_p025=0.4,
                bootstrap_sign_flips=0,
            ),
        ]
    )
    assert selection == SELECTION_PCA
    assert kind == PCA_COMBAT_FACTOR


def test_selection_rethinks_when_single_factor_fails_role_or_stability() -> None:
    selection, _kind, reasons = select_combat_parameterization(
        [
            _snap(),
            _snap(kind=NET_COMBAT_RATE, val_rmse=2.236, role_gap=14.3, bootstrap_p025=0.4),
            _snap(
                kind=PCA_COMBAT_FACTOR, val_rmse=2.50, bootstrap_p025=0.4, bootstrap_sign_flips=0
            ),
        ]
    )
    assert selection == SELECTION_RETHINK
    assert any("constrained" in reason.lower() for reason in reasons)


def test_keep_two_feature_when_it_is_stable() -> None:
    selection, kind, _reasons = select_combat_parameterization(
        [
            _snap(bootstrap_p025=0.15, bootstrap_sign_flips=0),
            _snap(kind=NET_COMBAT_RATE, val_rmse=2.40, bootstrap_p025=0.4, bootstrap_sign_flips=0),
        ]
    )
    assert selection == SELECTION_KEEP_TWO
    assert kind == TWO_FEATURE


def test_readiness_gate() -> None:
    snapshot = _snap(
        kind=NET_COMBAT_RATE,
        bootstrap_p025=0.4,
        bootstrap_sign_flips=0,
        bootstrap_draws=200,
    )
    assert (
        combat_factor_readiness(
            selection=SELECTION_NCR,
            winning_kind=NET_COMBAT_RATE,
            snapshot=snapshot,
        )
        == "READY_FOR_FINAL_METRIC_VERSION"
    )
    assert (
        combat_factor_readiness(
            selection=SELECTION_KEEP_TWO,
            winning_kind=TWO_FEATURE,
            snapshot=_snap(),
        )
        == "NOT_READY"
    )
    assert (
        combat_factor_readiness(
            selection=SELECTION_NCR,
            winning_kind=NET_COMBAT_RATE,
            snapshot=snapshot,
        )
        != "READY_FOR_FRONTEND"
    )
    assert (
        combat_factor_readiness(
            selection=SELECTION_RETHINK,
            winning_kind=TWO_FEATURE,
            snapshot=_snap(),
            persisted=True,
            snapshots_exist=True,
            ranking_policy_defined=True,
            reliability_policy_defined=True,
            api_contract_ready=True,
        )
        == "NOT_READY"
    )


def test_recommended_spec_and_artifacts_are_isolated() -> None:
    spec = recommended_spec(NET_COMBAT_RATE)
    assert spec["version"] == CIR_V02_RECOMMENDED_VERSION
    assert spec["persist"] is False
    assert "net_combat_rate" in spec["combat"]["features"]
    assert CIR_V01_VERSION != CIR_V02_RECOMMENDED_VERSION
    assert CIR_REAL_EXPERIMENT_VERSION == "v0.1-real-2026"
    assert FROZEN_COMBAT_FEATURES == ("kpr_residual", "negative_dpr_residual")
    spec_ctx = frozen_context_spec()
    assert spec_ctx.lam == FROZEN_LAMBDA
    assert spec_ctx.tau == FROZEN_TAU
    assert FROZEN_SHRINKAGE_K == 50.0
    assert TWO_FEATURE in CANDIDATE_KINDS
    assert competitive_rmse(2.236, 2.235) is True
    assert competitive_rmse(2.30, 2.235) is False
