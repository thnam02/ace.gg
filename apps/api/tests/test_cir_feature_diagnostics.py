from __future__ import annotations

from app.metrics.cir_feature_diagnostics import (
    PlayerFeatureRow,
    TeamFeatureRow,
    decide_feature_dispositions,
    diagnose_feature_distributions,
    diagnose_incremental_feature,
    diagnose_residual_adr,
    feature_correlations,
    fit_named_ols,
    interpret_residual_adr,
    materially_improves,
    pearson_correlation,
    quantile_bins,
    recommend_cir_v02,
    select_feature_subset,
    within_rmse_slack,
)
from app.metrics.cir_feature_pruning_config import (
    default_feature_subset_matrix,
    register_feature_subset,
)
from app.metrics.context_v2_config import recommended_context_v2_spec
from app.schemas.cir_feature_pruning import (
    FeatureSubsetResult,
    IncrementalFeatureDiagnosis,
    ResidualAdrDiagnosis,
)
from app.schemas.context_v2 import RoleBiasMetrics, SplitMetrics


def _subset(
    name: str,
    features: tuple[str, ...],
    *,
    val_rmse: float,
    test_rmse: float = 99.0,
    val_spearman: float = 0.1,
    gap: float = 10.0,
) -> FeatureSubsetResult:
    return FeatureSubsetResult(
        name=name,
        features=list(features),
        number_of_features=len(features),
        ridge_alpha=1.0,
        validation_metrics=SplitMetrics(rmse=val_rmse, mae=val_rmse, r2=0.2, spearman=val_spearman),
        test_metrics=SplitMetrics(rmse=test_rmse, mae=test_rmse, r2=0.9, spearman=0.9),
        coefficients={feature: 0.1 for feature in features},
        role_bias_metrics=RoleBiasMetrics(max_role_median_gap=gap),
    )


def test_subset_matrix_includes_required_experiments() -> None:
    matrix = default_feature_subset_matrix()
    required = {
        "full_candidate",
        "combat_only",
        "combat_plus_residual_adr",
        "combat_plus_apr",
        "combat_plus_kast",
        "combat_plus_apr_kast",
        "combat_plus_opening",
        "combat_plus_apr_residual_adr",
        "combat_plus_apr_kast_residual_adr",
        "full_without_opening",
        "full_without_kast",
        "full_without_residual_adr",
    }
    assert required <= set(matrix)
    assert matrix["combat_only"] == ("kpr_residual", "negative_dpr_residual")
    assert "clutch_rate_adjusted" not in matrix["full_candidate"]
    extended = register_feature_subset(matrix, "custom", ("kpr_residual",))
    assert "custom" in extended
    assert "custom" not in matrix


def test_feature_diagnostics_and_correlations() -> None:
    rows = [
        PlayerFeatureRow(
            values={"kpr_residual": 0.2, "apr_residual": 0.1, "residual_adr": 10.0},
            role="Duelist",
            tier="T1",
            split="train",
            signed_outcome=2.0,
        ),
        PlayerFeatureRow(
            values={"kpr_residual": -0.1, "apr_residual": None, "residual_adr": -4.0},
            role="Controller",
            tier="T2",
            split="train",
            signed_outcome=-1.0,
        ),
        PlayerFeatureRow(
            values={"kpr_residual": 0.0, "apr_residual": 0.0, "residual_adr": 0.0},
            role="Sentinel",
            tier="T1",
            split="train",
            signed_outcome=0.5,
        ),
    ]
    reports = diagnose_feature_distributions(
        rows,
        features=("kpr_residual", "apr_residual", "residual_adr"),
    )
    overall_kpr = next(
        item for item in reports if item.feature == "kpr_residual" and item.group_type == "overall"
    )
    assert overall_kpr.count == 3
    assert overall_kpr.mean is not None
    assert overall_kpr.p10 is not None
    assert overall_kpr.missing_pct == 0.0
    apr = next(
        item for item in reports if item.feature == "apr_residual" and item.group_type == "overall"
    )
    assert apr.missing_pct > 0
    assert any(item.group_type == "role" for item in reports)
    assert any(item.group_type == "tier" and item.group_value == "T1" for item in reports)

    team_rows = [
        TeamFeatureRow(
            deltas={"kpr_residual": 1.0, "negative_dpr_residual": 0.95, "apr_residual": 0.1},
            outcome_residual=2.0,
            split="train",
        ),
        TeamFeatureRow(
            deltas={"kpr_residual": 2.0, "negative_dpr_residual": 1.9, "apr_residual": -0.2},
            outcome_residual=3.0,
            split="train",
        ),
        TeamFeatureRow(
            deltas={"kpr_residual": -1.0, "negative_dpr_residual": -0.9, "apr_residual": 0.0},
            outcome_residual=-1.0,
            split="train",
        ),
        TeamFeatureRow(
            deltas={"kpr_residual": 0.0, "negative_dpr_residual": 0.05, "apr_residual": 0.4},
            outcome_residual=0.2,
            split="train",
        ),
    ]
    pairs = feature_correlations(
        team_rows,
        features=("kpr_residual", "negative_dpr_residual", "apr_residual"),
        threshold=0.7,
    )
    flagged = [pair for pair in pairs if pair.flagged]
    assert flagged
    assert all(abs(pair.correlation) >= 0.7 for pair in flagged)
    assert not any(
        {pair.left, pair.right} == {"kpr_residual", "negative_dpr_residual"} and not pair.flagged
        for pair in pairs
        if abs(pair.correlation) >= 0.7
    )


