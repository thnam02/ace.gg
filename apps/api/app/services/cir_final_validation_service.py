from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_final_validation import (
    audit_failure_conditions,
    build_recommendation,
    chronological_two_way,
    coefficient_sign,
    coefficient_summary,
    decide_readiness,
    numeric_summary,
    ordered_player_ids,
    rank_map,
    rank_movement,
    ranking_correlations,
    recommend_sample_threshold,
    relative_rmse_increase,
    second_feature_adds_value,
    split_metrics_from_arrays,
    top_n_retention,
)
from app.metrics.cir_final_validation_config import (
    BOOTSTRAP_SEED,
    DEFAULT_BOOTSTRAP_ITERATIONS,
    FROZEN_COMBAT_FEATURES,
    FROZEN_SHRINKAGE_K,
    KPR_FEATURE,
    LATER_EVENT_RMSE_RATIO_LIMIT,
    MIN_TRAIN_TEAM_MAPS,
    NEGATIVE_DPR_FEATURE,
    NESTED_TRAIN_FRACTION,
    PRIMARY_TRAIN_FRACTION,
    PRIMARY_VALIDATION_FRACTION,
    RANKING_ROUND_THRESHOLDS,
    REGION_LABELS,
    SAMPLE_SIZE_THRESHOLDS,
    SMALL_REGION_MAPS,
    TEMPORAL_SPLIT_GRID,
    frozen_context_spec,
)
from app.metrics.cir_scoring import CIRModelCoefficients
from app.metrics.cir_v01 import CIR_V01_FEATURE_NAMES
from app.metrics.cir_validation_config import CIR_ROLES
from app.metrics.cir_validation_metrics import (
    distribution_summary,
    percentile,
    spearman_correlation,
)
from app.metrics.context_v2_config import CONTEXT_MODE_NONE, CONTEXT_MODE_V1, CONTEXT_MODE_V2
from app.metrics.context_v2_diagnostics import role_bias_metrics
from app.metrics.derived import safe_ratio
from app.metrics.ridge_regression import fit_ridge, predict_ridge
from app.models import MetricVersion, PlayerMapStats
from app.schemas.cir_final_validation import (
    AggregationSanityResult,
    BaselineExactComparison,
    BootstrapResult,
    CIRFinalValidationReport,
    CombatRedundancyResult,
    ContextSensitivityResult,
    EventHoldoutResult,
    LeakageAuditItem,
    PlayerScoreUncertainty,
    RankingStabilityResult,
    RegionResult,
    RoleResult,
    RollingFoldResult,
    RollingValidationSummary,
    SampleSizeResult,
    TargetSensitivityResult,
    TemporalSplitResult,
    TierResult,
)
from app.schemas.context_v2 import SplitMetrics
from app.services.cir_final_validation_support import (
    PlayerScore,
    as_float,
    bootstrap_player_draws,
    coef_stability,
    fit_feature_subset,
    fit_ridge_on_maps,
    gap_from_scores,
    map_count,
    maps_by_event,
    match_id_for,
    match_ids_for_maps,
    metrics_for_split,
    order_maps,
    ordered_events,
    partial_period_scores,
    player_scores,
    predict_team_maps,
    region_by_map,
    resample_match_ids,
    role_outcome_corr,
    score_spearman,
    split_ids,
    split_periods,
    team_maps_mean_aggregated,
    team_maps_with_raw_target,
)
from app.services.cir_training_service import (
    CIREvaluationBundle,
    CIRTrainingService,
    _chronological_map_ids,
    _coefficients_for_features,
    _design_matrix,
    _TeamMapPrepared,
)
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from app.services.team_rating_service import TeamRatingService


@dataclass
class _FoldOutcome:
    bundle: CIREvaluationBundle
    coefficients: CIRModelCoefficients
    ridge_alpha: float
    val_metrics: SplitMetrics
    test_metrics: SplitMetrics
    role_gap: float | None
    player_scores: dict[UUID, PlayerScore]


