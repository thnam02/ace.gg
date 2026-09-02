from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from app.metrics.cir_combat_factor import (
    CombatPCA,
    equal_weight_combat,
    fit_combat_pca,
    net_combat_rate,
    transform_combat_pca,
)
from app.metrics.cir_combat_factor_config import (
    COMBAT_FACTOR_FEATURE,
    EQUAL_WEIGHT,
    EQUAL_WEIGHT_FEATURE,
    FEATURES_BY_KIND,
    KPR_FEATURE,
    KPR_ONLY,
    MIN_TRAIN_TEAM_MAPS,
    NEGATIVE_DPR_FEATURE,
    NEGATIVE_DPR_ONLY,
    NET_COMBAT_FEATURE,
    NET_COMBAT_RATE,
    PC2_FEATURE,
    PCA_COMBAT_FACTOR,
    TWO_FEATURE,
)
from app.metrics.cir_final_validation import split_metrics_from_arrays
from app.metrics.cir_scoring import CIRModelCoefficients, build_team_delta_vector
from app.metrics.cir_standardization import fit_standardization, standardize_features
from app.metrics.cir_validation_config import CIR_ROLES
from app.metrics.context_v2_diagnostics import role_bias_metrics
from app.metrics.derived import safe_ratio
from app.metrics.ridge_regression import fit_ridge, predict_ridge
from app.models import PlayerMapStats
from app.schemas.cir_combat_factor import CombatCandidatePrimary
from app.schemas.context_v2 import RoleBiasMetrics, SplitMetrics
from app.services.cir_final_validation_support import (
    PlayerScore,
    fit_ridge_on_maps,
    gap_from_scores,
    match_id_for,
    match_ids_for_maps,
    metrics_for_split,
    player_scores,
    resample_match_ids,
)
from app.services.cir_training_service import (
    CIREvaluationBundle,
    _coefficients_for_features,
    _design_matrix,
    _PlayerMapPrepared,
    _TeamMapPrepared,
)


@dataclass
class AppliedCombat:
    kind: str
    feature_names: tuple[str, ...]
    bundle: CIREvaluationBundle
    coefficients: CIRModelCoefficients
    ridge_alpha: float
    val_metrics: SplitMetrics
    test_metrics: SplitMetrics
    role_gap: float | None
    player_scores: dict[UUID, PlayerScore]
    pca: CombatPCA | None = None
    role_bias: RoleBiasMetrics | None = None


def combat_coefficient(kind: str, coefficients: CIRModelCoefficients) -> float | None:
    features = FEATURES_BY_KIND[kind]
    if kind == TWO_FEATURE:
        return None
    if not features:
        return None
    return coefficients.coefficients.get(features[0])


def copy_player(
    row: _PlayerMapPrepared,
    standardized: dict[str, float],
    raw: dict[str, float | None] | None = None,
) -> _PlayerMapPrepared:
    return _PlayerMapPrepared(
        stats=row.stats,
        split=row.split,
        raw_features=raw if raw is not None else row.raw_features,
        standardized_features=standardized,
        baseline_level=row.baseline_level,
        non_context_features=row.non_context_features,
        adjusted=row.adjusted,
    )


def rebuild_team_maps(
    prepared: list[_PlayerMapPrepared],
    original: list[_TeamMapPrepared],
    feature_names: tuple[str, ...],
) -> list[_TeamMapPrepared]:
    lookup = {row.match_map_id: row for row in original}
    grouped: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
    for row in prepared:
        grouped[row.stats.match_map_id].append(row)
    rebuilt: list[_TeamMapPrepared] = []
    for match_map_id, rows in grouped.items():
        source = lookup.get(match_map_id)
        if source is None:
            continue
        match = rows[0].stats.match_map.match
        if match.team_a_id is None or match.team_b_id is None:
            continue
        team_a = [row.standardized_features for row in rows if row.stats.team_id == match.team_a_id]
        team_b = [row.standardized_features for row in rows if row.stats.team_id == match.team_b_id]
        rebuilt.append(
            _TeamMapPrepared(
                match_map_id=match_map_id,
                split=source.split,
                outcome_residual=source.outcome_residual,
                deltas=build_team_delta_vector(team_a, team_b, feature_names=feature_names),
            )
        )
    return rebuilt


def _train_rows(
    prepared: list[_PlayerMapPrepared],
    train_map_ids: set[UUID] | None,
) -> list[_PlayerMapPrepared]:
    if train_map_ids is None:
        return [row for row in prepared if row.split == "train"]
    return [row for row in prepared if row.stats.match_map_id in train_map_ids]


