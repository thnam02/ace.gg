from __future__ import annotations

from uuid import uuid4

from app.metrics.cir_final_validation import (
    audit_failure_conditions,
    chronological_two_way,
    coefficient_summary,
    decide_readiness,
    recommend_sample_threshold,
    sample_label,
    second_feature_adds_value,
    top_n_retention,
)
from app.metrics.cir_final_validation_config import FROZEN_COMBAT_FEATURES, TEMPORAL_SPLIT_GRID
from app.schemas.cir_final_validation import FailureConditionAudit
from app.services.cir_training_service import _chronological_split


def test_frozen_candidate_is_combat_only() -> None:
    assert FROZEN_COMBAT_FEATURES == ("kpr_residual", "negative_dpr_residual")
    assert len(TEMPORAL_SPLIT_GRID) == 5


def test_chronological_splits_cover_all_maps() -> None:
    map_ids = [uuid4() for _ in range(20)]
    for train_frac, val_frac in TEMPORAL_SPLIT_GRID:
        train, val, test = _chronological_split(
            map_ids, train_fraction=train_frac, validation_fraction=val_frac
        )
        assert train.isdisjoint(val)
        assert train.isdisjoint(test)
        assert val.isdisjoint(test)
        assert train | val | test == set(map_ids)
        assert len(train) >= len(val)
        assert len(train) >= len(test)


def test_chronological_two_way_is_ordered() -> None:
    map_ids = [uuid4() for _ in range(10)]
    train, val = chronological_two_way(map_ids, 0.8)
    assert not train & val
    assert train | val == set(map_ids)
    assert map_ids[0] in train
    assert map_ids[-1] in val


def test_coefficient_summary_counts_sign_flips() -> None:
    summary = coefficient_summary([0.2, 0.1, -0.05, 0.3])
    assert summary.sign_flip_count == 1
    assert summary.positive_share == 0.75


def test_second_feature_adds_value_uses_one_percent_bar() -> None:
    assert second_feature_adds_value(2.220, 2.235) is False
    assert second_feature_adds_value(2.10, 2.30) is True


def test_top_n_retention_and_sample_labels() -> None:
    reference = [f"p{index}" for index in range(50)]
    shifted = ["p0", "p99"] + reference[1:10] + reference[12:]
    assert top_n_retention(reference, shifted, 10) == 0.9
    assert sample_label(50) == "LOW_SAMPLE"
    assert sample_label(120) == "PROVISIONAL"
    assert sample_label(300) == "ESTABLISHED"


def test_recommend_sample_threshold_prefers_250_when_stable() -> None:
    assert recommend_sample_threshold([(50, 20, 0.6), (100, 18, 0.8), (250, 12, 0.9)]) == 250
    assert recommend_sample_threshold([(100, 3, 0.9), (250, 3, 0.7), (500, 10, 0.9)]) == 500


def test_readiness_never_frontend_without_persistence() -> None:
    passed = FailureConditionAudit(passed=True)
    failed = FailureConditionAudit(passed=False, failures=["sign flips"])
    assert (
        decide_readiness(
            failure_audit=failed,
            persisted=False,
            snapshots_exist=False,
            ranking_policy_defined=False,
            reliability_policy_defined=False,
            api_contract_ready=False,
        )
        == "NOT_READY"
    )
    assert (
        decide_readiness(
            failure_audit=passed,
            persisted=False,
            snapshots_exist=False,
            ranking_policy_defined=False,
            reliability_policy_defined=False,
            api_contract_ready=False,
        )
        == "READY_FOR_FINAL_METRIC_VERSION"
    )
    assert (
        decide_readiness(
            failure_audit=passed,
            persisted=True,
            snapshots_exist=True,
            ranking_policy_defined=True,
            reliability_policy_defined=True,
            api_contract_ready=True,
        )
        == "READY_FOR_FRONTEND"
    )


def test_failure_audit_flags_sign_flips_and_role_gaps() -> None:
    audit = audit_failure_conditions(
        kpr_values=[0.2, -0.1, -0.2],
        ndpr_values=[0.5, 0.4, 0.3],
        primary_val_rmse=2.2,
        later_event_rmses=[2.3, 4.0],
        t1_rmse=2.0,
        t2_rmse=4.0,
        t1_kpr_sign="positive",
        t2_kpr_sign="negative",
        t1_ndpr_sign="positive",
        t2_ndpr_sign="positive",
        role_gaps=[5.0, 16.0, 18.0],
        bootstrap_kpr_low=-0.01,
        bootstrap_ndpr_low=0.1,
        ranking_spearman_500=0.7,
        cir_event_wins=1,
        kd_event_wins=4,
        acs_event_wins=0,
        vlr_event_wins=0,
        baseline_cir_better=False,
    )
    assert audit.passed is False
    assert any("sign flips" in item for item in audit.failures)