class CirFinalValidationService:
    """Robustness checks for the frozen combat-only CIR candidate. Does not persist."""

    def __init__(
        self,
        session: Session,
        *,
        require_complete_maps: bool = True,
        shrinkage_k: float = FROZEN_SHRINKAGE_K,
        bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
        bootstrap_seed: int = BOOTSTRAP_SEED,
    ) -> None:
        self._session = session
        self._require_complete_maps = require_complete_maps
        self._shrinkage_k = shrinkage_k
        self._bootstrap_iterations = bootstrap_iterations
        self._bootstrap_seed = bootstrap_seed
        self._spec = frozen_context_spec()
        self._features = FROZEN_COMBAT_FEATURES
        self._team_rating_service = TeamRatingService(session)

    def run(self) -> CIRFinalValidationReport:
        preserved = self._snapshot_v01_real()
        self._team_rating_service.rebuild_team_ratings()
        primary_fit = self._fit()
        assert primary_fit is not None
        bundle = primary_fit.bundle
        primary = self._temporal_from_fit(
            "70/15/15",
            primary_fit,
            train_fraction=PRIMARY_TRAIN_FRACTION,
            validation_fraction=PRIMARY_VALIDATION_FRACTION,
        )
        primary_ids = split_ids(bundle)
        coef_kpr: list[float] = []
        coef_ndpr: list[float] = []
        alphas: list[float] = []
        role_gaps: list[float] = []
        self._collect_coefs(primary_fit, coef_kpr, coef_ndpr, alphas, role_gaps)

        temporal = [primary]
        for train_frac, val_frac in TEMPORAL_SPLIT_GRID:
            if abs(train_frac - PRIMARY_TRAIN_FRACTION) < 1e-9:
                continue
            fit = self._fit(train_fraction=train_frac, validation_fraction=val_frac)
            if fit is None:
                continue
            row = self._temporal_from_fit(
                f"{train_frac:.3g}/{val_frac:.3g}/{1 - train_frac - val_frac:.3g}",
                fit,
                train_fraction=train_frac,
                validation_fraction=val_frac,
            )
            increase = relative_rmse_increase(
                primary.validation_metrics.rmse, row.validation_metrics.rmse
            )
            if increase is not None and increase > 0.15:
                row.flagged = True
                row.flag_reason = f"val RMSE {increase:.1%} above primary"
            temporal.append(row)
            self._collect_coefs(fit, coef_kpr, coef_ndpr, alphas, role_gaps)

        rolling = self._rolling_validation(primary_fit, coef_kpr, coef_ndpr, alphas, role_gaps)
        holdouts = self._event_holdouts(primary_fit, coef_kpr, coef_ndpr, alphas, role_gaps)
        scored = [item for item in holdouts if item.holdout_metrics.rmse is not None]
        best_event = min(scored, key=lambda item: item.holdout_metrics.rmse or 0.0, default=None)
        worst_event = max(scored, key=lambda item: item.holdout_metrics.rmse or 0.0, default=None)
        for item in holdouts:
            if (
                primary.validation_metrics.rmse is not None
                and item.holdout_metrics.rmse is not None
                and item.holdout_metrics.rmse
                > primary.validation_metrics.rmse * LATER_EVENT_RMSE_RATIO_LIMIT
            ):
                item.degraded = True

        tier_results = self._tier_results(coef_kpr, coef_ndpr, alphas, role_gaps)
        tier_status = _tier_status(tier_results)
        region_results = self._region_results(primary_fit)
        role_results, primary_role_gap = self._role_results(primary_fit)
        bootstrap = self._bootstrap(primary_fit)
        ranking, player_uncertainty, unstable = self._ranking(primary_fit)
        sample_size = self._sample_size(primary_fit)
        target = self._target_sensitivity(primary_fit)
        context_rows = self._context_sensitivity(primary_ids)
        redundancy = self._redundancy(primary_fit)
        aggregation = self._aggregation_sanity(primary_fit)
        baselines = self._baselines(primary_fit, preserved)
        wins = _count_event_wins(holdouts)
        leakage = self._leakage_audit(primary_fit)
        later_rmses = [rmse for item in holdouts if (rmse := item.holdout_metrics.rmse) is not None]
        t1 = next((item for item in tier_results if item.name == "T1_only"), None)
        t2 = next((item for item in tier_results if item.name == "T2_only"), None)
        ranking_500 = next(
            (
                item.spearman
                for item in ranking
                if item.comparison == "sample_size" and item.round_threshold == 500
            ),
            None,
        )
        failure = audit_failure_conditions(
            kpr_values=coef_kpr,
            ndpr_values=coef_ndpr,
            primary_val_rmse=primary.validation_metrics.rmse,
            later_event_rmses=later_rmses,
            t1_rmse=t1.evaluation_metrics.rmse if t1 is not None else None,
            t2_rmse=t2.evaluation_metrics.rmse if t2 is not None else None,
            t1_kpr_sign=t1.coefficient_signs.get(KPR_FEATURE, "missing") if t1 else "missing",
            t2_kpr_sign=t2.coefficient_signs.get(KPR_FEATURE, "missing") if t2 else "missing",
            t1_ndpr_sign=t1.coefficient_signs.get(NEGATIVE_DPR_FEATURE, "missing")
            if t1
            else "missing",
            t2_ndpr_sign=t2.coefficient_signs.get(NEGATIVE_DPR_FEATURE, "missing")
            if t2
            else "missing",
            role_gaps=role_gaps,
            bootstrap_kpr_low=bootstrap.kpr_interval_2_5,
            bootstrap_ndpr_low=bootstrap.negative_dpr_interval_2_5,
            ranking_spearman_500=ranking_500,
            cir_event_wins=wins[0],
            kd_event_wins=wins[1],
            acs_event_wins=wins[2],
            vlr_event_wins=wins[3],
            baseline_cir_better=_cir_beats_baselines(baselines),
        )
        if unstable:
            failure.warnings.append("Unstable high-sample players: " + ", ".join(unstable[:8]))
        sample_threshold = recommend_sample_threshold(
            [
                (row.round_threshold, row.eligible_players, row.spearman_vs_full)
                for row in sample_size
            ]
        )
        readiness = decide_readiness(
            failure_audit=failure,
            persisted=False,
            snapshots_exist=False,
            ranking_policy_defined=False,
            reliability_policy_defined=False,
            api_contract_ready=False,
        )
        reasons = [
            "Frozen candidate is kpr_residual + negative_dpr_residual under Context v2.",
            f"Primary chronological val RMSE={primary.validation_metrics.rmse}.",
            f"Tier generalization: {tier_status}.",
            f"Readiness={readiness}; CIR v0.2 was not persisted.",
            "Frontend is unchanged. CIR / v0.1-real-2026 was not overwritten.",
        ]
        reasons.extend(failure.failures)
        reasons.extend(failure.warnings)
        recommendation = build_recommendation(
            readiness=readiness,
            sample_threshold=sample_threshold,
            reasons=reasons,
        )
        self._assert_v01_real_unchanged(preserved)
        return CIRFinalValidationReport(
            frozen_features=list(self._features),
            context_configuration=self._spec.configuration(),
            shrinkage_k=self._shrinkage_k,
            primary=primary,
            temporal_splits=sorted(temporal, key=lambda item: item.train_fraction),
            rolling=rolling,
            event_holdouts=holdouts,
            best_generalized_event=best_event.event_name if best_event else None,
            worst_generalized_event=worst_event.event_name if worst_event else None,
            tier_results=tier_results,
            tier_generalization=tier_status,
            region_results=region_results,
            role_results=role_results,
            role_median_gap=primary_role_gap,
            coefficient_stability=coef_stability(coef_kpr, coef_ndpr, alphas),
            bootstrap=bootstrap,
            ranking_stability=ranking,
            player_uncertainty=player_uncertainty,
            sample_size=sample_size,
            target_sensitivity=target,
            context_sensitivity=context_rows,
            combat_redundancy=redundancy,
            aggregation_sanity=aggregation,
            baselines=baselines,
            events_won_by_cir=wins[0],
            events_won_by_kd=wins[1],
            events_won_by_acs=wins[2],
            events_won_by_vlr=wins[3],
            leakage_audit=leakage,
            failure_audit=failure,
            recommendation=recommendation,
            preserved_metric_version=CIR_REAL_EXPERIMENT_VERSION,
        )

    def _fit(
        self,
        *,
        train_fraction: float = PRIMARY_TRAIN_FRACTION,
        validation_fraction: float = PRIMARY_VALIDATION_FRACTION,
        split_ids_arg: tuple[set[UUID], set[UUID], set[UUID]] | None = None,
        eligible_map_ids: set[UUID] | None = None,
        context_mode: str | None = None,
        feature_names: tuple[str, ...] | None = None,
    ) -> _FoldOutcome | None:
        trainer = CIRTrainingService(
            self._session,
            require_complete_maps=self._require_complete_maps,
            persist=False,
            rebuild_ratings=False,
            context_mode=context_mode or self._spec.mode,
            context_spec=self._spec,
            shrinkage_k=self._shrinkage_k,
            feature_names=feature_names or self._features,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
            split_ids=split_ids_arg,
            eligible_map_ids=eligible_map_ids,
            team_rating_service=self._team_rating_service,
        )
        try:
            result, bundle = trainer.fit_cir_v01()
        except (ValueError, np.linalg.LinAlgError):
            return None
        coefficients = CIRModelCoefficients(
            intercept=result.intercept,
            coefficients=result.coefficients,
        )
        scores = player_scores(bundle, coefficients, bundle.feature_names, self._shrinkage_k)
        return _FoldOutcome(
            bundle=bundle,
            coefficients=coefficients,
            ridge_alpha=result.ridge_alpha,
            val_metrics=metrics_for_split(bundle, "validation", coefficients, bundle.feature_names),
            test_metrics=metrics_for_split(bundle, "test", coefficients, bundle.feature_names),
            role_gap=gap_from_scores(scores),
            player_scores=scores,
        )

    def _bundle(self, fit: _FoldOutcome) -> CIREvaluationBundle:
        return fit.bundle

    def _temporal_from_fit(
        self,
        name: str,
        fit: _FoldOutcome,
        *,
        train_fraction: float,
        validation_fraction: float,
    ) -> TemporalSplitResult:
        bundle = self._bundle(fit)
        periods = split_periods(bundle)
        return TemporalSplitResult(
            name=name,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
            test_fraction=max(0.0, 1.0 - train_fraction - validation_fraction),
            train_period_start=periods["train"][0],
            train_period_end=periods["train"][1],
            validation_period_start=periods["validation"][0],
            validation_period_end=periods["validation"][1],
            test_period_start=periods["test"][0],
            test_period_end=periods["test"][1],
            n_train_maps=map_count(bundle, "train"),
            n_val_maps=map_count(bundle, "validation"),
            n_test_maps=map_count(bundle, "test"),
            validation_metrics=fit.val_metrics,
            test_metrics=fit.test_metrics,
            kpr_coefficient=fit.coefficients.coefficients.get(KPR_FEATURE),
            negative_dpr_coefficient=fit.coefficients.coefficients.get(NEGATIVE_DPR_FEATURE),
            ridge_alpha=fit.ridge_alpha,
            role_median_gap=fit.role_gap,
        )

    def _rolling_validation(
        self,
        primary: _FoldOutcome,
        coef_kpr: list[float],
        coef_ndpr: list[float],
        alphas: list[float],
        role_gaps: list[float],
    ) -> RollingValidationSummary:
        bundle = self._bundle(primary)
        events = ordered_events(bundle)
        by_event = maps_by_event(bundle)
        folds: list[RollingFoldResult] = []
        rmses: list[float] = []
        maes: list[float] = []
        r2s: list[float] = []
        rhos: list[float] = []
        min_train_events = 2 if len(events) < 4 else 3
        for index in range(min_train_events, len(events)):
            train_events = events[:index]
            val_event = events[index]
            train_maps: list[UUID] = []
            for event in train_events:
                train_maps.extend(by_event[event[0]])
            nested_train, nested_val = chronological_two_way(
                order_maps(bundle, train_maps), NESTED_TRAIN_FRACTION
            )
            eval_maps = set(by_event[val_event[0]])
            fit = self._fit(split_ids_arg=(nested_train, nested_val, eval_maps))
            if fit is None:
                continue
            folds.append(
                RollingFoldResult(
                    train_events=[item[1] for item in train_events],
                    validation_event=val_event[1],
                    n_train_maps=len(nested_train),
                    n_val_maps=len(eval_maps),
                    validation_metrics=fit.test_metrics,
                    kpr_coefficient=fit.coefficients.coefficients.get(KPR_FEATURE),
                    negative_dpr_coefficient=fit.coefficients.coefficients.get(
                        NEGATIVE_DPR_FEATURE
                    ),
                    ridge_alpha=fit.ridge_alpha,
                    role_median_gap=fit.role_gap,
                )
            )
            self._collect_coefs(fit, coef_kpr, coef_ndpr, alphas, role_gaps)
            if fit.test_metrics.rmse is not None:
                rmses.append(fit.test_metrics.rmse)
            if fit.test_metrics.mae is not None:
                maes.append(fit.test_metrics.mae)
            if fit.test_metrics.r2 is not None:
                r2s.append(fit.test_metrics.r2)
            if fit.test_metrics.spearman is not None:
                rhos.append(fit.test_metrics.spearman)
        return RollingValidationSummary(
            folds=folds,
            rmse=numeric_summary(rmses),
            mae=numeric_summary(maes),
            r2=numeric_summary(r2s),
            spearman=numeric_summary(rhos),
        )

    def _event_holdouts(
        self,
        primary: _FoldOutcome,
        coef_kpr: list[float],
        coef_ndpr: list[float],
        alphas: list[float],
        role_gaps: list[float],
    ) -> list[EventHoldoutResult]:
        bundle = self._bundle(primary)
        events = ordered_events(bundle)
        by_event = maps_by_event(bundle)
        unique_maps = list(dict.fromkeys(row.stats.match_map_id for row in bundle.prepared_maps))
        results: list[EventHoldoutResult] = []
        for event_id, name, vlr_id, tier, region in events:
            holdout = set(by_event[event_id])
            others = [map_id for map_id in order_maps(bundle, unique_maps) if map_id not in holdout]
            if len(others) < MIN_TRAIN_TEAM_MAPS:
                continue
            train_ids, val_ids = chronological_two_way(others, NESTED_TRAIN_FRACTION)
            fit = self._fit(split_ids_arg=(train_ids, val_ids, holdout))
            if fit is None:
                continue
            results.append(
                EventHoldoutResult(
                    event_id=str(event_id),
                    event_name=name,
                    vlr_event_id=vlr_id,
                    tier=tier,
                    region=region,
                    n_train_maps=len(train_ids),
                    n_holdout_maps=len(holdout),
                    holdout_metrics=fit.test_metrics,
                    kpr_coefficient=fit.coefficients.coefficients.get(KPR_FEATURE),
                    negative_dpr_coefficient=fit.coefficients.coefficients.get(
                        NEGATIVE_DPR_FEATURE
                    ),
                    ridge_alpha=fit.ridge_alpha,
                    role_median_gap=fit.role_gap,
                    best_baseline=_best_holdout_baseline(fit),
                )
            )
            self._collect_coefs(fit, coef_kpr, coef_ndpr, alphas, role_gaps)
        return results

    def _tier_results(
        self,
        coef_kpr: list[float],
        coef_ndpr: list[float],
        alphas: list[float],
        role_gaps: list[float],
    ) -> list[TierResult]:
        rows: list[TierResult] = []
        map_tiers = self._map_tiers()
        t1_maps = {map_id for map_id, tier in map_tiers.items() if tier == "T1"}
        t2_maps = {map_id for map_id, tier in map_tiers.items() if tier == "T2"}
        for name, eligible in (("T1_only", t1_maps), ("T2_only", t2_maps)):
            if len(eligible) < MIN_TRAIN_TEAM_MAPS:
                continue
            fit = self._fit(eligible_map_ids=eligible)
            if fit is None:
                continue
            rows.append(self._tier_row(name, fit, eval_split="validation"))
            self._collect_coefs(fit, coef_kpr, coef_ndpr, alphas, role_gaps)
        if t1_maps and t2_maps:
            train_t1, val_t1 = chronological_two_way(
                self._ordered_eligible(t1_maps), NESTED_TRAIN_FRACTION
            )
            fit = self._fit(split_ids_arg=(train_t1, val_t1, t2_maps))
            if fit is not None:
                rows.append(self._tier_row("train_T1_eval_T2", fit, eval_split="test"))
                self._collect_coefs(fit, coef_kpr, coef_ndpr, alphas, role_gaps)
            train_t2, val_t2 = chronological_two_way(
                self._ordered_eligible(t2_maps), NESTED_TRAIN_FRACTION
            )
            fit = self._fit(split_ids_arg=(train_t2, val_t2, t1_maps))
            if fit is not None:
                rows.append(self._tier_row("train_T2_eval_T1", fit, eval_split="test"))
                self._collect_coefs(fit, coef_kpr, coef_ndpr, alphas, role_gaps)
        return rows

    def _tier_row(self, name: str, fit: _FoldOutcome, *, eval_split: str) -> TierResult:
        bundle = self._bundle(fit)
        metrics = fit.val_metrics if eval_split == "validation" else fit.test_metrics
        kpr = fit.coefficients.coefficients.get(KPR_FEATURE)
        ndpr = fit.coefficients.coefficients.get(NEGATIVE_DPR_FEATURE)
        return TierResult(
            name=name,
            n_train_maps=map_count(bundle, "train"),
            n_eval_maps=map_count(bundle, eval_split),
            evaluation_metrics=metrics,
            kpr_coefficient=kpr,
            negative_dpr_coefficient=ndpr,
            coefficient_signs={
                KPR_FEATURE: coefficient_sign(kpr),
                NEGATIVE_DPR_FEATURE: coefficient_sign(ndpr),
            },
            ridge_alpha=fit.ridge_alpha,
            role_median_gap=fit.role_gap,
        )

    def _region_results(self, fit: _FoldOutcome) -> list[RegionResult]:
        bundle = self._bundle(fit)
        grouped: dict[str, list[_TeamMapPrepared]] = defaultdict(list)
        regions = region_by_map(bundle)
        for team_map in bundle.team_maps:
            grouped[regions.get(team_map.match_map_id, "Unknown")].append(team_map)
        results: list[RegionResult] = []
        for region in (*REGION_LABELS, "Unknown"):
            maps = grouped.get(region, [])
            players = [score for score in fit.player_scores.values() if score.region == region]
            if not maps and not players:
                continue
            cir_values = [score.cir for score in players]
            summary = distribution_summary(cir_values)
            role_values: dict[str, list[tuple[float, int]]] = defaultdict(list)
            for score in players:
                role_values[score.role].append((score.cir, score.rounds))
            results.append(
                RegionResult(
                    region=region,
                    maps=len({item.match_map_id for item in maps}),
                    players=len(players),
                    rounds=sum(score.rounds for score in players),
                    evaluation_metrics=predict_team_maps(
                        maps, fit.coefficients, bundle.feature_names
                    ),
                    mean_cir=summary["mean"],
                    median_cir=summary["median"],
                    role_median_gap=role_bias_metrics(role_values).max_role_median_gap,
                    small_sample=len(maps) < SMALL_REGION_MAPS,
                )
            )
        return results

    def _role_results(self, fit: _FoldOutcome) -> tuple[list[RoleResult], float | None]:
        bundle = self._bundle(fit)
        by_role: dict[str, list[PlayerScore]] = defaultdict(list)
        map_counts: dict[str, set[UUID]] = defaultdict(set)
        for row in bundle.prepared_maps:
            role = row.stats.agent.role if row.stats.agent is not None else "Unknown"
            map_counts[role].add(row.stats.match_map_id)
        for score in fit.player_scores.values():
            by_role[score.role].append(score)
        results: list[RoleResult] = []
        role_values: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for role in CIR_ROLES:
            players = by_role.get(role, [])
            values = [item.cir for item in players]
            summary = distribution_summary(values)
            results.append(
                RoleResult(
                    role=role,
                    players=len(players),
                    maps=len(map_counts.get(role, set())),
                    rounds=sum(item.rounds for item in players),
                    mean_cir=summary["mean"],
                    median_cir=summary["median"],
                    std=summary["std"],
                    p10=summary["p10"],
                    p25=summary["p25"],
                    p75=summary["p75"],
                    p90=summary["p90"],
                    outcome_correlation=role_outcome_corr(bundle, fit.coefficients, role),
                )
            )
            role_values[role] = [(item.cir, item.rounds) for item in players]
        return results, role_bias_metrics(role_values).max_role_median_gap

    def _bootstrap(self, fit: _FoldOutcome) -> BootstrapResult:
        bundle = self._bundle(fit)
        train_maps = [row for row in bundle.team_maps if row.split == "train"]
        val_maps = [row for row in bundle.team_maps if row.split == "validation"]
        usable = match_ids_for_maps(bundle, {row.match_map_id for row in train_maps})
        maps_by_match: dict[UUID, list[_TeamMapPrepared]] = defaultdict(list)
        for row in train_maps:
            match_id = match_id_for(bundle, row.match_map_id)
            if match_id is not None:
                maps_by_match[match_id].append(row)
        usable = [match_id for match_id in usable if match_id in maps_by_match]
        if len(usable) < 2 or not val_maps:
            return BootstrapResult(iterations=0, block="match")
        rng = np.random.default_rng(self._bootstrap_seed)
        kpr_vals: list[float] = []
        ndpr_vals: list[float] = []
        rmses: list[float] = []
        r2s: list[float] = []
        rhos: list[float] = []
        val_design, val_targets = _design_matrix(val_maps, feature_names=self._features)
        for _ in range(self._bootstrap_iterations):
            sampled = resample_match_ids(usable, rng)
            boot_maps = [row for match_id in sampled for row in maps_by_match[match_id]]
            if len(boot_maps) < MIN_TRAIN_TEAM_MAPS:
                continue
            train_design, train_targets = _design_matrix(boot_maps, feature_names=self._features)
            try:
                intercept, weights = fit_ridge(train_design, train_targets, fit.ridge_alpha)
            except np.linalg.LinAlgError:
                continue
            coefs = _coefficients_for_features(self._features, weights)
            kpr_vals.append(float(coefs.get(KPR_FEATURE, 0.0)))
            ndpr_vals.append(float(coefs.get(NEGATIVE_DPR_FEATURE, 0.0)))
            metrics = split_metrics_from_arrays(
                val_targets, predict_ridge(val_design, intercept, weights)
            )
            if metrics.rmse is not None:
                rmses.append(metrics.rmse)
            if metrics.r2 is not None:
                r2s.append(metrics.r2)
            if metrics.spearman is not None:
                rhos.append(metrics.spearman)
        return BootstrapResult(
            iterations=len(kpr_vals),
            block="match",
            kpr=coefficient_summary(kpr_vals),
            negative_dpr=coefficient_summary(ndpr_vals),
            rmse=numeric_summary(rmses),
            r2=numeric_summary(r2s),
            spearman=numeric_summary(rhos),
            kpr_interval_2_5=percentile(kpr_vals, 2.5) if kpr_vals else None,
            kpr_interval_97_5=percentile(kpr_vals, 97.5) if kpr_vals else None,
            negative_dpr_interval_2_5=percentile(ndpr_vals, 2.5) if ndpr_vals else None,
            negative_dpr_interval_97_5=percentile(ndpr_vals, 97.5) if ndpr_vals else None,
        )

    def _ranking(
        self, primary: _FoldOutcome
    ) -> tuple[list[RankingStabilityResult], list[PlayerScoreUncertainty], list[str]]:
        bundle = self._bundle(primary)
        primary_scores = {str(score.player_id): score for score in primary.player_scores.values()}
        rows: list[RankingStabilityResult] = []
        for threshold in RANKING_ROUND_THRESHOLDS:
            eligible = [
                player_id
                for player_id, score in primary_scores.items()
                if score.rounds >= threshold
            ]
            partial = partial_period_scores(
                bundle,
                primary.coefficients,
                bundle.feature_names,
                threshold,
                self._shrinkage_k,
                bundle.reference_mean,
            )
            if len(eligible) < 2:
                rows.append(
                    RankingStabilityResult(
                        comparison="sample_size",
                        round_threshold=threshold,
                        eligible_players=len(eligible),
                    )
                )
                continue
            full_order = ordered_player_ids(
                {player_id: primary_scores[player_id].cir for player_id in eligible}
            )
            partial_order = ordered_player_ids(
                {
                    player_id: partial[UUID(player_id)]
                    for player_id in eligible
                    if UUID(player_id) in partial
                }
            )
            ref_ranks = rank_map(full_order)
            cand_ranks = rank_map(partial_order)
            spearman, kendall = ranking_correlations(ref_ranks, cand_ranks)
            mean_move, median_move = rank_movement(ref_ranks, cand_ranks)
            rows.append(
                RankingStabilityResult(
                    comparison="sample_size",
                    round_threshold=threshold,
                    eligible_players=len(eligible),
                    spearman=spearman,
                    kendall_tau=kendall,
                    mean_absolute_rank_movement=mean_move,
                    median_absolute_rank_movement=median_move,
                    top_10_retention=top_n_retention(full_order, partial_order, 10),
                    top_25_retention=top_n_retention(full_order, partial_order, 25),
                    top_50_retention=top_n_retention(full_order, partial_order, 50),
                )
            )
        draws = bootstrap_player_draws(
            bundle,
            bundle.feature_names,
            primary.ridge_alpha,
            self._shrinkage_k,
            iterations=min(self._bootstrap_iterations, 80),
            seed=self._bootstrap_seed,
        )
        uncertainty: list[PlayerScoreUncertainty] = []
        unstable: list[str] = []
        for score in sorted(primary.player_scores.values(), key=lambda item: -item.rounds):
            if score.rounds < 100:
                continue
            samples = draws.get(score.player_id, [])
            if len(samples) < 5:
                continue
            cir_values = [item[0] for item in samples]
            rank_values = [item[1] for item in samples]
            uncertainty.append(
                PlayerScoreUncertainty(
                    player_id=str(score.player_id),
                    handle=score.handle,
                    rounds=score.rounds,
                    cir_median=percentile(cir_values, 50),
                    cir_p05=percentile(cir_values, 5),
                    cir_p95=percentile(cir_values, 95),
                    rank_median=percentile(rank_values, 50),
                    rank_p05=percentile(rank_values, 5),
                    rank_p95=percentile(rank_values, 95),
                )
            )
            span = (percentile(rank_values, 95) or 0.0) - (percentile(rank_values, 5) or 0.0)
            if score.rounds >= 250 and span > 40:
                unstable.append(score.handle or str(score.player_id))
        return rows, uncertainty[:80], unstable

    def _sample_size(self, fit: _FoldOutcome) -> list[SampleSizeResult]:
        bundle = self._bundle(fit)
        full = {str(score.player_id): score for score in fit.player_scores.values()}
        rows: list[SampleSizeResult] = []
        for threshold in SAMPLE_SIZE_THRESHOLDS:
            partial = partial_period_scores(
                bundle,
                fit.coefficients,
                bundle.feature_names,
                threshold,
                self._shrinkage_k,
                bundle.reference_mean,
            )
            eligible = [
                player_id
                for player_id, score in full.items()
                if score.rounds >= threshold and UUID(player_id) in partial
            ]
            if len(eligible) < 2:
                rows.append(
                    SampleSizeResult(round_threshold=threshold, eligible_players=len(eligible))
                )
                continue
            full_vals = np.array([full[player_id].cir for player_id in eligible], dtype=np.float64)
            part_vals = np.array(
                [partial[UUID(player_id)] for player_id in eligible], dtype=np.float64
            )
            abs_diff = np.abs(full_vals - part_vals)
            full_order = ordered_player_ids(
                {player_id: full[player_id].cir for player_id in eligible}
            )
            part_order = ordered_player_ids(
                {player_id: partial[UUID(player_id)] for player_id in eligible}
            )
            mean_move, _median = rank_movement(rank_map(full_order), rank_map(part_order))
            rows.append(
                SampleSizeResult(
                    round_threshold=threshold,
                    eligible_players=len(eligible),
                    spearman_vs_full=spearman_correlation(full_vals, part_vals),
                    mean_absolute_cir_difference=float(np.mean(abs_diff)),
                    median_absolute_cir_difference=float(np.median(abs_diff)),
                    mean_absolute_rank_movement=mean_move,
                )
            )
        return rows

    def _target_sensitivity(self, fit: _FoldOutcome) -> TargetSensitivityResult:
        bundle = self._bundle(fit)
        raw_maps = team_maps_with_raw_target(bundle)
        elo_model, _alpha = fit_ridge_on_maps(bundle.team_maps, self._features)
        raw_model, _raw_alpha = fit_ridge_on_maps(raw_maps, self._features)
        elo_scores = player_scores(bundle, elo_model, self._features, self._shrinkage_k)
        original = bundle.team_maps
        bundle.team_maps = raw_maps
        raw_scores = player_scores(bundle, raw_model, self._features, self._shrinkage_k)
        bundle.team_maps = original
        spearman = score_spearman(elo_scores, raw_scores)
        flagged = spearman is not None and spearman < 0.8
        return TargetSensitivityResult(
            elo_residual=metrics_for_split(bundle, "validation", elo_model, self._features),
            raw_round_diff=predict_team_maps(
                [row for row in raw_maps if row.split == "validation"],
                raw_model,
                self._features,
            ),
            ranking_spearman=spearman,
            kpr_coefficient_elo=elo_model.coefficients.get(KPR_FEATURE),
            kpr_coefficient_raw=raw_model.coefficients.get(KPR_FEATURE),
            role_gap_elo=gap_from_scores(elo_scores),
            role_gap_raw=gap_from_scores(raw_scores),
            flagged=flagged,
            conclusion=(
                "Rankings moved substantially when replacing Elo OutcomeResidual "
                "with raw round differential."
                if flagged
                else "CIR conclusions are reasonably stable to the Elo vs raw round-diff target."
            ),
        )

    def _context_sensitivity(
        self,
        primary_ids: tuple[set[UUID], set[UUID], set[UUID]],
    ) -> list[ContextSensitivityResult]:
        rows: list[ContextSensitivityResult] = []
        for name, mode in (
            ("context_v2", CONTEXT_MODE_V2),
            ("context_v1", CONTEXT_MODE_V1),
            ("no_context", CONTEXT_MODE_NONE),
        ):
            fit = self._fit(split_ids_arg=primary_ids, context_mode=mode)
            if fit is None:
                continue
            rows.append(
                ContextSensitivityResult(
                    name=name,
                    validation_metrics=fit.val_metrics,
                    test_metrics=fit.test_metrics,
                    role_median_gap=fit.role_gap,
                    kpr_coefficient=fit.coefficients.coefficients.get(KPR_FEATURE),
                    negative_dpr_coefficient=fit.coefficients.coefficients.get(
                        NEGATIVE_DPR_FEATURE
                    ),
                )
            )
        return rows

    def _redundancy(self, fit: _FoldOutcome) -> CombatRedundancyResult:
        bundle = self._bundle(fit)
        kpr_only = fit_feature_subset(bundle, (KPR_FEATURE,))
        dpr_only = fit_feature_subset(bundle, (NEGATIVE_DPR_FEATURE,))
        both = fit_feature_subset(bundle, self._features)
        kpr_scores = player_scores(bundle, kpr_only[0], (KPR_FEATURE,), self._shrinkage_k)
        dpr_scores = player_scores(bundle, dpr_only[0], (NEGATIVE_DPR_FEATURE,), self._shrinkage_k)
        both_scores = player_scores(bundle, both[0], self._features, self._shrinkage_k)
        singles = [item for item in (kpr_only[1].rmse, dpr_only[1].rmse) if item is not None]
        incremental = second_feature_adds_value(both[1].rmse, min(singles) if singles else None)
        return CombatRedundancyResult(
            kpr_only=kpr_only[1],
            negative_dpr_only=dpr_only[1],
            both=both[1],
            kpr_only_test=kpr_only[2],
            negative_dpr_only_test=dpr_only[2],
            both_test=both[2],
            ranking_correlation_kpr_vs_both=score_spearman(kpr_scores, both_scores),
            ranking_correlation_dpr_vs_both=score_spearman(dpr_scores, both_scores),
            role_gap_kpr_only=gap_from_scores(kpr_scores),
            role_gap_dpr_only=gap_from_scores(dpr_scores),
            role_gap_both=gap_from_scores(both_scores),
            incremental_value=incremental,
            conclusion=(
                "Both combat features add incremental validation value."
                if incremental
                else "ONE_FEATURE_CANDIDATE: the second combat feature does not clear the 1% RMSE "
                "bar. Keep the frozen two-feature candidate for this phase."
            ),
        )

    def _aggregation_sanity(self, fit: _FoldOutcome) -> AggregationSanityResult:
        bundle = self._bundle(fit)
        mean_maps = team_maps_mean_aggregated(bundle)
        sum_model, _ = fit_ridge_on_maps(bundle.team_maps, self._features)
        mean_model, _ = fit_ridge_on_maps(mean_maps, self._features)
        sum_scores = player_scores(bundle, sum_model, self._features, self._shrinkage_k)
        mean_scores = player_scores(bundle, mean_model, self._features, self._shrinkage_k)
        spearman = score_spearman(sum_scores, mean_scores)
        robust = spearman is not None and spearman >= 0.95
        return AggregationSanityResult(
            sum_validation=metrics_for_split(bundle, "validation", sum_model, self._features),
            mean_validation=predict_team_maps(
                [row for row in mean_maps if row.split == "validation"],
                mean_model,
                self._features,
            ),
            ranking_spearman=spearman,
            conclusion=(
                "Player rankings are robust to sum vs mean team aggregation."
                if robust
                else "Aggregation convention moves rankings; keep production sum aggregation."
            ),
        )

    def _baselines(
        self,
        fit: _FoldOutcome,
        preserved: dict[str, object] | None,
    ) -> list[BaselineExactComparison]:
        bundle = self._bundle(fit)
        rows = [
            BaselineExactComparison(
                name="combat_only_cir_candidate",
                validation_metrics=fit.val_metrics,
                test_metrics=fit.test_metrics,
                role_median_gap=fit.role_gap,
                source="live frozen candidate on identical maps/split",
            )
        ]
        v01_fit = self._fit(split_ids_arg=split_ids(bundle), feature_names=CIR_V01_FEATURE_NAMES)
        if v01_fit is not None:
            rows.append(
                BaselineExactComparison(
                    name="CIR_v0.1_feature_set_refit",
                    validation_metrics=v01_fit.val_metrics,
                    test_metrics=v01_fit.test_metrics,
                    role_median_gap=v01_fit.role_gap,
                    source="same maps/split/context; original CIR v0.1 feature list refit",
                )
            )
        for name, fn in (
            ("team_average_kd", _kd),
            ("team_average_acs", _acs),
            ("team_average_vlr_rating", _vlr),
        ):
            val, test = _univariate_baseline(fit, fn)
            rows.append(
                BaselineExactComparison(
                    name=name,
                    validation_metrics=val,
                    test_metrics=test,
                    source="univariate on identical eligible maps and split",
                )
            )
        if preserved is not None:
            stored = preserved.get("regularization")
            if isinstance(stored, dict):
                metrics = stored.get("validation_metrics")
                if isinstance(metrics, dict):
                    rows.append(
                        BaselineExactComparison(
                            name="CIR_v0.1-real-2026",
                            validation_metrics=SplitMetrics(
                                rmse=as_float(metrics.get("validation_rmse")),
                                r2=as_float(metrics.get("validation_r2")),
                            ),
                            test_metrics=SplitMetrics(
                                rmse=as_float(metrics.get("test_rmse")),
                                r2=as_float(metrics.get("test_r2")),
                            ),
                            source="stored MetricVersion (not retrained)",
                        )
                    )
        return rows

    def _leakage_audit(self, fit: _FoldOutcome) -> list[LeakageAuditItem]:
        periods = split_periods(self._bundle(fit))
        return [
            LeakageAuditItem(
                name="team_elo",
                fit_scope="chronological pre-match snapshots",
                earliest_date=periods["train"][0],
                latest_date=periods["train"][1],
                notes="Pre-match Elo only; no future matches.",
            ),
            LeakageAuditItem(
                name="context_v2_expectations",
                fit_scope="train maps",
                earliest_date=periods["train"][0],
                latest_date=periods["train"][1],
                notes="Validation/test use frozen train registry.",
            ),
            LeakageAuditItem(
                name="standardization",
                fit_scope="train player-maps",
                earliest_date=periods["train"][0],
                latest_date=periods["train"][1],
                notes="mu/sigma frozen from train.",
            ),
            LeakageAuditItem(
                name="ridge_alpha_and_coefficients",
                fit_scope="train design; alpha selected on validation",
                earliest_date=periods["train"][0],
                latest_date=periods["validation"][1],
                notes="Test never used for alpha or coefficients.",
            ),
            LeakageAuditItem(
                name="reference_percentile",
                fit_scope="train player shrunk CIR",
                earliest_date=periods["train"][0],
                latest_date=periods["train"][1],
                notes="Empirical CDF reference is train-only.",
            ),
            LeakageAuditItem(
                name="bootstrap_folds",
                fit_scope="resampled train matches; frozen transforms",
                earliest_date=periods["train"][0],
                latest_date=periods["train"][1],
                notes="Bootstrap does not include validation/test maps.",
            ),
            LeakageAuditItem(
                name="temporal_folds",
                fit_scope="chronological train window only",
                earliest_date=periods["train"][0],
                latest_date=periods["train"][1],
                notes="Rolling/LOEO nested val is taken from the train-side events.",
            ),
        ]

    def _collect_coefs(
        self,
        fit: _FoldOutcome,
        kpr: list[float],
        ndpr: list[float],
        alphas: list[float],
        gaps: list[float],
    ) -> None:
        kpr_value = fit.coefficients.coefficients.get(KPR_FEATURE)
        ndpr_value = fit.coefficients.coefficients.get(NEGATIVE_DPR_FEATURE)
        if kpr_value is not None:
            kpr.append(float(kpr_value))
        if ndpr_value is not None:
            ndpr.append(float(ndpr_value))
        alphas.append(float(fit.ridge_alpha))
        if fit.role_gap is not None:
            gaps.append(float(fit.role_gap))

    def _map_tiers(self) -> dict[UUID, str]:
        stats = (
            CIRTrainingService(
                self._session,
                require_complete_maps=self._require_complete_maps,
                persist=False,
                rebuild_ratings=False,
                team_rating_service=self._team_rating_service,
            )
            ._select_dataset()
            .stats
        )
        tiers: dict[UUID, str] = {}
        for row in stats:
            event = row.match_map.match.event
            tiers[row.match_map_id] = (event.tier or "Unknown") if event is not None else "Unknown"
        return tiers

    def _ordered_eligible(self, eligible: set[UUID]) -> list[UUID]:
        stats = (
            CIRTrainingService(
                self._session,
                require_complete_maps=self._require_complete_maps,
                persist=False,
                rebuild_ratings=False,
                eligible_map_ids=eligible,
                team_rating_service=self._team_rating_service,
            )
            ._select_dataset()
            .stats
        )
        return _chronological_map_ids(stats)

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
                f"{CIR_REAL_EXPERIMENT_VERSION} changed during final CIR robustness validation"
            )