def _standardized_pair(row: _PlayerMapPrepared) -> tuple[float, float]:
    return (
        float(row.standardized_features.get(KPR_FEATURE, 0.0)),
        float(row.standardized_features.get(NEGATIVE_DPR_FEATURE, 0.0)),
    )


def transform_prepared(
    bundle: CIREvaluationBundle,
    kind: str,
    train_map_ids: set[UUID] | None = None,
) -> tuple[list[_PlayerMapPrepared], CombatPCA | None]:
    prepared = bundle.prepared_maps
    if kind in {TWO_FEATURE, KPR_ONLY, NEGATIVE_DPR_ONLY}:
        return prepared, None
    train = _train_rows(prepared, train_map_ids)
    if kind == NET_COMBAT_RATE:
        train_raw = [
            {
                NET_COMBAT_FEATURE: net_combat_rate(
                    row.raw_features.get(KPR_FEATURE),
                    row.raw_features.get(NEGATIVE_DPR_FEATURE),
                )
            }
            for row in train
        ]
        params = fit_standardization(train_raw, feature_names=(NET_COMBAT_FEATURE,))
        transformed: list[_PlayerMapPrepared] = []
        for row in prepared:
            ncr = net_combat_rate(
                row.raw_features.get(KPR_FEATURE),
                row.raw_features.get(NEGATIVE_DPR_FEATURE),
            )
            raw = dict(row.raw_features)
            raw[NET_COMBAT_FEATURE] = ncr
            extra = standardize_features(
                {NET_COMBAT_FEATURE: ncr}, params, feature_names=(NET_COMBAT_FEATURE,)
            )
            standardized = dict(row.standardized_features)
            standardized[NET_COMBAT_FEATURE] = extra[NET_COMBAT_FEATURE]
            transformed.append(copy_player(row, standardized, raw=raw))
        return transformed, None
    if kind == EQUAL_WEIGHT:
        transformed = []
        for row in prepared:
            z_kpr, z_ndpr = _standardized_pair(row)
            standardized = dict(row.standardized_features)
            standardized[EQUAL_WEIGHT_FEATURE] = equal_weight_combat(z_kpr, z_ndpr)
            transformed.append(copy_player(row, standardized))
        return transformed, None
    train_matrix = np.array([_standardized_pair(row) for row in train], dtype=np.float64)
    pca = fit_combat_pca(train_matrix)
    matrix = np.array([_standardized_pair(row) for row in prepared], dtype=np.float64)
    pc1, pc2 = transform_combat_pca(matrix, pca)
    transformed = []
    for row, score, score_pc2 in zip(prepared, pc1, pc2, strict=True):
        standardized = dict(row.standardized_features)
        standardized[COMBAT_FACTOR_FEATURE] = float(score)
        standardized[PC2_FEATURE] = float(score_pc2)
        transformed.append(copy_player(row, standardized))
    return transformed, pca


def derived_bundle(
    original: CIREvaluationBundle,
    prepared: list[_PlayerMapPrepared],
    team_maps: list[_TeamMapPrepared],
    features: tuple[str, ...],
    coefficients: CIRModelCoefficients,
    ridge_alpha: float,
    shrinkage_k: float,
) -> CIREvaluationBundle:
    return CIREvaluationBundle(
        prepared_maps=prepared,
        team_maps=team_maps,
        standardization=original.standardization,
        full_coefficients=coefficients,
        ridge_alpha=ridge_alpha,
        reference_mean=original.reference_mean,
        reference_population=original.reference_population,
        shrinkage_k=shrinkage_k,
        feature_names=features,
    )


def apply_parameterization(
    bundle: CIREvaluationBundle,
    kind: str,
    shrinkage_k: float,
    *,
    train_map_ids: set[UUID] | None = None,
    ridge_alpha: float | None = None,
    ridge_maps: list[_TeamMapPrepared] | None = None,
) -> AppliedCombat:
    features = FEATURES_BY_KIND[kind]
    prepared, pca = transform_prepared(bundle, kind, train_map_ids=train_map_ids)
    if kind in {TWO_FEATURE, KPR_ONLY, NEGATIVE_DPR_ONLY}:
        team_maps = bundle.team_maps
        model_bundle = bundle
    else:
        team_maps = rebuild_team_maps(prepared, bundle.team_maps, features)
        model_bundle = derived_bundle(
            bundle,
            prepared,
            team_maps,
            features,
            CIRModelCoefficients(intercept=0.0, coefficients={}),
            ridge_alpha or 0.01,
            shrinkage_k,
        )
    fit_maps = ridge_maps if ridge_maps is not None else team_maps
    coefficients, alpha = fit_ridge_on_maps(fit_maps, features, alpha=ridge_alpha)
    if kind not in {TWO_FEATURE, KPR_ONLY, NEGATIVE_DPR_ONLY}:
        model_bundle = derived_bundle(
            bundle, prepared, team_maps, features, coefficients, alpha, shrinkage_k
        )
    scores = player_scores(model_bundle, coefficients, features, shrinkage_k)
    bias = _role_bias(scores)
    return AppliedCombat(
        kind=kind,
        feature_names=features,
        bundle=model_bundle,
        coefficients=coefficients,
        ridge_alpha=alpha,
        val_metrics=metrics_for_split(model_bundle, "validation", coefficients, features),
        test_metrics=metrics_for_split(model_bundle, "test", coefficients, features),
        role_gap=gap_from_scores(scores),
        player_scores=scores,
        pca=pca,
        role_bias=bias,
    )


