from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.metrics.cir_scoring import (
    CIRModelCoefficients,
    apply_shrinkage,
    build_team_delta_vector,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_standardization import StandardizationParams
from app.metrics.cir_validation_metrics import mae, spearman_correlation
from app.metrics.context_v2_config import CONTEXT_MODE_V2
from app.metrics.context_v2_diagnostics import role_bias_metrics
from app.metrics.mir.mir_config import (
    ALL_MODEL_FEATURES,
    DEFAULT_MIR_SHRINKAGE_K,
    MIR_METRIC_NAME,
    MIR_RIDGE_ALPHAS,
    MIR_V01_EXPERIMENTAL_VERSION,
    STABILITY_ROUND_THRESHOLDS,
    mir_context_spec,
)
from app.metrics.mir.mir_residualization import MirResidualizers
from app.metrics.mir.mir_scoring import enabled_component_names
from app.metrics.ridge_regression import (
    fit_ridge,
    predict_ridge,
    r2_score,
    rmse,
    select_ridge_alpha,
)
from app.models import MetricVersion
from app.schemas.context_v2 import SplitMetrics
from app.schemas.mir_experiment import MirStabilityRow, MirSubsetResult
from app.services.cir_training_service import (
    CIREvaluationBundle,
    CIRTrainingService,
    _design_matrix,
    _TeamMapPrepared,
)
from app.services.mir_feature_service import MirFeatureService, MirPlayerMap
from app.services.team_rating_service import TeamRatingService


@dataclass
class MirEvaluationBundle:
    player_maps: list[MirPlayerMap]
    team_maps: list[_TeamMapPrepared]
    residualizers: MirResidualizers
    standardization: StandardizationParams
    feature_names: tuple[str, ...]
    shrinkage_k: float
    cir_bundle: CIREvaluationBundle


class MirTrainingService:
    """Fit MIR Ridge models without mutating CIR MetricVersions."""

    def __init__(
        self,
        session: Session,
        *,
        require_complete_maps: bool = True,
        shrinkage_k: float = DEFAULT_MIR_SHRINKAGE_K,
        persist: bool = False,
        persist_version: str = MIR_V01_EXPERIMENTAL_VERSION,
        rebuild_ratings: bool = True,
    ) -> None:
        self._session = session
        self._require_complete_maps = require_complete_maps
        self._shrinkage_k = shrinkage_k
        self._persist = persist
        self._persist_version = persist_version
        self._rebuild_ratings = rebuild_ratings
        self._team_rating_service = TeamRatingService(session)
        self._features = MirFeatureService()

    def prepare_bundle(self) -> MirEvaluationBundle:
        if self._rebuild_ratings:
            self._team_rating_service.rebuild_team_ratings()
        spec = mir_context_spec()
        trainer = CIRTrainingService(
            self._session,
            require_complete_maps=self._require_complete_maps,
            persist=False,
            rebuild_ratings=False,
            context_mode=CONTEXT_MODE_V2,
            context_spec=spec,
            shrinkage_k=self._shrinkage_k,
            feature_names=(
                "kpr_residual",
                "negative_dpr_residual",
                "apr_residual",
                "kast_residual",
                "opening_frequency_residual",
                "opening_efficiency_adjusted",
            ),
        )
        _training, cir_bundle = trainer.fit_cir_v01()
        player_maps, residualizers, standardization = self._features.transform(
            cir_bundle.prepared_maps,
            feature_names=ALL_MODEL_FEATURES,
        )
        team_maps = _rebuild_team_maps(cir_bundle.team_maps, player_maps, ALL_MODEL_FEATURES)
        return MirEvaluationBundle(
            player_maps=player_maps,
            team_maps=team_maps,
            residualizers=residualizers,
            standardization=standardization,
            feature_names=ALL_MODEL_FEATURES,
            shrinkage_k=self._shrinkage_k,
            cir_bundle=cir_bundle,
        )

    def fit_subset(
        self,
        bundle: MirEvaluationBundle,
        name: str,
        features: tuple[str, ...],
    ) -> MirSubsetResult:
        train_maps = [row for row in bundle.team_maps if row.split == "train"]
        val_maps = [row for row in bundle.team_maps if row.split == "validation"]
        test_maps = [row for row in bundle.team_maps if row.split == "test"]
        train_design, train_targets = _design_matrix(train_maps, feature_names=features)
        val_design, val_targets = _design_matrix(val_maps, feature_names=features)
        test_design, test_targets = _design_matrix(test_maps, feature_names=features)
        ridge_alpha = select_ridge_alpha(
            train_design,
            train_targets,
            val_design if len(val_targets) > 0 else train_design,
            val_targets if len(val_targets) > 0 else train_targets,
            MIR_RIDGE_ALPHAS,
        )
        intercept, weights = fit_ridge(train_design, train_targets, ridge_alpha)
        coefficients = {feature: float(weights[index]) for index, feature in enumerate(features)}
        model = CIRModelCoefficients(intercept=intercept, coefficients=coefficients)
        role_values = self.player_role_scores(bundle, model, features)
        t1_coefs, t2_coefs = _tier_extra_coefficients(bundle, features)
        return MirSubsetResult(
            name=name,
            features=list(features),
            number_of_features=len(features),
            ridge_alpha=ridge_alpha,
            validation_metrics=_split_metrics(val_design, val_targets, intercept, weights),
            test_metrics=_split_metrics(test_design, test_targets, intercept, weights),
            coefficients=coefficients,
            coefficient_signs=_signs(coefficients),
            role_bias_metrics=role_bias_metrics(role_values),
            t1_extra_coefficients=t1_coefs,
            t2_extra_coefficients=t2_coefs,
        )

    def player_role_scores(
        self,
        bundle: MirEvaluationBundle,
        coefficients: CIRModelCoefficients,
        features: tuple[str, ...],
    ) -> dict[str, list[tuple[float, int]]]:
        by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
        roles: dict[UUID, str] = {}
        train_ids: set[UUID] = set()
        for row in bundle.player_maps:
            raw = compute_raw_cir(row.standardized_features, coefficients, feature_names=features)
            by_player[row.stats.player_id].append((raw, row.stats.rounds))
            roles[row.stats.player_id] = row.role
            if row.split == "train":
                train_ids.add(row.stats.player_id)
        reference_mean = _reference_mean(by_player, train_ids)
        population = _reference_population(
            by_player,
            train_ids=train_ids,
            reference_mean=reference_mean,
            shrinkage_k=self._shrinkage_k,
        )
        grouped: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for player_id, values in by_player.items():
            raw_mean = round_weighted_mean(values)
            rounds = sum(weight for _, weight in values)
            if raw_mean is None:
                continue
            shrunk = apply_shrinkage(raw_mean, rounds, reference_mean, self._shrinkage_k)
            score = empirical_cdf(shrunk, population)
            grouped[roles.get(player_id, "Unknown")].append((score, rounds))
        return grouped

    def persist_metric_version(
        self,
        bundle: MirEvaluationBundle,
        subset: MirSubsetResult,
    ) -> MetricVersion:
        self._session.execute(
            delete(MetricVersion).where(
                MetricVersion.name == MIR_METRIC_NAME,
                MetricVersion.version == self._persist_version,
            )
        )
        version = MetricVersion(
            name=MIR_METRIC_NAME,
            version=self._persist_version,
            feature_names=list(subset.features),
            standardization_parameters=bundle.standardization.to_dict(),
            model_coefficients={
                "intercept": 0.0,
                "coefficients": subset.coefficients,
            },
            regularization_parameters={
                "alpha": subset.ridge_alpha,
                "residualizers": bundle.residualizers.to_dict(),
                "enabled_components": enabled_component_names(tuple(subset.features)),
                "validation_metrics": subset.validation_metrics.model_dump(),
                "test_metrics": subset.test_metrics.model_dump(),
                "context": mir_context_spec().configuration(),
            },
            shrinkage_parameters={"k": self._shrinkage_k},
            reference_population={"note": "experimental; player snapshots not written"},
        )
        self._session.add(version)
        self._session.flush()
        return version


def stability_rows(
    bundle: MirEvaluationBundle,
    subset: MirSubsetResult,
    shrinkage_k: float,
) -> list[MirStabilityRow]:
    features = tuple(subset.features)
    coefficients = CIRModelCoefficients(intercept=0.0, coefficients=subset.coefficients)
    full_scores = _full_period_scores(bundle, coefficients, features, shrinkage_k)
    player_maps: dict[UUID, list[MirPlayerMap]] = defaultdict(list)
    for row in bundle.player_maps:
        player_maps[row.stats.player_id].append(row)
    for rows in player_maps.values():
        rows.sort(
            key=lambda item: (
                item.stats.match_map.match.played_at or UTC,
                item.stats.match_map.match.vlr_match_id,
                item.stats.match_map_id,
            )
        )
    reports: list[MirStabilityRow] = []
    for threshold in STABILITY_ROUND_THRESHOLDS:
        partial: dict[UUID, float] = {}
        for player_id, rows in player_maps.items():
            cumulative = 0
            values: list[tuple[float, int]] = []
            for row in rows:
                if cumulative >= threshold:
                    break
                raw = compute_raw_cir(
                    row.standardized_features,
                    coefficients,
                    feature_names=features,
                )
                take = min(row.stats.rounds, threshold - cumulative)
                if take <= 0:
                    break
                values.append((raw, take))
                cumulative += take
            if cumulative < threshold:
                continue
            raw_mean = round_weighted_mean(values)
            if raw_mean is None:
                continue
            # Use combat-only CIR bundle reference for scale consistency of CDF.
            shrunk = apply_shrinkage(
                raw_mean, cumulative, bundle.cir_bundle.reference_mean, shrinkage_k
            )
            partial[player_id] = empirical_cdf(shrunk, bundle.cir_bundle.reference_population)
        eligible = [
            player_id
            for player_id, score in full_scores.items()
            if player_id in partial and score[1] >= threshold
        ]
        if len(eligible) < 2:
            reports.append(
                MirStabilityRow(
                    subset=subset.name,
                    round_threshold=threshold,
                    eligible_players=len(eligible),
                )
            )
            continue
        full_values = np.array(
            [full_scores[player_id][0] for player_id in eligible], dtype=np.float64
        )
        partial_values = np.array([partial[player_id] for player_id in eligible], dtype=np.float64)
        abs_diff = np.abs(full_values - partial_values)
        reports.append(
            MirStabilityRow(
                subset=subset.name,
                round_threshold=threshold,
                eligible_players=len(eligible),
                spearman_vs_full=spearman_correlation(full_values, partial_values),
                mean_absolute_mir_difference=float(np.mean(abs_diff)),
                median_absolute_mir_difference=float(np.median(abs_diff)),
            )
        )
    return reports


def _rebuild_team_maps(
    cir_team_maps: list[_TeamMapPrepared],
    player_maps: list[MirPlayerMap],
    feature_names: tuple[str, ...],
) -> list[_TeamMapPrepared]:
    grouped: dict[UUID, list[MirPlayerMap]] = defaultdict(list)
    for row in player_maps:
        grouped[row.stats.match_map_id].append(row)
    rebuilt: list[_TeamMapPrepared] = []
    for team_map in cir_team_maps:
        rows = grouped.get(team_map.match_map_id, [])
        if not rows:
            continue
        match = rows[0].stats.match_map.match
        if match.team_a_id is None or match.team_b_id is None:
            continue
        team_a = [row for row in rows if row.stats.team_id == match.team_a_id]
        team_b = [row for row in rows if row.stats.team_id == match.team_b_id]
        deltas = build_team_delta_vector(
            [row.standardized_features for row in team_a],
            [row.standardized_features for row in team_b],
            feature_names=feature_names,
        )
        rebuilt.append(
            _TeamMapPrepared(
                match_map_id=team_map.match_map_id,
                split=team_map.split,
                outcome_residual=team_map.outcome_residual,
                deltas=deltas,
            )
        )
    return rebuilt


def _split_metrics(
    design: NDArray[np.float64],
    targets: NDArray[np.float64],
    intercept: float,
    weights: NDArray[np.float64],
) -> SplitMetrics:
    if len(targets) == 0:
        return SplitMetrics()
    predictions = predict_ridge(design, intercept, weights)
    return SplitMetrics(
        rmse=rmse(targets, predictions),
        mae=mae(targets, predictions),
        r2=r2_score(targets, predictions),
        spearman=spearman_correlation(targets, predictions),
    )


def _signs(coefficients: dict[str, float]) -> dict[str, str]:
    signs: dict[str, str] = {}
    for name, value in coefficients.items():
        if value > 0:
            signs[name] = "+"
        elif value < 0:
            signs[name] = "-"
        else:
            signs[name] = "0"
    return signs


def _tier_extra_coefficients(
    bundle: MirEvaluationBundle,
    features: tuple[str, ...],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    extra = [
        name
        for name in features
        if name not in {"kpr_context_residual", "negative_dpr_context_residual"}
    ]
    t1 = _fit_extra_coefs(bundle, features, extra, "T1")
    t2 = _fit_extra_coefs(bundle, features, extra, "T2")
    return t1, t2


def _fit_extra_coefs(
    bundle: MirEvaluationBundle,
    features: tuple[str, ...],
    extra: list[str],
    tier: str,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {name: None for name in extra}
    if not extra:
        return result
    map_tier: dict[UUID, str] = {}
    for row in bundle.player_maps:
        map_tier[row.stats.match_map_id] = row.tier
    train_maps = [
        row
        for row in bundle.team_maps
        if row.split == "train" and map_tier.get(row.match_map_id) == tier
    ]
    val_maps = [
        row
        for row in bundle.team_maps
        if row.split == "validation" and map_tier.get(row.match_map_id) == tier
    ]
    if len(train_maps) < 8:
        return result
    train_design, train_targets = _design_matrix(train_maps, feature_names=features)
    val_design, val_targets = _design_matrix(
        val_maps if val_maps else train_maps,
        feature_names=features,
    )
    alpha = select_ridge_alpha(
        train_design,
        train_targets,
        val_design,
        val_targets,
        MIR_RIDGE_ALPHAS,
    )
    _intercept, weights = fit_ridge(train_design, train_targets, alpha)
    for index, name in enumerate(features):
        if name in result:
            result[name] = float(weights[index])
    return result


def _reference_mean(
    by_player: dict[UUID, list[tuple[float, int]]],
    train_ids: set[UUID],
) -> float:
    values: list[float] = []
    for player_id in train_ids:
        mean = round_weighted_mean(by_player.get(player_id, []))
        if mean is not None:
            values.append(mean)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _reference_population(
    by_player: dict[UUID, list[tuple[float, int]]],
    *,
    train_ids: set[UUID],
    reference_mean: float,
    shrinkage_k: float,
) -> list[float]:
    population: list[float] = []
    for player_id in train_ids:
        values = by_player.get(player_id, [])
        raw = round_weighted_mean(values)
        if raw is None:
            continue
        rounds = sum(weight for _, weight in values)
        population.append(apply_shrinkage(raw, rounds, reference_mean, shrinkage_k))
    return population


def _full_period_scores(
    bundle: MirEvaluationBundle,
    coefficients: CIRModelCoefficients,
    features: tuple[str, ...],
    shrinkage_k: float,
) -> dict[UUID, tuple[float, int]]:
    by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
    train_ids = {row.stats.player_id for row in bundle.player_maps if row.split == "train"}
    for row in bundle.player_maps:
        raw = compute_raw_cir(row.standardized_features, coefficients, feature_names=features)
        by_player[row.stats.player_id].append((raw, row.stats.rounds))
    reference_mean = _reference_mean(by_player, train_ids)
    population = _reference_population(
        by_player,
        train_ids=train_ids,
        reference_mean=reference_mean,
        shrinkage_k=shrinkage_k,
    )
    scores: dict[UUID, tuple[float, int]] = {}
    for player_id, values in by_player.items():
        raw_mean = round_weighted_mean(values)
        rounds = sum(weight for _, weight in values)
        if raw_mean is None:
            continue
        shrunk = apply_shrinkage(raw_mean, rounds, reference_mean, shrinkage_k)
        scores[player_id] = (empirical_cdf(shrunk, population), rounds)
    return scores