def _univariate_baseline(
    fit: _FoldOutcome,
    metric_fn: Callable[[PlayerMapStats], float],
) -> tuple[SplitMetrics, SplitMetrics]:
    bundle = fit.bundle
    stats_by_map: dict[UUID, list[PlayerMapStats]] = defaultdict(list)
    for row in bundle.prepared_maps:
        stats_by_map[row.stats.match_map_id].append(row.stats)
    pairs: dict[str, list[tuple[float, float]]] = {"train": [], "validation": [], "test": []}
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
        left = sum(metric_fn(item) for item in team_a) / len(team_a)
        right = sum(metric_fn(item) for item in team_b) / len(team_b)
        pairs[team_map.split].append((left - right, team_map.outcome_residual))
    train = pairs["train"]
    if not train:
        return SplitMetrics(), SplitMetrics()
    x = np.array([item[0] for item in train], dtype=np.float64)
    y = np.array([item[1] for item in train], dtype=np.float64)
    if len(x) == 1 or np.allclose(x, x[0]):
        slope, intercept = 0.0, float(np.mean(y))
    else:
        fitted = np.polyfit(x, y, 1)
        slope, intercept = float(fitted[0]), float(fitted[1])

    def eval_split(name: str) -> SplitMetrics:
        rows = pairs[name]
        if not rows:
            return SplitMetrics()
        xs = np.array([item[0] for item in rows], dtype=np.float64)
        ys = np.array([item[1] for item in rows], dtype=np.float64)
        return split_metrics_from_arrays(ys, slope * xs + intercept)

    return eval_split("validation"), eval_split("test")