def apply_pc1_pc2(
    bundle: CIREvaluationBundle,
    shrinkage_k: float,
) -> tuple[AppliedCombat, AppliedCombat]:
    pc1 = apply_parameterization(bundle, PCA_COMBAT_FACTOR, shrinkage_k)
    features = (COMBAT_FACTOR_FEATURE, PC2_FEATURE)
    team_maps = rebuild_team_maps(pc1.bundle.prepared_maps, bundle.team_maps, features)
    coefficients, alpha = fit_ridge_on_maps(team_maps, features)
    model_bundle = derived_bundle(
        bundle, pc1.bundle.prepared_maps, team_maps, features, coefficients, alpha, shrinkage_k
    )
    scores = player_scores(model_bundle, coefficients, features, shrinkage_k)
    both = AppliedCombat(
        kind="pc1_pc2",
        feature_names=features,
        bundle=model_bundle,
        coefficients=coefficients,
        ridge_alpha=alpha,
        val_metrics=metrics_for_split(model_bundle, "validation", coefficients, features),
        test_metrics=metrics_for_split(model_bundle, "test", coefficients, features),
        role_gap=gap_from_scores(scores),
        player_scores=scores,
        pca=pc1.pca,
        role_bias=_role_bias(scores),
    )
    return pc1, both


def _role_bias(scores: dict[UUID, PlayerScore]) -> RoleBiasMetrics:
    grouped: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for score in scores.values():
        grouped[score.role].append((score.cir, score.rounds))
    return role_bias_metrics(grouped)


def to_primary_row(
    applied: AppliedCombat,
    *,
    competitive: bool,
    interpretation: str,
) -> CombatCandidatePrimary:
    bias = applied.role_bias or RoleBiasMetrics()
    display = {
        TWO_FEATURE: "Two-feature combat",
        NEGATIVE_DPR_ONLY: "Negative-DPR only",
        KPR_ONLY: "KPR only",
        NET_COMBAT_RATE: "Net Combat Rate",
        PCA_COMBAT_FACTOR: "PCA Combat Factor",
        EQUAL_WEIGHT: "Equal-weight combat",
    }
    coefs = applied.coefficients.coefficients
    return CombatCandidatePrimary(
        kind=applied.kind,
        display_name=display.get(applied.kind, applied.kind),
        interpretation=interpretation,
        n_combat_dimensions=len(applied.feature_names),
        validation_metrics=applied.val_metrics,
        test_metrics=applied.test_metrics,
        ridge_alpha=applied.ridge_alpha,
        combat_coefficient=combat_coefficient(applied.kind, applied.coefficients),
        kpr_coefficient=coefs.get(KPR_FEATURE) if KPR_FEATURE in applied.feature_names else None,
        negative_dpr_coefficient=(
            coefs.get(NEGATIVE_DPR_FEATURE)
            if NEGATIVE_DPR_FEATURE in applied.feature_names
            else None
        ),
        role_median_gap=applied.role_gap,
        role_medians={role: bias.medians.get(role) for role in CIR_ROLES},
        controller_vs_duelist=bias.controller_vs_duelist_gap,
        controller_vs_initiator=bias.controller_vs_initiator_gap,
        controller_vs_sentinel=bias.controller_vs_sentinel_gap,
        role_bias=bias,
        competitive_rmse=competitive,
    )


def train_kpr_ndpr_correlation(bundle: CIREvaluationBundle) -> float | None:
    xs: list[float] = []
    ys: list[float] = []
    for row in bundle.prepared_maps:
        if row.split != "train":
            continue
        kpr = row.raw_features.get(KPR_FEATURE)
        ndpr = row.raw_features.get(NEGATIVE_DPR_FEATURE)
        if kpr is None or ndpr is None:
            continue
        xs.append(float(kpr))
        ys.append(float(ndpr))
    if len(xs) < 2:
        return None
    return float(np.corrcoef(np.array(xs), np.array(ys))[0, 1])