def test_residual_adr_diagnostic_models() -> None:
    rows = [
        TeamFeatureRow(
            deltas={
                "kpr_residual": kpr,
                "negative_dpr_residual": kpr * 0.2,
                "residual_adr": adr,
            },
            outcome_residual=1.5 * kpr - 0.4 * adr,
            split="train",
        )
        for kpr, adr in (
            (1.0, 8.0),
            (0.5, 2.0),
            (-0.2, -3.0),
            (0.8, 1.0),
            (-1.0, 6.0),
            (0.1, -1.0),
        )
    ]
    diagnosis = diagnose_residual_adr(rows)
    assert "residual_adr" in diagnosis.univariate.coefficients
    assert "residual_adr" in diagnosis.controlling_for_combat.coefficients
    assert "residual_adr_sq" in diagnosis.quadratic.coefficients
    assert diagnosis.univariate.sample_size == 6
    assert diagnosis.bins
    interpretation, evidence = interpret_residual_adr(
        univariate_slope=0.2,
        controlled_slope=-0.3,
        combat_correlations={"kpr_residual": 0.8, "negative_dpr_residual": 0.2},
        quadratic_coef=0.0,
        role_slopes={"Duelist": 0.1, "Controller": 0.1},
        bins=[],
    )
    assert interpretation in {"multicollinearity", "unclear"}
    assert evidence


def test_role_level_apr_kast_and_opening_diagnostics() -> None:
    kast = diagnose_incremental_feature(
        feature="kast_residual",
        combat_rmse=1.0,
        with_feature_rmse=0.999,
        combat_spearman=0.40,
        with_feature_spearman=0.401,
        by_role_outcome_correlation={
            "Controller": 0.02,
            "Duelist": 0.01,
            "Initiator": -0.01,
            "Sentinel": 0.0,
        },
    )
    assert kast.conclusion == "no meaningful incremental value"

    apr = diagnose_incremental_feature(
        feature="apr_residual",
        combat_rmse=1.0,
        with_feature_rmse=0.97,
        combat_spearman=0.40,
        with_feature_spearman=0.45,
        by_role_outcome_correlation={
            "Controller": 0.20,
            "Initiator": 0.18,
            "Duelist": 0.02,
            "Sentinel": 0.16,
        },
    )
    assert apr.conclusion == "adds global value"
    assert apr.by_role_outcome_correlation["Controller"] == 0.20

    opening = diagnose_incremental_feature(
        feature="opening",
        combat_rmse=1.0,
        with_feature_rmse=0.9995,
        combat_spearman=0.40,
        with_feature_spearman=0.401,
        by_role_outcome_correlation={"Duelist": 0.12},
        duelist_outcome_correlation=0.18,
        non_duelist_outcome_correlation=0.01,
        opening_style=True,
    )
    assert opening.conclusion == "useful only for Duelists"


def test_simplicity_selection_uses_validation_only() -> None:
    combat = _subset("combat_only", ("kpr_residual", "negative_dpr_residual"), val_rmse=1.001)
    bloated = _subset(
        "full_candidate",
        ("kpr_residual", "negative_dpr_residual", "apr_residual", "kast_residual"),
        val_rmse=1.0,
        test_rmse=0.1,
        val_spearman=0.10,
        gap=12.0,
    )
    winner = select_feature_subset([bloated, combat])
    assert winner.name == "combat_only"

    improved = _subset(
        "combat_plus_apr",
        ("kpr_residual", "negative_dpr_residual", "apr_residual"),
        val_rmse=1.0,
        test_rmse=5.0,
        val_spearman=0.20,
        gap=12.0,
    )
    winner_material = select_feature_subset([improved, combat])
    assert winner_material.name == "combat_plus_apr"
    assert materially_improves(improved, combat)
    assert within_rmse_slack(1.001, 1.0)

    worse_val_better_test = _subset(
        "looks_good_on_test",
        ("kpr_residual",),
        val_rmse=1.5,
        test_rmse=0.01,
    )
    selected = select_feature_subset([combat, worse_val_better_test])
    assert selected.name == "combat_only"


