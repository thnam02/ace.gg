from __future__ import annotations

from app.metrics.cir_scoring import apply_shrinkage, empirical_cdf, round_weighted_mean
from app.metrics.context_v2 import ContextV2Level, exposure_weight, hierarchical_mean
from app.metrics.mir.mir_config import (
    APR_CONTEXT,
    DPR_CONTEXT,
    KAST_CONTEXT,
    KPR_CONTEXT,
    OPENING_EFFICIENCY_CONTEXT,
    OPENING_FREQUENCY_CONTEXT,
    ROUND_PARTICIPATION,
    SUPPORT_ASSIST,
    default_mir_subset_matrix,
    mir_context_rules,
)
from app.metrics.mir.mir_economy import economy_is_usable, inspect_economy_availability
from app.metrics.mir.mir_features import alias_context_features, opening_attempts
from app.metrics.mir.mir_residualization import (
    apply_mir_residualizers,
    damped_context_residual,
    fit_linear_residualizer,
    fit_mir_residualizers,
    shrink_rate,
)
from app.metrics.mir.mir_scoring import compute_raw_mir, reliability_score
from app.metrics.mir.mir_validation import (
    classify_signal,
    evidence_gate,
    mir_readiness,
    select_mir_decision,
    select_mir_subset,
)
from app.schemas.context_v2 import RoleBiasMetrics, SplitMetrics
from app.schemas.mir_experiment import MirSubsetResult
from tests.test_context_v2 import _obs


def test_apr_and_kast_residualization_are_orthogonal_to_combat() -> None:
    rows = []
    for index in range(12):
        kpr = 0.1 * index
        dpr = -0.05 * index
        rows.append(
            {
                KPR_CONTEXT: kpr,
                DPR_CONTEXT: dpr,
                APR_CONTEXT: 0.4 * kpr + 0.1,
                KAST_CONTEXT: 2.0 * kpr + 0.3 * dpr + 5.0,
                OPENING_FREQUENCY_CONTEXT: 0.2,
                OPENING_EFFICIENCY_CONTEXT: 0.1 * kpr,
            }
        )
    models = fit_mir_residualizers(rows, opening_attempts=[8] * len(rows))
    applied = [apply_mir_residualizers(row, models, opening_attempts=8) for row in rows]
    apr_unique = [row[SUPPORT_ASSIST] for row in applied]
    assert all(value is not None for value in apr_unique)
    assert max(abs(value or 0.0) for value in apr_unique) < 1e-6
    kast_unique = [row[ROUND_PARTICIPATION] for row in applied]
    assert max(abs(value or 0.0) for value in kast_unique) < 1e-5


def test_opening_residualization_damps_small_samples() -> None:
    observed = 0.9
    expected = 0.5
    full = damped_context_residual(observed, expected, attempts=40, prior_k=8.0)
    tiny = damped_context_residual(observed, expected, attempts=1, prior_k=8.0)
    assert full is not None and tiny is not None
    assert abs(full) > abs(tiny)
    shrunk = shrink_rate(0.9, 0.5, attempts=0, prior_k=8.0)
    assert shrunk == 0.5


def test_residualizers_fit_train_only_and_freeze_on_holdout() -> None:
    train = [
        {
            KPR_CONTEXT: 1.0,
            DPR_CONTEXT: 0.0,
            APR_CONTEXT: 2.0,
            KAST_CONTEXT: 3.0,
            OPENING_FREQUENCY_CONTEXT: 0.1,
            OPENING_EFFICIENCY_CONTEXT: 0.2,
        },
        {
            KPR_CONTEXT: 2.0,
            DPR_CONTEXT: 1.0,
            APR_CONTEXT: 4.0,
            KAST_CONTEXT: 6.0,
            OPENING_FREQUENCY_CONTEXT: 0.2,
            OPENING_EFFICIENCY_CONTEXT: 0.4,
        },
        {
            KPR_CONTEXT: 3.0,
            DPR_CONTEXT: 2.0,
            APR_CONTEXT: 6.0,
            KAST_CONTEXT: 9.0,
            OPENING_FREQUENCY_CONTEXT: 0.3,
            OPENING_EFFICIENCY_CONTEXT: 0.6,
        },
    ]
    models = fit_mir_residualizers(train, opening_attempts=[10, 10, 10])
    holdout = {
        KPR_CONTEXT: 4.0,
        DPR_CONTEXT: 3.0,
        APR_CONTEXT: 8.0,
        KAST_CONTEXT: 12.0,
        OPENING_FREQUENCY_CONTEXT: 0.4,
        OPENING_EFFICIENCY_CONTEXT: 0.8,
    }
    applied = apply_mir_residualizers(holdout, models, opening_attempts=10)
    second = apply_mir_residualizers(holdout, models, opening_attempts=10)
    assert applied[SUPPORT_ASSIST] == second[SUPPORT_ASSIST]
    assert models.apr.coefficients[KPR_CONTEXT] != 0.0