def player_combat_means(
    bundle: CIREvaluationBundle,
) -> dict[UUID, tuple[float, float, int]]:
    grouped: dict[UUID, list[tuple[float, float, int]]] = defaultdict(list)
    for row in bundle.prepared_maps:
        kpr = row.raw_features.get(KPR_FEATURE)
        ndpr = row.raw_features.get(NEGATIVE_DPR_FEATURE)
        if kpr is None or ndpr is None:
            continue
        grouped[row.stats.player_id].append((float(kpr), float(ndpr), row.stats.rounds))
    means: dict[UUID, tuple[float, float, int]] = {}
    for player_id, rows in grouped.items():
        rounds = sum(item[2] for item in rows)
        if rounds <= 0:
            continue
        kpr = sum(item[0] * item[2] for item in rows) / rounds
        ndpr = sum(item[1] * item[2] for item in rows) / rounds
        means[player_id] = (kpr, ndpr, rounds)
    return means


def profile_label(kpr: float, ndpr: float, kpr_median: float, ndpr_median: float) -> str | None:
    high_kpr = kpr >= kpr_median
    high_ndpr = ndpr >= ndpr_median
    if high_kpr and not high_ndpr:
        return "high_kpr_high_dpr"
    if not high_kpr and high_ndpr:
        return "low_kpr_low_dpr"
    return None


def bootstrap_kind(
    original: CIREvaluationBundle,
    kind: str,
    shrinkage_k: float,
    iterations: int,
    seed: int,
    ridge_alpha: float,
) -> dict[str, list[float]]:
    train_maps = [row for row in original.team_maps if row.split == "train"]
    val_maps = [row for row in original.team_maps if row.split == "validation"]
    usable = match_ids_for_maps(original, {row.match_map_id for row in train_maps})
    maps_by_match: dict[UUID, list[_TeamMapPrepared]] = defaultdict(list)
    for row in train_maps:
        match_id = match_id_for(original, row.match_map_id)
        if match_id is not None:
            maps_by_match[match_id].append(row)
    usable = [match_id for match_id in usable if match_id in maps_by_match]
    out: dict[str, list[float]] = {
        "coefficient": [],
        "kpr": [],
        "ndpr": [],
        "rmse": [],
        "r2": [],
        "spearman": [],
        "kpr_loading": [],
        "ndpr_loading": [],
        "explained": [],
    }
    if len(usable) < 2 or not val_maps:
        return out
    rng = np.random.default_rng(seed)
    features = FEATURES_BY_KIND[kind]
    subset = kind in {TWO_FEATURE, KPR_ONLY, NEGATIVE_DPR_ONLY}
    if subset:
        val_design, val_targets = _design_matrix(val_maps, feature_names=features)
        for _ in range(iterations):
            sampled = resample_match_ids(usable, rng)
            boot_maps = [row for match_id in sampled for row in maps_by_match[match_id]]
            if len(boot_maps) < MIN_TRAIN_TEAM_MAPS:
                continue
            train_design, train_targets = _design_matrix(boot_maps, feature_names=features)
            try:
                intercept, weights = fit_ridge(train_design, train_targets, ridge_alpha)
            except np.linalg.LinAlgError:
                continue
            coefs = _coefficients_for_features(features, weights)
            if kind == TWO_FEATURE:
                out["coefficient"].append(float(coefs.get(KPR_FEATURE, 0.0)))
                out["kpr"].append(float(coefs.get(KPR_FEATURE, 0.0)))
                out["ndpr"].append(float(coefs.get(NEGATIVE_DPR_FEATURE, 0.0)))
            else:
                out["coefficient"].append(float(coefs.get(features[0], 0.0)))
            metrics = _metrics(val_targets, predict_ridge(val_design, intercept, weights))
            _append_metrics(out, metrics)
        return out

    for _ in range(iterations):
        sampled = resample_match_ids(usable, rng)
        boot_ids: set[UUID] = set()
        sampled_maps: list[_TeamMapPrepared] = []
        for match_id in sampled:
            for row in maps_by_match[match_id]:
                sampled_maps.append(row)
                boot_ids.add(row.match_map_id)
        if len(sampled_maps) < MIN_TRAIN_TEAM_MAPS:
            continue
        try:
            applied = apply_parameterization(
                original,
                kind,
                shrinkage_k,
                train_map_ids=boot_ids,
                ridge_alpha=ridge_alpha,
                ridge_maps=None,
            )
        except (ValueError, np.linalg.LinAlgError):
            continue
        # Refit ridge on the resampled train maps using the transformed deltas.
        transformed_train = [
            row for row in applied.bundle.team_maps if row.match_map_id in boot_ids
        ]
        try:
            coefficients, _alpha = fit_ridge_on_maps(transformed_train, features, alpha=ridge_alpha)
        except np.linalg.LinAlgError:
            continue
        out["coefficient"].append(float(coefficients.coefficients.get(features[0], 0.0)))
        if applied.pca is not None:
            out["kpr_loading"].append(applied.pca.kpr_loading_pc1)
            out["ndpr_loading"].append(applied.pca.ndpr_loading_pc1)
            out["explained"].append(applied.pca.explained_pc1)
        val_metrics = metrics_for_split(applied.bundle, "validation", coefficients, features)
        _append_metrics(out, val_metrics)
    return out