def test_role_gap_helpers_and_recommendation() -> None:
    selected = _subset(
        "combat_plus_apr",
        ("kpr_residual", "negative_dpr_residual", "apr_residual"),
        val_rmse=1.0,
    )
    rec = recommend_cir_v02(
        selected,
        shrinkage_k=50.0,
        context_label="Context v2; lambda=1; tau=500",
        reasons=["validation-only"],
    )
    assert rec.combat == ["kpr_residual", "negative_dpr_residual"]
    assert rec.team == ["apr_residual"]
    assert rec.damage == []
    assert rec.opening == []
    assert rec.clutch == "disabled"
    assert rec.shrinkage_k == 50.0


def test_ols_and_bins_are_deterministic() -> None:
    columns = {"residual_adr": [1.0, 2.0, 3.0, 4.0], "kpr_residual": [0.1, 0.2, 0.0, -0.1]}
    target = [0.5, 1.0, 1.4, 1.7]
    first = fit_named_ols(columns, target, ("residual_adr", "kpr_residual"), model_name="m")
    second = fit_named_ols(columns, target, ("residual_adr", "kpr_residual"), model_name="m")
    assert first.coefficients == second.coefficients
    bins = quantile_bins([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], list(range(10)))
    assert bins
    assert pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_recommended_context_v2_spec() -> None:
    spec = recommended_context_v2_spec()
    assert spec.lam == 1.0
    assert spec.tau == 500.0
    assert spec.hierarchical is True
    assert spec.rules["kpr"].level.value == "role_tier"
    assert spec.rules["apr"].level.value == "agent_tier"
    assert spec.rules["kast"].level.value == "role_tier"
    assert spec.rules["opening_frequency"].level.value == "role"
    assert spec.rules["residual_adr"].level.value == "none"


def test_feature_dispositions_follow_simplicity_and_adr_diagnosis() -> None:
    combat = _subset(
        "combat_only", ("kpr_residual", "negative_dpr_residual"), val_rmse=1.0, gap=5.0
    )
    adr = _subset(
        "combat_plus_residual_adr",
        ("kpr_residual", "negative_dpr_residual", "residual_adr"),
        val_rmse=1.02,
        gap=8.0,
    )
    kast = _subset(
        "combat_plus_kast",
        ("kpr_residual", "negative_dpr_residual", "kast_residual"),
        val_rmse=0.996,
        gap=5.2,
    )
    apr = _subset(
        "combat_plus_apr",
        ("kpr_residual", "negative_dpr_residual", "apr_residual"),
        val_rmse=0.9996,
        gap=5.0,
    )
    opening = _subset(
        "combat_plus_opening",
        (
            "kpr_residual",
            "negative_dpr_residual",
            "opening_frequency_residual",
            "opening_efficiency_adjusted",
        ),
        val_rmse=0.997,
        gap=10.0,
    )
    rows = decide_feature_dispositions(
        subset_by_name={
            "combat_only": combat,
            "combat_plus_residual_adr": adr,
            "combat_plus_kast": kast,
            "combat_plus_apr": apr,
            "combat_plus_opening": opening,
        },
        residual_adr=ResidualAdrDiagnosis(interpretation="true negative conditional association"),
        kast=IncrementalFeatureDiagnosis(feature="kast_residual", conclusion="adds global value"),
        apr=IncrementalFeatureDiagnosis(
            feature="apr_residual", conclusion="no meaningful incremental value"
        ),
        opening=IncrementalFeatureDiagnosis(feature="opening", conclusion="adds global value"),
        selected=combat,
    )
    by_feature = {item.feature: item.disposition for item in rows}
    assert by_feature["kpr_residual"] == "KEEP"
    assert by_feature["negative_dpr_residual"] == "KEEP"
    assert by_feature["residual_adr"] == "REMOVE"
    assert by_feature["apr_residual"] == "REMOVE"
    assert by_feature["kast_residual"] == "REMOVE"
    assert by_feature["opening_frequency_residual / opening_efficiency_adjusted"] == "REMOVE"
