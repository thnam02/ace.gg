from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy.orm import Session

from app.metrics.cir_features import missing_feature_names
from app.metrics.cir_scoring import (
    CIRModelCoefficients,
    apply_shrinkage,
    build_team_delta_vector,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_standardization import fit_standardization, standardize_features
from app.metrics.cir_v01 import CIR_V01_FEATURE_NAMES, DEFAULT_RIDGE_ALPHAS
from app.metrics.cir_validation_config import (
    ABLATION_VARIANTS,
    CIR_ROLES,
    SHRINKAGE_K_VALUES,
    STABILITY_ROUND_THRESHOLDS,
)
from app.metrics.cir_validation_metrics import (
    distribution_summary,
    mae,
    percentile,
    rank_stability,
    spearman_correlation,
)
from app.metrics.ridge_regression import (
    fit_ridge,
    predict_ridge,
    r2_score,
    rmse,
    select_ridge_alpha,
)
from app.models import PlayerMapStats
from app.schemas.cir_validation import (
    AblationReport,
    AblationResult,
    BaselineComparisonReport,
    BaselineMetricReport,
    CIRValidationResult,
    DatasetQualityReport,
    MissingFeatureAnalysisReport,
    MissingFeatureByGroupReport,
    MissingFeatureSplitReport,
    RoleBiasReport,
    RoleDistributionSummary,
    ShrinkageAnalysisReport,
    ShrinkageKReport,
    StabilityAnalysisReport,
    StabilityThresholdReport,
)
from app.services.cir_training_service import (
    CIREvaluationBundle,
    CIRTrainingService,
    _average_acs,
    _average_kd,
    _average_vlr,
    _fit_univariate,
    _PlayerMapPrepared,
    _team_metric_delta,
    _TeamMapPrepared,
)

_ROLE_BIAS_WARNING_THRESHOLD = 10.0
_ABLATION_NEGLIGIBLE_PCT = 0.2
_ABLATION_IMPROVE_PCT = 0.0


@dataclass
class _PlayerScore:
    player_id: UUID
    role: str | None
    cir: float
    shrunk_raw_cir: float
    rounds: int


class CIRValidationService:
    """Validate CIR v0.1 robustness, balance, and baseline usefulness."""

    def __init__(
        self,
        session: Session,
        *,
        training_service: CIRTrainingService | None = None,
    ) -> None:
        self._session = session
        self._training_service = training_service or CIRTrainingService(session)

    def validate_cir_v01(self) -> CIRValidationResult:
        bundle = self._training_service.prepare_evaluation_bundle()
        player_scores = self._player_scores(bundle)

        dataset_quality = self._dataset_quality(bundle)
        role_bias = self._role_bias(player_scores)
        baseline_comparison = self._baseline_comparison(bundle)
        ablation_results = self._ablation_study(bundle)
        shrinkage_analysis = self._shrinkage_analysis(bundle, player_scores)
        stability_analysis = self._stability_analysis(bundle)
        missing_feature_analysis = self._missing_feature_analysis(bundle)
        recommendations = self._build_recommendations(
            dataset_quality=dataset_quality,
            role_bias=role_bias,
            baseline_comparison=baseline_comparison,
            ablation_results=ablation_results,
            shrinkage_analysis=shrinkage_analysis,
            stability_analysis=stability_analysis,
            missing_feature_analysis=missing_feature_analysis,
        )

        return CIRValidationResult(
            dataset_quality=dataset_quality,
            role_bias=role_bias,
            baseline_comparison=baseline_comparison,
            ablation_results=ablation_results,
            shrinkage_analysis=shrinkage_analysis,
            stability_analysis=stability_analysis,
            missing_feature_analysis=missing_feature_analysis,
            recommendations=recommendations,
        )

    def _player_scores(self, bundle: CIREvaluationBundle) -> list[_PlayerScore]:
        players: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
        roles: dict[UUID, str | None] = {}
        for row in bundle.prepared_maps:
            raw_cir = compute_raw_cir(row.standardized_features, bundle.full_coefficients)
            players[row.stats.player_id].append((raw_cir, row.stats.rounds))
            agent = row.stats.agent
            roles[row.stats.player_id] = agent.role if agent is not None else None

        scores: list[_PlayerScore] = []
        for player_id, values in players.items():
            player_raw_cir = round_weighted_mean(values)
            rounds = sum(weight for _, weight in values)
            if player_raw_cir is None:
                continue
            shrunk = apply_shrinkage(
                player_raw_cir,
                rounds,
                bundle.reference_mean,
                bundle.shrinkage_k,
            )
            cir = empirical_cdf(shrunk, bundle.reference_population)
            scores.append(
                _PlayerScore(
                    player_id=player_id,
                    role=roles.get(player_id),
                    cir=cir,
                    shrunk_raw_cir=shrunk,
                    rounds=rounds,
                )
            )
        return scores

    def _dataset_quality(self, bundle: CIREvaluationBundle) -> DatasetQualityReport:
        prepared = bundle.prepared_maps
        players: set[UUID] = set()
        maps: set[UUID] = set()
        players_by_role: dict[str, int] = defaultdict(int)
        observations_by_role: dict[str, int] = defaultdict(int)
        observations_by_agent: dict[str, int] = defaultdict(int)
        observations_by_tier: dict[str, int] = defaultdict(int)
        rounds_per_player: dict[UUID, int] = defaultdict(int)
        missing_kast = 0
        missing_clutch = 0
        missing_opening = 0
        missing_adr = 0
        context_fallback_counts: dict[str, int] = defaultdict(int)
        neutralized: dict[str, int] = defaultdict(int)
        total_rounds = 0

        for row in prepared:
            stats = row.stats
            players.add(stats.player_id)
            maps.add(stats.match_map_id)
            total_rounds += stats.rounds
            rounds_per_player[stats.player_id] += stats.rounds

            role = stats.agent.role if stats.agent is not None else "Unknown"
            agent_name = stats.agent.name if stats.agent is not None else "Unknown"
            tier = stats.match_map.match.event.tier or "Unknown"
            observations_by_role[role] += 1
            observations_by_agent[agent_name] += 1
            observations_by_tier[tier] += 1

            if stats.kast_pct is None:
                missing_kast += 1
            if stats.clutch_attempts is None or stats.clutch_attempts == 0:
                missing_clutch += 1
            if stats.first_kills is None and stats.first_deaths is None:
                missing_opening += 1
            if stats.adr is None:
                missing_adr += 1

            level = row.baseline_level or "unknown"
            context_fallback_counts[level] += 1

            for feature_name in missing_feature_names(row.raw_features):
                neutralized[feature_name] += 1

        for player_id in players:
            sample = next(row for row in prepared if row.stats.player_id == player_id)
            role = sample.stats.agent.role if sample.stats.agent is not None else "Unknown"
            players_by_role[role] += 1

        player_round_list = list(rounds_per_player.values())
        total_obs = len(prepared)
        fallback_pct = {
            level: (count / total_obs * 100.0) if total_obs else 0.0
            for level, count in context_fallback_counts.items()
        }

        return DatasetQualityReport(
            total_players=len(players),
            total_maps=len(maps),
            total_player_map_observations=total_obs,
            total_rounds=total_rounds,
            players_by_role=dict(players_by_role),
            observations_by_role=dict(observations_by_role),
            observations_by_agent=dict(observations_by_agent),
            observations_by_tier=dict(observations_by_tier),
            median_rounds_per_player=percentile(player_round_list, 50),
            p25_rounds_per_player=percentile(player_round_list, 25),
            p75_rounds_per_player=percentile(player_round_list, 75),
            missing_kast=missing_kast,
            missing_clutch=missing_clutch,
            missing_opening=missing_opening,
            missing_adr=missing_adr,
            context_fallback_counts=dict(context_fallback_counts),
            context_fallback_percentages=fallback_pct,
            neutralized_missing_feature_counts=dict(neutralized),
        )

    def _role_bias(self, player_scores: list[_PlayerScore]) -> RoleBiasReport:
        by_role: dict[str, list[float]] = defaultdict(list)
        for score in player_scores:
            role = score.role or "Unknown"
            if role in CIR_ROLES:
                by_role[role].append(score.cir)

        distributions: list[RoleDistributionSummary] = []
        medians: dict[str, float | None] = {}
        for role in CIR_ROLES:
            values = by_role.get(role, [])
            summary = distribution_summary(values)
            distributions.append(
                RoleDistributionSummary(
                    role=role,
                    count=int(summary["count"] or 0),
                    mean=summary["mean"],
                    median=summary["median"],
                    std=summary["std"],
                    p10=summary["p10"],
                    p25=summary["p25"],
                    p75=summary["p75"],
                    p90=summary["p90"],
                )
            )
            medians[role] = summary["median"]

        pairwise: dict[str, float] = {}
        warnings: list[str] = []
        for i, role_a in enumerate(CIR_ROLES):
            for role_b in CIR_ROLES[i + 1:]:
                median_a = medians.get(role_a)
                median_b = medians.get(role_b)
                if median_a is None or median_b is None:
                    continue
                diff = median_a - median_b
                key = f"{role_a}_vs_{role_b}"
                pairwise[key] = diff
                if abs(diff) >= _ROLE_BIAS_WARNING_THRESHOLD:
                    higher = role_a if diff > 0 else role_b
                    lower = role_b if diff > 0 else role_a
                    warnings.append(
                        f"{higher} median CIR is {abs(diff):.1f} points above {lower} median"
                    )

        return RoleBiasReport(
            distributions=distributions,
            pairwise_median_differences=pairwise,
            warnings=warnings,
        )

    def _baseline_comparison(self, bundle: CIREvaluationBundle) -> BaselineComparisonReport:
        metrics: list[BaselineMetricReport] = []

        for split in ("validation", "test"):
            team_maps = [row for row in bundle.team_maps if row.split == split]
            if not team_maps:
                continue

            cir_report = self._evaluate_predictions(
                team_maps,
                bundle.full_coefficients,
                name="CIR",
                split=split,
            )
            metrics.append(cir_report)

            for baseline_name, metric_fn in (
                ("K/D", _average_kd),
                ("ACS", _average_acs),
                ("VLR Rating", _average_vlr),
            ):
                metrics.append(
                    self._evaluate_baseline_metric(
                        bundle,
                        team_maps,
                        metric_fn=metric_fn,
                        name=baseline_name,
                        split=split,
                    )
                )

        return BaselineComparisonReport(metrics=metrics)

    def _evaluate_predictions(
        self,
        team_maps: list[_TeamMapPrepared],
        coefficients: CIRModelCoefficients,
        *,
        name: str,
        split: str,
        feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
    ) -> BaselineMetricReport:
        design, targets = _design_matrix_for_features(team_maps, feature_names)
        if len(targets) == 0:
            return BaselineMetricReport(name=name, split=split)

        weights = np.array(
            [coefficients.coefficients.get(feature, 0.0) for feature in feature_names],
            dtype=np.float64,
        )
        predictions = predict_ridge(design, coefficients.intercept, weights)
        return BaselineMetricReport(
            name=name,
            split=split,
            rmse=rmse(targets, predictions),
            mae=mae(targets, predictions),
            r2=r2_score(targets, predictions),
            spearman=spearman_correlation(targets, predictions),
        )

    def _evaluate_baseline_metric(
        self,
        bundle: CIREvaluationBundle,
        team_maps: list[_TeamMapPrepared],
        *,
        metric_fn: Callable[[PlayerMapStats], float],
        name: str,
        split: str,
    ) -> BaselineMetricReport:
        train_maps = [row for row in bundle.team_maps if row.split == "train"]
        train_x: list[float] = []
        train_y: list[float] = []
        for team_map in train_maps:
            delta = self._team_metric_delta_for_map(bundle, team_map.match_map_id, metric_fn)
            train_x.append(delta)
            train_y.append(team_map.outcome_residual)

        if not train_x:
            return BaselineMetricReport(name=name, split=split)

        slope, intercept = _fit_univariate(train_x, train_y)

        eval_x: list[float] = []
        eval_y: list[float] = []
        for team_map in team_maps:
            delta = self._team_metric_delta_for_map(bundle, team_map.match_map_id, metric_fn)
            eval_x.append(delta)
            eval_y.append(team_map.outcome_residual)

        predictions = np.array(
            [slope * x + intercept for x in eval_x],
            dtype=np.float64,
        )
        targets = np.array(eval_y, dtype=np.float64)
        return BaselineMetricReport(
            name=name,
            split=split,
            rmse=rmse(targets, predictions),
            mae=mae(targets, predictions),
            r2=r2_score(targets, predictions),
            spearman=spearman_correlation(targets, predictions),
        )

    def _team_metric_delta_for_map(
        self,
        bundle: CIREvaluationBundle,
        match_map_id: UUID,
        metric_fn: Callable[[PlayerMapStats], float],
    ) -> float:
        rows = [row for row in bundle.prepared_maps if row.stats.match_map_id == match_map_id]
        if not rows:
            return 0.0
        match = rows[0].stats.match_map.match
        if match.team_a_id is None or match.team_b_id is None:
            return 0.0
        team_a = [row.stats for row in rows if row.stats.team_id == match.team_a_id]
        team_b = [row.stats for row in rows if row.stats.team_id == match.team_b_id]
        return _team_metric_delta(team_a, team_b, metric_fn)

    def _ablation_study(self, bundle: CIREvaluationBundle) -> AblationReport:
        full_val_rmse, full_test_rmse = self._split_rmse(bundle, bundle.full_coefficients)
        results: list[AblationResult] = []

        for variant, removed in ABLATION_VARIANTS.items():
            use_non_context = removed is None and variant == "without_context_adjustment"
            if variant == "full_model":
                feature_names = CIR_V01_FEATURE_NAMES
                source = "context"
            elif use_non_context:
                feature_names = CIR_V01_FEATURE_NAMES
                source = "non_context"
            else:
                removed_set = set(removed or ())
                feature_names = tuple(
                    name for name in CIR_V01_FEATURE_NAMES if name not in removed_set
                )
                source = "context"

            if not feature_names:
                continue

            coefficients, ridge_alpha, val_rmse, test_rmse, val_r2, test_r2 = (
                self._train_ablation_variant(bundle, feature_names, source=source)
            )

            coef_changes = {
                name: coefficients.coefficients.get(name, 0.0)
                - bundle.full_coefficients.coefficients.get(name, 0.0)
                for name in feature_names
            }

            val_delta = (
                None
                if val_rmse is None or full_val_rmse is None
                else val_rmse - full_val_rmse
            )
            test_delta = (
                None
                if test_rmse is None or full_test_rmse is None
                else test_rmse - full_test_rmse
            )
            impact = self._ablation_impact(val_delta, full_val_rmse)

            results.append(
                AblationResult(
                    variant=variant,
                    features_used=list(feature_names),
                    ridge_alpha=ridge_alpha,
                    validation_rmse=val_rmse,
                    test_rmse=test_rmse,
                    validation_r2=val_r2,
                    test_r2=test_r2,
                    coefficient_changes=coef_changes,
                    rmse_delta_vs_full_validation=val_delta,
                    rmse_delta_vs_full_test=test_delta,
                    impact=impact,
                )
            )

        return AblationReport(
            full_model_validation_rmse=full_val_rmse,
            full_model_test_rmse=full_test_rmse,
            results=results,
        )

    def _train_ablation_variant(
        self,
        bundle: CIREvaluationBundle,
        feature_names: tuple[str, ...],
        *,
        source: str,
    ) -> tuple[
        CIRModelCoefficients,
        float,
        float | None,
        float | None,
        float | None,
        float | None,
    ]:
        prepared = self._standardize_for_ablation(bundle.prepared_maps, feature_names, source)
        team_maps = self._rebuild_team_maps(prepared, bundle.team_maps, feature_names)

        train_maps = [row for row in team_maps if row.split == "train"]
        val_maps = [row for row in team_maps if row.split == "validation"]
        test_maps = [row for row in team_maps if row.split == "test"]

        train_design, train_targets = _design_matrix_for_features(train_maps, feature_names)
        val_design, val_targets = _design_matrix_for_features(val_maps, feature_names)
        test_design, test_targets = _design_matrix_for_features(test_maps, feature_names)

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
            coefficients={
                name: float(weights[index]) for index, name in enumerate(feature_names)
            },
        )

        val_rmse: float | None = None
        val_r2: float | None = None
        if len(val_targets) > 0:
            val_predictions = predict_ridge(val_design, intercept, weights)
            val_rmse = rmse(val_targets, val_predictions)
            val_r2 = r2_score(val_targets, val_predictions)

        test_rmse: float | None = None
        test_r2: float | None = None
        if len(test_targets) > 0:
            test_predictions = predict_ridge(test_design, intercept, weights)
            test_rmse = rmse(test_targets, test_predictions)
            test_r2 = r2_score(test_targets, test_predictions)

        return coefficients, ridge_alpha, val_rmse, test_rmse, val_r2, test_r2

    def _standardize_for_ablation(
        self,
        prepared_maps: list[_PlayerMapPrepared],
        feature_names: tuple[str, ...],
        source: str,
    ) -> list[_PlayerMapPrepared]:
        train_raw: list[dict[str, float | None]] = []
        for row in prepared_maps:
            if row.split != "train":
                continue
            raw = (
                row.non_context_features if source == "non_context" else row.raw_features
            )
            train_raw.append({name: raw.get(name) for name in feature_names})

        standardization = fit_standardization(train_raw)
        updated: list[_PlayerMapPrepared] = []
        for row in prepared_maps:
            raw = (
                row.non_context_features if source == "non_context" else row.raw_features
            )
            subset = {name: raw.get(name) for name in feature_names}
            standardized = standardize_features(subset, standardization)
            updated.append(
                _PlayerMapPrepared(
                    stats=row.stats,
                    split=row.split,
                    raw_features=row.raw_features,
                    standardized_features=standardized,
                    baseline_level=row.baseline_level,
                    non_context_features=row.non_context_features,
                )
            )
        return updated

    def _rebuild_team_maps(
        self,
        prepared_maps: list[_PlayerMapPrepared],
        original_team_maps: list[_TeamMapPrepared],
        feature_names: tuple[str, ...],
    ) -> list[_TeamMapPrepared]:
        grouped: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
        for row in prepared_maps:
            grouped[row.stats.match_map_id].append(row)

        rebuilt: list[_TeamMapPrepared] = []
        for team_map in original_team_maps:
            rows = grouped.get(team_map.match_map_id, [])
            if not rows:
                continue
            match = rows[0].stats.match_map.match
            team_a_rows = [row for row in rows if row.stats.team_id == match.team_a_id]
            team_b_rows = [row for row in rows if row.stats.team_id == match.team_b_id]
            deltas = build_team_delta_vector(
                [row.standardized_features for row in team_a_rows],
                [row.standardized_features for row in team_b_rows],
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

    def _split_rmse(
        self,
        bundle: CIREvaluationBundle,
        coefficients: CIRModelCoefficients,
    ) -> tuple[float | None, float | None]:
        val_maps = [row for row in bundle.team_maps if row.split == "validation"]
        test_maps = [row for row in bundle.team_maps if row.split == "test"]
        val_rmse = self._evaluate_predictions(
            val_maps, coefficients, name="CIR", split="validation"
        ).rmse
        test_rmse = self._evaluate_predictions(
            test_maps, coefficients, name="CIR", split="test"
        ).rmse
        return val_rmse, test_rmse

    def _ablation_impact(self, delta: float | None, baseline: float | None) -> str | None:
        if delta is None or baseline is None or baseline == 0.0:
            return None
        pct = abs(delta / baseline) * 100.0
        if delta < 0 and pct > _ABLATION_NEGLIGIBLE_PCT:
            return "improves"
        if pct <= _ABLATION_NEGLIGIBLE_PCT:
            return "negligible"
        return "harms"

    def _shrinkage_analysis(
        self,
        bundle: CIREvaluationBundle,
        reference_scores: list[_PlayerScore],
    ) -> ShrinkageAnalysisReport:
        reference_k = bundle.shrinkage_k
        reference_ranks = self._rank_map(reference_scores)

        raw_by_player: dict[UUID, tuple[float, int]] = {}
        for row in bundle.prepared_maps:
            raw_cir = compute_raw_cir(row.standardized_features, bundle.full_coefficients)
            player_id = row.stats.player_id
            if player_id not in raw_by_player:
                raw_by_player[player_id] = (0.0, 0)
            total_raw, total_rounds = raw_by_player[player_id]
            raw_by_player[player_id] = (
                total_raw + raw_cir * row.stats.rounds,
                total_rounds + row.stats.rounds,
            )

        player_raw: dict[UUID, float] = {}
        for player_id, (weighted_sum, rounds) in raw_by_player.items():
            if rounds > 0:
                player_raw[player_id] = weighted_sum / rounds

        results: list[ShrinkageKReport] = []
        best_k: float | None = None
        best_score = float("-inf")

        for k in SHRINKAGE_K_VALUES:
            cir_scores: list[float] = []
            ranks: dict[str, int] = {}
            ordered = sorted(
                reference_scores,
                key=lambda item: apply_shrinkage(
                    player_raw.get(item.player_id, 0.0),
                    item.rounds,
                    bundle.reference_mean,
                    k,
                ),
                reverse=True,
            )
            for index, item in enumerate(ordered):
                shrunk = apply_shrinkage(
                    player_raw.get(item.player_id, 0.0),
                    item.rounds,
                    bundle.reference_mean,
                    k,
                )
                cir = empirical_cdf(shrunk, bundle.reference_population)
                cir_scores.append(cir)
                ranks[str(item.player_id)] = index + 1

            stability = rank_stability(reference_ranks, ranks)
            score_array = np.array(cir_scores, dtype=np.float64)
            score_std = float(np.std(score_array)) if cir_scores else None
            validation_spearman = self._shrinkage_validation_association(bundle, k, player_raw)

            results.append(
                ShrinkageKReport(
                    k=k,
                    score_std=score_std,
                    rank_stability_vs_reference=stability,
                    validation_outcome_spearman=validation_spearman,
                )
            )

            if stability is not None:
                tradeoff = stability - (score_std or 0.0) * 0.01
                if tradeoff > best_score:
                    best_score = tradeoff
                    best_k = k

        recommended = best_k if best_k is not None and best_k != reference_k else None
        if recommended is None and results:
            val_stabilities = [
                (row.k, row.rank_stability_vs_reference or 0.0) for row in results
            ]
            recommended = max(val_stabilities, key=lambda item: item[1])[0]

        return ShrinkageAnalysisReport(
            reference_k=reference_k,
            recommended_k=recommended,
            results=results,
        )

    def _shrinkage_validation_association(
        self,
        bundle: CIREvaluationBundle,
        k: float,
        player_raw: dict[UUID, float],
    ) -> float | None:
        val_maps = [row for row in bundle.team_maps if row.split == "validation"]
        if not val_maps:
            return None

        deltas: list[float] = []
        targets: list[float] = []
        for team_map in val_maps:
            rows = [
                row
                for row in bundle.prepared_maps
                if row.stats.match_map_id == team_map.match_map_id
            ]
            if not rows:
                continue
            match = rows[0].stats.match_map.match
            team_a_delta = 0.0
            team_b_delta = 0.0
            for row in rows:
                raw = player_raw.get(row.stats.player_id, 0.0)
                shrunk = apply_shrinkage(
                    raw,
                    row.stats.rounds,
                    bundle.reference_mean,
                    k,
                )
                cir = empirical_cdf(shrunk, bundle.reference_population)
                if row.stats.team_id == match.team_a_id:
                    team_a_delta += cir
                elif row.stats.team_id == match.team_b_id:
                    team_b_delta += cir
            deltas.append(team_a_delta - team_b_delta)
            targets.append(team_map.outcome_residual)

        if len(deltas) < 2:
            return None
        return spearman_correlation(
            np.array(deltas, dtype=np.float64),
            np.array(targets, dtype=np.float64),
        )

    def _stability_analysis(self, bundle: CIREvaluationBundle) -> StabilityAnalysisReport:
        thresholds: list[StabilityThresholdReport] = []
        full_scores = self._player_scores(bundle)
        full_cir = {score.player_id: score.cir for score in full_scores}
        full_rounds = {score.player_id: score.rounds for score in full_scores}

        player_maps: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
        for row in bundle.prepared_maps:
            player_maps[row.stats.player_id].append(row)

        for player_id, rows in player_maps.items():
            rows.sort(
                key=lambda item: (
                    item.stats.match_map.match.played_at or UTC,
                    item.stats.match_map.match.vlr_match_id,
                    item.stats.match_map_id,
                )
            )

        for threshold in STABILITY_ROUND_THRESHOLDS:
            partial_cir: dict[UUID, float] = {}
            for player_id, rows in player_maps.items():
                cumulative = 0
                values: list[tuple[float, int]] = []
                for row in rows:
                    if cumulative >= threshold:
                        break
                    raw_cir = compute_raw_cir(row.standardized_features, bundle.full_coefficients)
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
                shrunk = apply_shrinkage(
                    raw,
                    cumulative,
                    bundle.reference_mean,
                    bundle.shrinkage_k,
                )
                partial_cir[player_id] = empirical_cdf(shrunk, bundle.reference_population)

            eligible = [
                player_id
                for player_id in partial_cir
                if full_rounds.get(player_id, 0) >= threshold
            ]
            if len(eligible) < 2:
                thresholds.append(
                    StabilityThresholdReport(
                        round_threshold=threshold,
                        eligible_players=len(eligible),
                    )
                )
                continue

            full_values = np.array(
                [full_cir[player_id] for player_id in eligible],
                dtype=np.float64,
            )
            partial_values = np.array(
                [partial_cir[player_id] for player_id in eligible],
                dtype=np.float64,
            )
            abs_diff = np.abs(full_values - partial_values)
            thresholds.append(
                StabilityThresholdReport(
                    round_threshold=threshold,
                    eligible_players=len(eligible),
                    spearman_rank_correlation=spearman_correlation(full_values, partial_values),
                    mean_absolute_cir_difference=float(np.mean(abs_diff)),
                    median_absolute_cir_difference=float(np.median(abs_diff)),
                )
            )

        return StabilityAnalysisReport(thresholds=thresholds)

    def _missing_feature_analysis(
        self,
        bundle: CIREvaluationBundle,
    ) -> MissingFeatureAnalysisReport:
        total = len(bundle.prepared_maps)
        missing_counts: dict[str, int] = defaultdict(int)
        for row in bundle.prepared_maps:
            for feature in missing_feature_names(row.raw_features):
                missing_counts[feature] += 1

        missing_rates = {
            feature: (missing_counts.get(feature, 0) / total * 100.0) if total else 0.0
            for feature in CIR_V01_FEATURE_NAMES
        }

        splits: list[MissingFeatureSplitReport] = []
        systematic: list[MissingFeatureByGroupReport] = []
        warnings: list[str] = []

        for split_name in ("validation", "test"):
            split_maps = [row for row in bundle.team_maps if row.split == split_name]
            complete_rmse, missing_rmse, complete_count, missing_count = (
                self._missing_split_rmse(bundle, split_maps)
            )
            splits.append(
                MissingFeatureSplitReport(
                    split=split_name,
                    complete_count=complete_count,
                    missing_count=missing_count,
                    validation_rmse_complete=complete_rmse,
                    validation_rmse_missing=missing_rmse,
                )
            )

        group_types = ("role", "agent", "tier", "event")
        for group_type in group_types:
            for feature in CIR_V01_FEATURE_NAMES:
                groups = self._missing_by_group(bundle, group_type, feature)
                if not groups:
                    continue
                rates = [rate for rate in groups.values() if rate > 0]
                if len(rates) < 2:
                    continue
                max_rate = max(rates)
                min_rate = min(rates)
                if max_rate - min_rate >= 20.0:
                    max_group = max(groups, key=lambda key: groups[key])
                    min_group = min(groups, key=lambda key: groups[key])
                    systematic.append(
                        MissingFeatureByGroupReport(
                            group_type=group_type,
                            group_value=max_group,
                            feature=feature,
                            missing_rate=groups[max_group],
                        )
                    )
                    warnings.append(
                        f"{feature} missingness for {group_type}={max_group} "
                        f"({groups[max_group]:.1f}%) exceeds "
                        f"{group_type}={min_group} ({groups[min_group]:.1f}%)"
                    )

        return MissingFeatureAnalysisReport(
            missing_rates_by_feature=missing_rates,
            splits=splits,
            systematic_by_group=systematic,
            warnings=warnings,
        )

    def _missing_split_rmse(
        self,
        bundle: CIREvaluationBundle,
        team_maps: list[_TeamMapPrepared],
    ) -> tuple[float | None, float | None, int, int]:
        complete_targets: list[float] = []
        complete_preds: list[float] = []
        missing_targets: list[float] = []
        missing_preds: list[float] = []
        complete_count = 0
        missing_count = 0

        weights = np.array(
            [
                bundle.full_coefficients.coefficients[name]
                for name in CIR_V01_FEATURE_NAMES
            ],
            dtype=np.float64,
        )

        for team_map in team_maps:
            rows = [
                row
                for row in bundle.prepared_maps
                if row.stats.match_map_id == team_map.match_map_id
            ]
            has_missing = any(missing_feature_names(row.raw_features) for row in rows)
            design, _ = _design_matrix_for_features([team_map], CIR_V01_FEATURE_NAMES)
            if design.shape[0] == 0:
                continue
            prediction = float(
                predict_ridge(design, bundle.full_coefficients.intercept, weights)[0]
            )
            if has_missing:
                missing_count += 1
                missing_targets.append(team_map.outcome_residual)
                missing_preds.append(prediction)
            else:
                complete_count += 1
                complete_targets.append(team_map.outcome_residual)
                complete_preds.append(prediction)

        complete_rmse = (
            rmse(
                np.array(complete_targets, dtype=np.float64),
                np.array(complete_preds, dtype=np.float64),
            )
            if complete_targets
            else None
        )
        missing_rmse = (
            rmse(
                np.array(missing_targets, dtype=np.float64),
                np.array(missing_preds, dtype=np.float64),
            )
            if missing_targets
            else None
        )
        return complete_rmse, missing_rmse, complete_count, missing_count

    def _missing_by_group(
        self,
        bundle: CIREvaluationBundle,
        group_type: str,
        feature: str,
    ) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        totals: dict[str, int] = defaultdict(int)
        for row in bundle.prepared_maps:
            if group_type == "role":
                group = row.stats.agent.role if row.stats.agent else "Unknown"
            elif group_type == "agent":
                group = row.stats.agent.name if row.stats.agent else "Unknown"
            elif group_type == "tier":
                group = row.stats.match_map.match.event.tier or "Unknown"
            else:
                group = row.stats.match_map.match.event.name or "Unknown"
            totals[group] += 1
            if row.raw_features.get(feature) is None:
                counts[group] += 1
        return {
            group: (counts[group] / totals[group] * 100.0) if totals[group] else 0.0
            for group in totals
        }

    def _rank_map(self, scores: list[_PlayerScore]) -> dict[str, int]:
        ordered = sorted(scores, key=lambda item: item.cir, reverse=True)
        return {str(item.player_id): index + 1 for index, item in enumerate(ordered)}

    def _build_recommendations(
        self,
        *,
        dataset_quality: DatasetQualityReport,
        role_bias: RoleBiasReport,
        baseline_comparison: BaselineComparisonReport,
        ablation_results: AblationReport,
        shrinkage_analysis: ShrinkageAnalysisReport,
        stability_analysis: StabilityAnalysisReport,
        missing_feature_analysis: MissingFeatureAnalysisReport,
    ) -> list[str]:
        recommendations: list[str] = []

        for warning in role_bias.warnings:
            recommendations.append(f"Role bias detected: {warning}; review role-normalization.")

        for result in ablation_results.results:
            if result.variant == "full_model":
                continue
            if result.impact == "improves" and result.rmse_delta_vs_full_validation is not None:
                pct = abs(result.rmse_delta_vs_full_validation / (
                    ablation_results.full_model_validation_rmse or 1.0
                )) * 100.0
                recommendations.append(
                    f"{result.variant} improved validation RMSE by {pct:.1f}%; "
                    "consider removing it in CIR v0.2."
                )
            elif result.impact == "negligible":
                recommendations.append(
                    f"{result.variant} had <{_ABLATION_NEGLIGIBLE_PCT:.1f}% effect; "
                    "likely redundant."
                )
            elif result.impact == "harms" and result.rmse_delta_vs_full_validation is not None:
                pct = abs(
                    result.rmse_delta_vs_full_validation / (
                        ablation_results.full_model_validation_rmse or 1.0
                    )
                ) * 100.0
                recommendations.append(
                    f"{result.variant} harmed validation RMSE by {pct:.1f}%; keep in CIR v0.2."
                )

        if shrinkage_analysis.recommended_k is not None:
            recommendations.append(
                f"k={shrinkage_analysis.recommended_k:.0f} produced the best "
                "validation stability/performance tradeoff."
            )

        for threshold in stability_analysis.thresholds:
            spearman = threshold.spearman_rank_correlation
            if spearman is not None and spearman >= 0.9:
                recommendations.append(
                    f"CIR stabilizes near {threshold.round_threshold} rounds "
                    f"(Spearman={threshold.spearman_rank_correlation:.2f})."
                )
                break

        role_levels = dataset_quality.context_fallback_percentages
        if len(role_levels) >= 2:
            sorted_levels = sorted(role_levels.items(), key=lambda item: item[1], reverse=True)
            high_level, high_pct = sorted_levels[0]
            low_level, low_pct = sorted_levels[-1]
            if high_pct - low_pct >= 15.0:
                recommendations.append(
                    f"Observations at baseline level '{high_level}' are "
                    f"{high_pct - low_pct:.1f}% more common than '{low_level}'."
                )

        duelist_rate = dataset_quality.observations_by_role.get("Duelist", 0)
        controller_rate = dataset_quality.observations_by_role.get("Controller", 0)
        total_obs = dataset_quality.total_player_map_observations
        if total_obs > 0 and duelist_rate > 0 and controller_rate > 0:
            duelist_fb = dataset_quality.context_fallback_percentages.get("global", 0.0)
            if duelist_fb > 0:
                recommendations.append(
                    f"Review context fallback usage ({duelist_fb:.1f}% global baseline)."
                )

        for warning in missing_feature_analysis.warnings[:3]:
            recommendations.append(f"Missing-feature pattern: {warning}")

        cir_val = next(
            (
                metric
                for metric in baseline_comparison.metrics
                if metric.name == "CIR" and metric.split == "validation"
            ),
            None,
        )
        kd_val = next(
            (
                metric
                for metric in baseline_comparison.metrics
                if metric.name == "K/D" and metric.split == "validation"
            ),
            None,
        )
        if cir_val and kd_val and cir_val.rmse is not None and kd_val.rmse is not None:
            if cir_val.rmse < kd_val.rmse:
                recommendations.append(
                    "CIR outperformed K/D on validation RMSE against outcome residual."
                )
            else:
                recommendations.append(
                    "CIR did not outperform K/D on validation RMSE; "
                    "baseline comparison inconclusive."
                )

        return recommendations


def _design_matrix_for_features(
    team_maps: list[_TeamMapPrepared],
    feature_names: tuple[str, ...],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if not team_maps:
        return np.empty((0, len(feature_names) + 1)), np.empty(0)
    rows = [
        [1.0] + [team_map.deltas.get(name, 0.0) for name in feature_names]
        for team_map in team_maps
    ]
    targets = [team_map.outcome_residual for team_map in team_maps]
    return np.array(rows, dtype=np.float64), np.array(targets, dtype=np.float64)