def _metrics(targets: NDArray[np.float64], predictions: NDArray[np.float64]) -> SplitMetrics:
    return split_metrics_from_arrays(targets, predictions)


def _append_metrics(out: dict[str, list[float]], metrics: SplitMetrics) -> None:
    if metrics.rmse is not None:
        out["rmse"].append(metrics.rmse)
    if metrics.r2 is not None:
        out["r2"].append(metrics.r2)
    if metrics.spearman is not None:
        out["spearman"].append(metrics.spearman)


def univariate_baselines(
    bundle: CIREvaluationBundle,
) -> dict[str, tuple[SplitMetrics, SplitMetrics]]:
    stats_by_map: dict[UUID, list[PlayerMapStats]] = defaultdict(list)
    for row in bundle.prepared_maps:
        stats_by_map[row.stats.match_map_id].append(row.stats)
    extractors: dict[str, Callable[[PlayerMapStats], float]] = {
        "kd": _baseline_kd,
        "acs": _baseline_acs,
        "vlr": _baseline_vlr,
    }
    results: dict[str, tuple[SplitMetrics, SplitMetrics]] = {}
    for name, fn in extractors.items():
        pairs: dict[str, list[tuple[float, float]]] = {
            "train": [],
            "validation": [],
            "test": [],
        }
        for team_map in bundle.team_maps:
            rows = stats_by_map.get(team_map.match_map_id, [])
            if not rows:
                continue
            match = rows[0].match_map.match
            if match.team_a_id is None or match.team_b_id is None:
                continue
            team_a = [item for item in rows if item.team_id == match.team_a_id]
            team_b = [item for item in rows if item.team_id == match.team_b_id]
            if not team_a or not team_b:
                continue
            left = sum(fn(item) for item in team_a) / len(team_a)
            right = sum(fn(item) for item in team_b) / len(team_b)
            pairs[team_map.split].append((left - right, team_map.outcome_residual))
        train = pairs["train"]
        if not train:
            results[name] = (SplitMetrics(), SplitMetrics())
            continue
        x = np.array([item[0] for item in train], dtype=np.float64)
        y = np.array([item[1] for item in train], dtype=np.float64)
        if len(x) == 1 or np.allclose(x, x[0]):
            slope, intercept = 0.0, float(np.mean(y))
        else:
            fitted = np.polyfit(x, y, 1)
            slope, intercept = float(fitted[0]), float(fitted[1])

        def eval_split(
            split_name: str,
            *,
            slope: float = slope,
            intercept: float = intercept,
        ) -> SplitMetrics:
            rows = pairs[split_name]
            if not rows:
                return SplitMetrics()
            xs = np.array([item[0] for item in rows], dtype=np.float64)
            ys = np.array([item[1] for item in rows], dtype=np.float64)
            return split_metrics_from_arrays(ys, slope * xs + intercept)

        results[name] = (eval_split("validation"), eval_split("test"))
    return results


def _baseline_kd(stats: PlayerMapStats) -> float:
    return safe_ratio(stats.kills, stats.deaths) or 0.0


def _baseline_acs(stats: PlayerMapStats) -> float:
    return stats.acs or 0.0


def _baseline_vlr(stats: PlayerMapStats) -> float:
    return stats.vlr_rating or 0.0


__all__ = [
    "AppliedCombat",
    "apply_parameterization",
    "apply_pc1_pc2",
    "bootstrap_kind",
    "combat_coefficient",
    "player_combat_means",
    "profile_label",
    "to_primary_row",
    "train_kpr_ndpr_correlation",
    "univariate_baselines",
]