def test_linear_residualizer_and_aliasing() -> None:
    model = fit_linear_residualizer(
        [1.0, 2.0, 3.0],
        [{KPR_CONTEXT: 1.0}, {KPR_CONTEXT: 2.0}, {KPR_CONTEXT: 3.0}],
        (KPR_CONTEXT,),
    )
    residual = model.residual(2.0, {KPR_CONTEXT: 2.0})
    assert residual is not None
    assert abs(residual) < 1e-8
    aliased = alias_context_features({"kpr_residual": 0.5, "apr_residual": 0.2})
    assert aliased[KPR_CONTEXT] == 0.5
    assert aliased[APR_CONTEXT] == 0.2
    assert opening_attempts(3, 2) == 5


def test_role_expectation_hierarchy_uses_parent_shrinkage() -> None:
    observations = [
        _obs(1, role="Initiator", agent_name="Sova", tier="T1", assists=20, rounds=20),
        _obs(2, role="Initiator", agent_name="Sova", tier="T1", assists=16, rounds=20),
        _obs(3, role="Initiator", agent_name="Fade", tier="T1", assists=8, rounds=20),
    ]
    from app.metrics.context_v2 import build_context_v2_registry

    registry = build_context_v2_registry(observations)
    rules = mir_context_rules()
    assert rules["apr"].level == ContextV2Level.AGENT_TIER
    mean, level = hierarchical_mean(
        registry,
        observations[0],
        ContextV2Level.AGENT_TIER,
        "apr",
        tau=500.0,
    )
    assert mean is not None
    assert level == "agent_tier"
    weight = exposure_weight(registry.agent_tier[("Sova", "T1")], "apr")
    assert weight > 0


def test_economy_feasibility_is_disabled() -> None:
    rows = inspect_economy_availability()
    assert rows
    assert all(item.missing_pct == 100.0 for item in rows)
    assert economy_is_usable(rows) is False
    assert "pistol_rounds" in {item.field for item in rows}


def test_evidence_gate_and_selection_use_validation_only() -> None:
    combat = MirSubsetResult(
        name="combat_only",
        features=["kpr_context_residual", "negative_dpr_context_residual"],
        number_of_features=2,
        validation_metrics=SplitMetrics(rmse=1.0, r2=0.5, spearman=0.4),
        test_metrics=SplitMetrics(rmse=0.1, r2=0.99, spearman=0.99),
        coefficients={"kpr_context_residual": 0.4, "negative_dpr_context_residual": 0.5},
        role_bias_metrics=RoleBiasMetrics(max_role_median_gap=6.0),
    )
    unique = MirSubsetResult(
        name="combat_plus_apr_unique",
        features=["kpr_context_residual", "negative_dpr_context_residual", SUPPORT_ASSIST],
        number_of_features=3,
        validation_metrics=SplitMetrics(rmse=0.999, r2=0.5, spearman=0.4),
        test_metrics=SplitMetrics(rmse=0.01, r2=0.99, spearman=0.99),
        coefficients={SUPPORT_ASSIST: 0.2},
        role_bias_metrics=RoleBiasMetrics(max_role_median_gap=6.0),
    )
    passed, _evidence = evidence_gate(combat, unique, extra_features=(SUPPORT_ASSIST,))
    assert passed is False
    winner = select_mir_subset([unique, combat])
    assert winner.name == "combat_only"
    assert (
        classify_signal(
            unique_vs_combat_delta=-0.0005,
            unique_vs_raw_delta=-0.01,
            unique_coef=0.2,
            gate_passed=False,
            role_specific=False,
            harmful_rmse=False,
        )
        == "REDUNDANT_WITH_COMBAT"
    )
    assert (
        classify_signal(
            unique_vs_combat_delta=0.02,
            unique_vs_raw_delta=0.01,
            unique_coef=-0.2,
            gate_passed=False,
            role_specific=False,
            harmful_rmse=True,
        )
        == "HARMFUL"
    )
    assert select_mir_decision(
        "combat_only", support_enabled=False, opening_enabled=False, economy_enabled=False
    ) == ("COMBAT_ONLY_REMAINS_BEST")
    assert mir_readiness("COMBAT_ONLY_REMAINS_BEST", -0.02) == "NOT_READY"