def _best_holdout_baseline(fit: _FoldOutcome) -> str:
    candidates: dict[str, float | None] = {"combat_only": fit.test_metrics.rmse}
    for name, fn in (("kd", _kd), ("acs", _acs), ("vlr", _vlr)):
        _val, test = _univariate_baseline(fit, fn)
        candidates[name] = test.rmse
    present = {name: rmse for name, rmse in candidates.items() if rmse is not None}
    if not present:
        return "combat_only"
    return min(present, key=lambda name: present[name] or 0.0)


def _count_event_wins(holdouts: list[EventHoldoutResult]) -> tuple[int, int, int, int]:
    cir = kd = acs = vlr = 0
    for item in holdouts:
        winner = item.best_baseline or "combat_only"
        if winner == "combat_only":
            cir += 1
        elif winner == "kd":
            kd += 1
        elif winner == "acs":
            acs += 1
        elif winner == "vlr":
            vlr += 1
    return cir, kd, acs, vlr


def _tier_status(rows: list[TierResult]) -> str:
    t1 = next((item for item in rows if item.name == "T1_only"), None)
    t2 = next((item for item in rows if item.name == "T2_only"), None)
    if t1 is None or t2 is None:
        return "TIER_GENERALIZATION_UNSTABLE"
    signs_ok = (
        t1.coefficient_signs.get(KPR_FEATURE) == "positive"
        and t2.coefficient_signs.get(KPR_FEATURE) == "positive"
        and t1.coefficient_signs.get(NEGATIVE_DPR_FEATURE) == "positive"
        and t2.coefficient_signs.get(NEGATIVE_DPR_FEATURE) == "positive"
    )
    return "TIER_GENERALIZATION_STABLE" if signs_ok else "TIER_GENERALIZATION_UNSTABLE"


def _cir_beats_baselines(rows: list[BaselineExactComparison]) -> bool:
    combat = next((item for item in rows if item.name == "combat_only_cir_candidate"), None)
    if combat is None or combat.validation_metrics.rmse is None:
        return False
    for name in ("team_average_kd", "team_average_acs", "team_average_vlr_rating"):
        other = next((item for item in rows if item.name == name), None)
        if other is None or other.validation_metrics.rmse is None:
            continue
        if combat.validation_metrics.rmse >= other.validation_metrics.rmse:
            return False
    return True


def _kd(stats: PlayerMapStats) -> float:
    return safe_ratio(stats.kills, stats.deaths) or 0.0


def _acs(stats: PlayerMapStats) -> float:
    return stats.acs or 0.0


def _vlr(stats: PlayerMapStats) -> float:
    return stats.vlr_rating or 0.0
