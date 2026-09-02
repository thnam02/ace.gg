from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_feature_diagnostics import (
    PlayerFeatureRow,
    TeamFeatureRow,
    coefficient_signs,
    decide_feature_dispositions,
    diagnose_feature_distributions,
    diagnose_incremental_feature,
    diagnose_residual_adr_grouped,
    feature_correlations,
    pearson_correlation,
    recommend_cir_v02,
    select_feature_subset,
    within_rmse_slack,
)
from app.metrics.cir_feature_pruning_config import (
    DEFAULT_PRUNING_SHRINKAGE_K,
    PRUNING_CANDIDATE_FEATURES,
    STABILITY_ROUND_THRESHOLDS,
    default_feature_subset_matrix,
)
from app.metrics.cir_scoring import (
    CIRModelCoefficients,
    apply_shrinkage,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_v01 import DEFAULT_RIDGE_ALPHAS
from app.metrics.cir_validation_metrics import mae, spearman_correlation
from app.metrics.context_v2_config import recommended_context_v2_spec
from app.metrics.context_v2_diagnostics import role_bias_metrics
from app.metrics.ridge_regression import (
    fit_ridge,
    predict_ridge,
    r2_score,
    rmse,
    select_ridge_alpha,
)
from app.models import MetricVersion
from app.schemas.cir_feature_pruning import (
    FeaturePruningReport,
    FeatureSubsetResult,
    StabilityThresholdResult,
)
from app.schemas.context_v2 import SplitMetrics
from app.services.cir_training_service import (
    CIREvaluationBundle,
    CIRTrainingService,
    _coefficients_for_features,
    _design_matrix,
    _PlayerMapPrepared,
)
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from app.services.team_rating_service import TeamRatingService


@dataclass(frozen=True)
class _PlayerCir:
    cir: float
    rounds: int


class CirFeaturePruningService:
    """Diagnose and prune CIR candidate features without mutating CIR v0.1-real-2026."""

    def __init__(
        self,
        session: Session,
        *,
        require_complete_maps: bool = True,
        shrinkage_k: float = DEFAULT_PRUNING_SHRINKAGE_K,
        subset_matrix: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._session = session
        self._require_complete_maps = require_complete_maps
        self._shrinkage_k = shrinkage_k
        self._matrix = (
            subset_matrix if subset_matrix is not None else default_feature_subset_matrix()
        )
        self._team_rating_service = TeamRatingService(session)

    def run(self) -> FeaturePruningReport:
        preserved = self._snapshot_v01_real()
        self._team_rating_service.rebuild_team_ratings()
        spec = recommended_context_v2_spec()
        trainer = CIRTrainingService(
            self._session,
            require_complete_maps=self._require_complete_maps,
            persist=False,
            rebuild_ratings=False,
            context_mode=spec.mode,
            context_spec=spec,
            shrinkage_k=self._shrinkage_k,
            feature_names=PRUNING_CANDIDATE_FEATURES,
        )
        _training, bundle = trainer.fit_cir_v01()

        available = tuple(
            name for name in PRUNING_CANDIDATE_FEATURES if name in bundle.feature_names
        )
        subset_results: list[FeatureSubsetResult] = []
        for name, features in self._matrix.items():
            filtered = tuple(feature for feature in features if feature in available)
            if not filtered:
                continue
            subset_results.append(self._fit_subset(bundle, name, filtered))

        selected = select_feature_subset(subset_results)
        by_name = {item.name: item for item in subset_results}

        train_player_rows = self._player_rows(bundle, split="train")
        train_team_rows = self._team_rows(bundle, split="train")
        diagnostics = diagnose_feature_distributions(
            train_player_rows,
            features=available,
        )
        correlations = feature_correlations(train_team_rows, features=available)
        adr_diagnosis = diagnose_residual_adr_grouped(train_team_rows, train_player_rows)

        combat = by_name.get("combat_only")
        role_corrs = self._role_feature_correlations(train_player_rows)
        kast = diagnose_incremental_feature(
            feature="kast_residual",
            combat_rmse=_rmse(combat),
            with_feature_rmse=_rmse(by_name.get("combat_plus_kast")),
            combat_spearman=_spearman(combat),
            with_feature_spearman=_spearman(by_name.get("combat_plus_kast")),
            by_role_outcome_correlation=role_corrs.get("kast_residual", {}),
        )
        apr = diagnose_incremental_feature(
            feature="apr_residual",
            combat_rmse=_rmse(combat),
            with_feature_rmse=_rmse(by_name.get("combat_plus_apr")),
            combat_spearman=_spearman(combat),
            with_feature_spearman=_spearman(by_name.get("combat_plus_apr")),
            by_role_outcome_correlation=role_corrs.get("apr_residual", {}),
        )
        opening_both = by_name.get("combat_plus_opening")
        duelist_opening, non_duelist_opening = self._opening_role_correlations(train_player_rows)
        opening = diagnose_incremental_feature(
            feature="opening",
            combat_rmse=_rmse(combat),
            with_feature_rmse=_rmse(opening_both),
            combat_spearman=_spearman(combat),
            with_feature_spearman=_spearman(opening_both),
            by_role_outcome_correlation=role_corrs.get("opening_frequency_residual", {}),
            duelist_outcome_correlation=duelist_opening,
            non_duelist_outcome_correlation=non_duelist_opening,
            opening_style=True,
        )

        dispositions = decide_feature_dispositions(
            subset_by_name=by_name,
            residual_adr=adr_diagnosis,
            kast=kast,
            apr=apr,
            opening=opening,
            selected=selected,
        )
        stability_targets = self._stability_subsets(subset_results, selected)
        stability: list[StabilityThresholdResult] = []
        for item in stability_targets:
            coefficients = CIRModelCoefficients(
                intercept=0.0,
                coefficients=item.coefficients,
            )
            stability.extend(
                self._stability_for_subset(bundle, item.name, coefficients, item.features)
            )

        context_label = (
            f"Context v2; lambda={spec.lam:g}; tau={spec.tau:g}; "
            "KPR/DPR=role+tier; APR=agent+tier; KAST=role+tier; "
            "Opening=role; Residual ADR=none; Clutch=disabled"
        )
        reasons = [
            f"Selected {selected.name} from validation RMSE with a 1% simplicity tie-break.",
            "Test metrics were reported but not used for model selection.",
            (
                f"Validation RMSE={selected.validation_metrics.rmse} "
                f"MAE={selected.validation_metrics.mae} "
                f"R²={selected.validation_metrics.r2} "
                f"Spearman={selected.validation_metrics.spearman}."
            ),
            (
                f"max_role_median_gap={selected.role_bias_metrics.max_role_median_gap}; "
                "role medians were not equalized."
            ),
            f"Player shrinkage k={self._shrinkage_k} (configurable; not retuned here).",
            "CIR v0.2 was not implemented and v0.1-real-2026 was not overwritten.",
        ]
        recommendation = recommend_cir_v02(
            selected,
            shrinkage_k=self._shrinkage_k,
            context_label=context_label,
            reasons=reasons,
        )
        self._assert_v01_real_unchanged(preserved)
        return FeaturePruningReport(
            context_configuration=spec.configuration(),
            shrinkage_k=self._shrinkage_k,
            feature_diagnostics=diagnostics,
            feature_correlations=correlations,
            residual_adr_diagnosis=adr_diagnosis,
            kast_diagnosis=kast,
            apr_diagnosis=apr,
            opening_diagnosis=opening,
            subset_results=subset_results,
            selected_subset=selected.name,
            stability=stability,
            dispositions=dispositions,
            recommendation=recommendation,
            preserved_metric_version=CIR_REAL_EXPERIMENT_VERSION,
        )

    def _fit_subset(
        self,
        bundle: CIREvaluationBundle,
        name: str,
        features: tuple[str, ...],
    ) -> FeatureSubsetResult:
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
            DEFAULT_RIDGE_ALPHAS,
        )
        intercept, weights = fit_ridge(train_design, train_targets, ridge_alpha)
        coefficients = CIRModelCoefficients(
            intercept=intercept,
            coefficients=_coefficients_for_features(features, weights),
        )
        subset_coefs = {feature: coefficients.coefficients[feature] for feature in features}
        val_metrics = _split_metrics(val_design, val_targets, intercept, weights)
        test_metrics = _split_metrics(test_design, test_targets, intercept, weights)
        role_values = self._player_role_scores(bundle, coefficients, features)
        return FeatureSubsetResult(
            name=name,
            features=list(features),
            number_of_features=len(features),
            ridge_alpha=ridge_alpha,
            validation_metrics=val_metrics,
            test_metrics=test_metrics,
            coefficient_signs=coefficient_signs(subset_coefs),
            coefficient_magnitudes={key: abs(value) for key, value in subset_coefs.items()},
            coefficients=subset_coefs,
            role_bias_metrics=role_bias_metrics(role_values),
        )

    def _player_role_scores(
        self,
        bundle: CIREvaluationBundle,
        coefficients: CIRModelCoefficients,
        features: tuple[str, ...],
    ) -> dict[str, list[tuple[float, int]]]:
        by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
        roles: dict[UUID, str] = {}
        for row in bundle.prepared_maps:
            raw = compute_raw_cir(
                row.standardized_features,
                coefficients,
                feature_names=features,
            )
            by_player[row.stats.player_id].append((raw, row.stats.rounds))
            if row.stats.agent is not None:
                roles[row.stats.player_id] = row.stats.agent.role
        reference_mean = _player_reference_mean(
            by_player,
            train_ids={row.stats.player_id for row in bundle.prepared_maps if row.split == "train"},
        )
        reference_population = _player_reference_population(
            by_player,
            train_ids={row.stats.player_id for row in bundle.prepared_maps if row.split == "train"},
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
            cir = empirical_cdf(shrunk, reference_population)
            grouped[roles.get(player_id, "Unknown")].append((cir, rounds))
        return grouped

    def _stability_subsets(
        self,
        results: list[FeatureSubsetResult],
        selected: FeatureSubsetResult,
    ) -> list[FeatureSubsetResult]:
        by_name = {item.name: item for item in results}
        chosen = [selected]
        for name in ("combat_only", "full_candidate"):
            item = by_name.get(name)
            if item is not None and item.name != selected.name:
                chosen.append(item)
        for item in results:
            if item.name in {row.name for row in chosen}:
                continue
            if within_rmse_slack(item.validation_metrics.rmse, selected.validation_metrics.rmse):
                chosen.append(item)
        return chosen

    def _stability_for_subset(
        self,
        bundle: CIREvaluationBundle,
        subset_name: str,
        coefficients: CIRModelCoefficients,
        features: list[str],
    ) -> list[StabilityThresholdResult]:
        feature_names = tuple(features)
        full_scores = self._full_period_cir(bundle, coefficients, feature_names)
        player_maps: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
        for row in bundle.prepared_maps:
            player_maps[row.stats.player_id].append(row)
        for rows in player_maps.values():
            rows.sort(
                key=lambda item: (
                    item.stats.match_map.match.played_at or UTC,
                    item.stats.match_map.match.vlr_match_id,
                    item.stats.match_map_id,
                )
            )
        reports: list[StabilityThresholdResult] = []
        for threshold in STABILITY_ROUND_THRESHOLDS:
            partial: dict[UUID, float] = {}
            for player_id, rows in player_maps.items():
                cumulative = 0
                values: list[tuple[float, int]] = []
                for row in rows:
                    if cumulative >= threshold:
                        break
                    raw_cir = compute_raw_cir(
                        row.standardized_features,
                        coefficients,
                        feature_names=feature_names,
                    )
                    take_rounds = min(row.stats.rounds, threshold - cumulative)
                    if take_rounds <= 0:
                        break
                    values.append((raw_cir, take_rounds))
                    cumulative += take_rounds
                if cumulative < threshold:
                    continue
                raw = round_weighted_mean(values)
                if raw is None:
                    continue
                shrunk = apply_shrinkage(raw, cumulative, bundle.reference_mean, self._shrinkage_k)
                partial[player_id] = empirical_cdf(shrunk, bundle.reference_population)
            eligible = [
                player_id
                for player_id, score in full_scores.items()
                if player_id in partial and score.rounds >= threshold
            ]
            if len(eligible) < 2:
                reports.append(
                    StabilityThresholdResult(
                        subset=subset_name,
                        round_threshold=threshold,
                        eligible_players=len(eligible),
                    )
                )
                continue
            full_values = np.array(
                [full_scores[player_id].cir for player_id in eligible],
                dtype=np.float64,
            )
            partial_values = np.array(
                [partial[player_id] for player_id in eligible],
                dtype=np.float64,
            )
            abs_diff = np.abs(full_values - partial_values)
            reports.append(
                StabilityThresholdResult(
                    subset=subset_name,
                    round_threshold=threshold,
                    eligible_players=len(eligible),
                    spearman_vs_full=spearman_correlation(full_values, partial_values),
                    mean_absolute_cir_difference=float(np.mean(abs_diff)),
                    median_absolute_cir_difference=float(np.median(abs_diff)),
                )
            )
        return reports

    def _full_period_cir(
        self,
        bundle: CIREvaluationBundle,
        coefficients: CIRModelCoefficients,
        features: tuple[str, ...],
    ) -> dict[UUID, _PlayerCir]:
        by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
        for row in bundle.prepared_maps:
            raw = compute_raw_cir(
                row.standardized_features,
                coefficients,
                feature_names=features,
            )
            by_player[row.stats.player_id].append((raw, row.stats.rounds))
        scores: dict[UUID, _PlayerCir] = {}
        for player_id, values in by_player.items():
            raw_mean = round_weighted_mean(values)
            rounds = sum(weight for _, weight in values)
            if raw_mean is None:
                continue
            shrunk = apply_shrinkage(raw_mean, rounds, bundle.reference_mean, self._shrinkage_k)
            scores[player_id] = _PlayerCir(
                cir=empirical_cdf(shrunk, bundle.reference_population),
                rounds=rounds,
            )
        return scores

    def _player_rows(
        self,
        bundle: CIREvaluationBundle,
        *,
        split: str,
    ) -> list[PlayerFeatureRow]:
        team_lookup = {row.match_map_id: row for row in bundle.team_maps}
        rows: list[PlayerFeatureRow] = []
        for row in bundle.prepared_maps:
            if row.split != split:
                continue
            team_map = team_lookup.get(row.stats.match_map_id)
            signed = None
            if team_map is not None:
                match = row.stats.match_map.match
                if row.stats.team_id == match.team_a_id:
                    signed = team_map.outcome_residual
                elif row.stats.team_id == match.team_b_id:
                    signed = -team_map.outcome_residual
            event = row.stats.match_map.match.event
            rows.append(
                PlayerFeatureRow(
                    values=row.raw_features,
                    role=row.stats.agent.role if row.stats.agent is not None else "Unknown",
                    tier=(event.tier or "Unknown") if event is not None else "Unknown",
                    split=row.split,
                    signed_outcome=signed,
                )
            )
        return rows

    def _team_rows(self, bundle: CIREvaluationBundle, *, split: str) -> list[TeamFeatureRow]:
        return [
            TeamFeatureRow(
                deltas=row.deltas, outcome_residual=row.outcome_residual, split=row.split
            )
            for row in bundle.team_maps
            if row.split == split
        ]

    def _role_feature_correlations(
        self,
        rows: list[PlayerFeatureRow],
    ) -> dict[str, dict[str, float | None]]:
        by_feature: dict[str, dict[str, float | None]] = {}
        for feature in ("apr_residual", "kast_residual", "opening_frequency_residual"):
            by_role: dict[str, float | None] = {}
            for role in ("Controller", "Initiator", "Duelist", "Sentinel"):
                role_rows = [row for row in rows if row.role == role]
                by_role[role] = _feature_outcome_corr(role_rows, feature)
            by_feature[feature] = by_role
        return by_feature

    def _opening_role_correlations(
        self,
        rows: list[PlayerFeatureRow],
    ) -> tuple[float | None, float | None]:
        duelist = [row for row in rows if row.role == "Duelist"]
        others = [row for row in rows if row.role != "Duelist"]
        return (
            _feature_outcome_corr(duelist, "opening_frequency_residual"),
            _feature_outcome_corr(others, "opening_frequency_residual"),
        )

    def _snapshot_v01_real(self) -> dict[str, object] | None:
        version = self._session.scalar(
            select(MetricVersion).where(
                MetricVersion.name == "CIR",
                MetricVersion.version == CIR_REAL_EXPERIMENT_VERSION,
            )
        )
        if version is None:
            return None
        return {
            "coefficients": dict(version.model_coefficients),
            "standardization": dict(version.standardization_parameters),
            "regularization": dict(version.regularization_parameters),
            "shrinkage": dict(version.shrinkage_parameters),
            "reference": dict(version.reference_population),
            "feature_names": list(version.feature_names),
        }

    def _assert_v01_real_unchanged(self, preserved: dict[str, object] | None) -> None:
        current = self._snapshot_v01_real()
        if preserved is None:
            return
        if current != preserved:
            raise RuntimeError(
                f"{CIR_REAL_EXPERIMENT_VERSION} changed during the CIR feature pruning experiment"
            )


def _rmse(result: FeatureSubsetResult | None) -> float | None:
    if result is None:
        return None
    return result.validation_metrics.rmse


def _spearman(result: FeatureSubsetResult | None) -> float | None:
    if result is None:
        return None
    return result.validation_metrics.spearman


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


def _feature_outcome_corr(rows: list[PlayerFeatureRow], feature: str) -> float | None:
    values: list[float] = []
    outcomes: list[float] = []
    for row in rows:
        value = row.values.get(feature)
        if value is None or row.signed_outcome is None:
            continue
        values.append(float(value))
        outcomes.append(float(row.signed_outcome))
    return pearson_correlation(values, outcomes)


def _player_reference_mean(
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


def _player_reference_population(
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