def test_t1_t2_inconsistency_fails_gate() -> None:
    combat = MirSubsetResult(
        name="combat_only",
        features=["kpr_context_residual"],
        number_of_features=1,
        validation_metrics=SplitMetrics(rmse=2.0, r2=0.4, spearman=0.3),
        role_bias_metrics=RoleBiasMetrics(max_role_median_gap=5.0),
        coefficients={"kpr_context_residual": 0.5},
    )
    candidate = MirSubsetResult(
        name="combat_plus_apr_unique",
        features=["kpr_context_residual", SUPPORT_ASSIST],
        number_of_features=2,
        validation_metrics=SplitMetrics(rmse=1.9, r2=0.45, spearman=0.32),
        role_bias_metrics=RoleBiasMetrics(max_role_median_gap=5.0),
        coefficients={SUPPORT_ASSIST: 0.2},
        t1_extra_coefficients={SUPPORT_ASSIST: 0.3},
        t2_extra_coefficients={SUPPORT_ASSIST: -0.2},
    )
    passed, evidence = evidence_gate(
        combat,
        candidate,
        extra_features=(SUPPORT_ASSIST,),
        t1_coefficients=candidate.t1_extra_coefficients,
        t2_coefficients=candidate.t2_extra_coefficients,
    )
    assert passed is False
    assert any("T1/T2" in line for line in evidence)


def test_player_aggregation_shrinkage_and_percentile() -> None:
    raw = round_weighted_mean([(1.0, 10), (3.0, 30)])
    assert raw == 2.5
    shrunk = apply_shrinkage(2.5, 40, reference_mean=0.0, shrinkage_k=50.0)
    assert 0.0 < shrunk < 2.5
    percentile = empirical_cdf(shrunk, [0.0, 0.5, 1.0, 2.0, 3.0])
    assert 0.0 <= percentile <= 100.0
    score = compute_raw_mir(
        {KPR_CONTEXT: 1.0, DPR_CONTEXT: 2.0},
        {KPR_CONTEXT: 0.5, DPR_CONTEXT: 0.25},
        (KPR_CONTEXT, DPR_CONTEXT),
    )
    assert score == 1.0
    assert 0.0 <= reliability_score(40, 4) <= 100.0


def test_marginal_contribution_is_the_player_term() -> None:
    from app.metrics.cir_scoring import build_team_delta_vector

    features = (KPR_CONTEXT,)
    team_a = [{KPR_CONTEXT: 1.0}, {KPR_CONTEXT: 2.0}]
    team_b = [{KPR_CONTEXT: 0.5}]
    full = build_team_delta_vector(team_a, team_b, feature_names=features)
    without = build_team_delta_vector([team_a[1]], team_b, feature_names=features)
    coef = 0.4
    prediction_full = coef * full[KPR_CONTEXT]
    prediction_without = coef * without[KPR_CONTEXT]
    assert abs((prediction_full - prediction_without) - coef * 1.0) < 1e-9


def test_subset_matrix_and_component_disable() -> None:
    matrix = default_mir_subset_matrix(economy_enabled=False)
    assert "combat_only" in matrix
    assert "full_mir_candidate" in matrix
    assert "combat_plus_economy_unique" not in matrix
    assert matrix["combat_only"] == (KPR_CONTEXT, DPR_CONTEXT)
    enabled = default_mir_subset_matrix(economy_enabled=True)
    assert "combat_plus_economy_unique" in enabled
