from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_combat_factor import (
    CombatCandidateSnapshot,
    combat_factor_readiness,
    competitive_rmse,
    interpretation,
    pc1_captures_shared_combat,
    pc2_adds_validation_value,
    recommended_spec,
    select_combat_parameterization,
)
from app.metrics.cir_combat_factor_config import (
    BOOTSTRAP_SEED,
    CANDIDATE_KINDS,
    CONSTRAINED_REGRESSION_FALLBACK,
    DEFAULT_BOOTSTRAP_ITERATIONS,
    EQUAL_WEIGHT,
    FROZEN_COMBAT_FEATURES,
    FROZEN_SHRINKAGE_K,
    KPR_FEATURE,
    LATER_EVENT_RMSE_RATIO_LIMIT,
    LOEO_KINDS,
    MIN_TRAIN_TEAM_MAPS,
    NEGATIVE_DPR_FEATURE,
    NESTED_TRAIN_FRACTION,
    NET_COMBAT_RATE,
    PCA_COMBAT_FACTOR,
    PRIMARY_TRAIN_FRACTION,
    PRIMARY_VALIDATION_FRACTION,
    RANKING_ROUND_THRESHOLDS,
    TEMPORAL_SPLIT_GRID,
    TWO_FEATURE,
    frozen_context_spec,
)
from app.metrics.cir_final_validation import (
    chronological_two_way,
    coefficient_sign,
    coefficient_summary,
    numeric_summary,
    ordered_player_ids,
    rank_map,
    rank_movement,
    ranking_correlations,
    top_n_retention,
)
from app.metrics.cir_final_validation_config import CIR_V02_RECOMMENDED_VERSION
from app.metrics.cir_v01 import CIR_METRIC_NAME
from app.metrics.cir_validation_metrics import percentile
from app.metrics.context_v2_config import CONTEXT_MODE_V2
from app.models import MetricVersion
from app.schemas.cir_combat_factor import (
    CombatBaselineRow,
    CombatBootstrapResult,
    CombatCoefficientStability,
    CombatEventHoldout,
    CombatFactorRecommendation,
    CombatFactorReport,
    CombatPlayerUncertainty,
    CombatRankingComparison,
    CombatRollingFold,
    CombatRollingSummary,
    CombatTemporalResult,
    CombatTierResult,
    PC2Diagnostic,
    PCALoadings,
)
from app.schemas.cir_final_validation import LeakageAuditItem
from app.schemas.context_v2 import SplitMetrics
from app.services.cir_combat_factor_support import (
    AppliedCombat,
    apply_parameterization,
    apply_pc1_pc2,
    bootstrap_kind,
    combat_coefficient,
    player_combat_means,
    profile_label,
    to_primary_row,
    train_kpr_ndpr_correlation,
    univariate_baselines,
)
from app.services.cir_final_validation_support import (
    as_float,
    bootstrap_player_draws,
    event_tier,
    map_count,
    maps_by_event,
    order_maps,
    ordered_events,
    partial_period_scores,
    split_periods,
)
from app.services.cir_training_service import (
    CIREvaluationBundle,
    CIRTrainingService,
    _chronological_map_ids,
)
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from app.services.team_rating_service import TeamRatingService


class CirCombatFactorExperimentService:
    """Compare combat parameterizations. Does not persist a CIR version."""

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
        self._team_rating_service = TeamRatingService(session)

    def run(self) -> CombatFactorReport:
        preserved = self._snapshot_v01_real()
        self._team_rating_service.rebuild_team_ratings()
        primary_bundle = self._fit_context()
        assert primary_bundle is not None
        applied = self._apply_all(primary_bundle)
        two = applied[TWO_FEATURE]
        reference_rmse = two.val_metrics.rmse
        candidates = [
            to_primary_row(
                applied[kind],
                competitive=competitive_rmse(applied[kind].val_metrics.rmse, reference_rmse),
                interpretation=interpretation(kind),
            )
            for kind in CANDIDATE_KINDS
        ]
        pca_applied = applied[PCA_COMBAT_FACTOR]
        pca_model = pca_applied.pca
        pca_row = PCALoadings()
        if pca_model is not None:
            pca_row = PCALoadings(
                kpr_loading_pc1=pca_model.kpr_loading_pc1,
                ndpr_loading_pc1=pca_model.ndpr_loading_pc1,
                kpr_loading_pc2=pca_model.kpr_loading_pc2,
                ndpr_loading_pc2=pca_model.ndpr_loading_pc2,
                explained_pc1=pca_model.explained_pc1,
                explained_pc2=pca_model.explained_pc2,
                oriented=pca_model.oriented,
                pc1_dominates=pc1_captures_shared_combat(pca_model.explained_pc1),
            )
        _pc1, pc1_pc2 = apply_pc1_pc2(primary_bundle, self._shrinkage_k)
        pc2_adds = pc2_adds_validation_value(pca_applied.val_metrics.rmse, pc1_pc2.val_metrics.rmse)
        pc2 = PC2Diagnostic(
            pc1_validation=pca_applied.val_metrics,
            pc1_pc2_validation=pc1_pc2.val_metrics,
            pc1_test=pca_applied.test_metrics,
            pc1_pc2_test=pc1_pc2.test_metrics,
            pc2_adds_value=pc2_adds,
            discard_pc2=not pc2_adds,
            note=(
                "PC2 adds at least 1% validation RMSE and is retained as a diagnostic only."
                if pc2_adds
                else "PC2 adds <1% validation RMSE; discard PC2. Combat space is one-dimensional."
            ),
        )
        coef_folds: dict[str, list[float]] = defaultdict(list)
        pca_kpr_folds: list[float] = []
        pca_ndpr_folds: list[float] = []
        self._collect_fold(applied, coef_folds, pca_kpr_folds, pca_ndpr_folds)
        temporal = self._temporal(primary_bundle, coef_folds, pca_kpr_folds, pca_ndpr_folds)
        rolling = self._rolling(primary_bundle, coef_folds, pca_kpr_folds, pca_ndpr_folds)
        holdouts, holdout_by_event = self._event_holdouts(
            primary_bundle, coef_folds, pca_kpr_folds, pca_ndpr_folds
        )
        tier_rows = self._tier(coef_folds, pca_kpr_folds, pca_ndpr_folds)
        bootstraps = {
            kind: bootstrap_kind(
                primary_bundle,
                kind,
                self._shrinkage_k,
                self._bootstrap_iterations,
                self._bootstrap_seed,
                applied[kind].ridge_alpha,
            )
            for kind in CANDIDATE_KINDS
        }
        bootstrap_rows = [self._bootstrap_row(kind, bootstraps[kind]) for kind in CANDIDATE_KINDS]
        ranking_rows = self._ranking(applied)
        uncertainty, sensitive = self._player_uncertainty(applied)
        baselines = self._baselines(primary_bundle, applied, preserved)
        leakage = self._leakage(primary_bundle)
        snapshots = self._snapshots(
            applied, bootstraps, ranking_rows, tier_rows, holdouts, baselines
        )
        selection, winning_kind, reasons = select_combat_parameterization(snapshots)
        event_wins, win_counts = self._event_wins(holdout_by_event, winning_kind)
        winner = next((item for item in snapshots if item.kind == winning_kind), None)
        readiness = combat_factor_readiness(
            selection=selection,
            winning_kind=winning_kind,
            snapshot=winner,
        )
        best: dict[str, str] = {}
        worst: dict[str, str] = {}
        for kind in LOEO_KINDS:
            rows = [item for item in holdouts if item.kind == kind and item.holdout_metrics.rmse]
            if not rows:
                continue
            best[kind] = min(rows, key=lambda item: item.holdout_metrics.rmse or 0).event_name
            worst[kind] = max(rows, key=lambda item: item.holdout_metrics.rmse or 0).event_name
        self._assert_v01_real_unchanged(preserved)
        return CombatFactorReport(
            frozen_context=self._spec.configuration(),
            shrinkage_k=self._shrinkage_k,
            candidates=candidates,
            pca=pca_row,
            pc2_diagnostic=pc2,
            kpr_ndpr_train_correlation=train_kpr_ndpr_correlation(primary_bundle),
            temporal=temporal,
            rolling=rolling,
            event_holdouts=holdouts,
            events_won_by_kind=event_wins,
            best_holdout=best,
            worst_holdout=worst,
            events_won_by_single_factor=win_counts["single"],
            events_won_by_two_feature=win_counts["two"],
            events_won_by_vlr=win_counts["vlr"],
            events_won_by_kd=win_counts["kd"],
            events_won_by_acs=win_counts["acs"],
            tier_results=tier_rows,
            coefficient_stability=self._coef_stability(coef_folds, pca_kpr_folds, pca_ndpr_folds),
            bootstrap=bootstrap_rows,
            ranking=ranking_rows,
            player_uncertainty=uncertainty,
            sensitive_profiles=sensitive,
            baselines=baselines,
            leakage_audit=leakage,
            recommendation=CombatFactorRecommendation(
                selection=selection,
                winning_kind=winning_kind,
                readiness=readiness,
                persist=False,
                metric_name=CIR_METRIC_NAME,
                version=CIR_V02_RECOMMENDED_VERSION,
                specification=recommended_spec(winning_kind),
                reasons=[
                    "Context v2, lambda=1, tau=500, k=50 are frozen.",
                    f"Train KPR vs -DPR correlation={train_kpr_ndpr_correlation(primary_bundle)}.",
                    f"Selection={selection}. Readiness={readiness}. CIR v0.2 was not persisted.",
                    *reasons,
                ],
                constrained_regression_fallback=CONSTRAINED_REGRESSION_FALLBACK,
            ),
            preserved_metric_version=CIR_REAL_EXPERIMENT_VERSION,
        )

    def _fit_context(
        self,
        *,
        train_fraction: float = PRIMARY_TRAIN_FRACTION,
        validation_fraction: float = PRIMARY_VALIDATION_FRACTION,
        split_ids_arg: tuple[set[UUID], set[UUID], set[UUID]] | None = None,
        eligible_map_ids: set[UUID] | None = None,
    ) -> CIREvaluationBundle | None:
        trainer = CIRTrainingService(
            self._session,
            require_complete_maps=self._require_complete_maps,
            persist=False,
            rebuild_ratings=False,
            context_mode=CONTEXT_MODE_V2,
            context_spec=self._spec,
            shrinkage_k=self._shrinkage_k,
            feature_names=FROZEN_COMBAT_FEATURES,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
            split_ids=split_ids_arg,
            eligible_map_ids=eligible_map_ids,
            team_rating_service=self._team_rating_service,
        )
        try:
            _result, bundle = trainer.fit_cir_v01()
        except (ValueError, np.linalg.LinAlgError):
            return None
        return bundle

    def _apply_all(self, bundle: CIREvaluationBundle) -> dict[str, AppliedCombat]:
        return {
            kind: apply_parameterization(bundle, kind, self._shrinkage_k)
            for kind in CANDIDATE_KINDS
        }

    def _collect_fold(
        self,
        applied: dict[str, AppliedCombat],
        coef_folds: dict[str, list[float]],
        pca_kpr: list[float],
        pca_ndpr: list[float],
    ) -> None:
        for kind, model in applied.items():
            value = combat_coefficient(kind, model.coefficients)
            if kind == TWO_FEATURE:
                kpr = model.coefficients.coefficients.get(KPR_FEATURE)
                if kpr is not None:
                    coef_folds[kind].append(float(kpr))
            elif value is not None:
                coef_folds[kind].append(float(value))
            if kind == PCA_COMBAT_FACTOR and model.pca is not None:
                pca_kpr.append(model.pca.kpr_loading_pc1)
                pca_ndpr.append(model.pca.ndpr_loading_pc1)

    def _temporal(
        self,
        primary: CIREvaluationBundle,
        coef_folds: dict[str, list[float]],
        pca_kpr: list[float],
        pca_ndpr: list[float],
    ) -> list[CombatTemporalResult]:
        rows: list[CombatTemporalResult] = []
        for train_frac, val_frac in TEMPORAL_SPLIT_GRID:
            if abs(train_frac - PRIMARY_TRAIN_FRACTION) < 1e-9:
                bundle: CIREvaluationBundle | None = primary
            else:
                bundle = self._fit_context(train_fraction=train_frac, validation_fraction=val_frac)
            if bundle is None:
                continue
            applied = self._apply_all(bundle)
            self._collect_fold(applied, coef_folds, pca_kpr, pca_ndpr)
            for kind, model in applied.items():
                rows.append(self._temporal_row(kind, model, train_frac, val_frac))
        return rows

    def _temporal_row(
        self,
        kind: str,
        model: AppliedCombat,
        train_frac: float,
        val_frac: float,
    ) -> CombatTemporalResult:
        coefs = model.coefficients.coefficients
        pca = model.pca
        return CombatTemporalResult(
            kind=kind,
            name=f"{train_frac:.3g}/{val_frac:.3g}/{1 - train_frac - val_frac:.3g}",
            train_fraction=train_frac,
            validation_fraction=val_frac,
            test_fraction=max(0.0, 1.0 - train_frac - val_frac),
            n_train_maps=map_count(model.bundle, "train"),
            n_val_maps=map_count(model.bundle, "validation"),
            n_test_maps=map_count(model.bundle, "test"),
            validation_metrics=model.val_metrics,
            test_metrics=model.test_metrics,
            combat_coefficient=combat_coefficient(kind, model.coefficients),
            kpr_coefficient=coefs.get(KPR_FEATURE) if kind == TWO_FEATURE else None,
            negative_dpr_coefficient=(
                coefs.get(NEGATIVE_DPR_FEATURE) if kind == TWO_FEATURE else None
            ),
            ridge_alpha=model.ridge_alpha,
            role_median_gap=model.role_gap,
            kpr_loading_pc1=pca.kpr_loading_pc1 if pca is not None else None,
            ndpr_loading_pc1=pca.ndpr_loading_pc1 if pca is not None else None,
        )

    def _rolling(
        self,
        primary: CIREvaluationBundle,
        coef_folds: dict[str, list[float]],
        pca_kpr: list[float],
        pca_ndpr: list[float],
    ) -> list[CombatRollingSummary]:
        events = ordered_events(primary)
        by_event = maps_by_event(primary)
        min_train = 2 if len(events) < 4 else 3
        by_kind: dict[str, list[CombatRollingFold]] = defaultdict(list)
        for index in range(min_train, len(events)):
            train_events = events[:index]
            val_event = events[index]
            train_maps: list[UUID] = []
            for event in train_events:
                train_maps.extend(by_event[event[0]])
            nested_train, nested_val = chronological_two_way(
                order_maps(primary, train_maps), NESTED_TRAIN_FRACTION
            )
            bundle = self._fit_context(
                split_ids_arg=(nested_train, nested_val, set(by_event[val_event[0]]))
            )
            if bundle is None:
                continue
            applied = self._apply_all(bundle)
            self._collect_fold(applied, coef_folds, pca_kpr, pca_ndpr)
            for kind, model in applied.items():
                pca = model.pca
                by_kind[kind].append(
                    CombatRollingFold(
                        kind=kind,
                        train_events=[item[1] for item in train_events],
                        validation_event=val_event[1],
                        n_train_maps=len(nested_train),
                        n_val_maps=len(by_event[val_event[0]]),
                        validation_metrics=model.test_metrics,
                        combat_coefficient=combat_coefficient(kind, model.coefficients),
                        kpr_loading_pc1=pca.kpr_loading_pc1 if pca is not None else None,
                        ndpr_loading_pc1=pca.ndpr_loading_pc1 if pca is not None else None,
                        role_median_gap=model.role_gap,
                    )
                )
        summaries: list[CombatRollingSummary] = []
        for kind in CANDIDATE_KINDS:
            folds = by_kind.get(kind, [])
            rmses = [
                float(item.validation_metrics.rmse)
                for item in folds
                if item.validation_metrics.rmse is not None
            ]
            r2s = [
                float(item.validation_metrics.r2)
                for item in folds
                if item.validation_metrics.r2 is not None
            ]
            rhos = [
                float(item.validation_metrics.spearman)
                for item in folds
                if item.validation_metrics.spearman is not None
            ]
            summaries.append(
                CombatRollingSummary(
                    kind=kind,
                    folds=folds,
                    rmse=numeric_summary(rmses),
                    r2=numeric_summary(r2s),
                    spearman=numeric_summary(rhos),
                )
            )
        return summaries

    def _event_holdouts(
        self,
        primary: CIREvaluationBundle,
        coef_folds: dict[str, list[float]],
        pca_kpr: list[float],
        pca_ndpr: list[float],
    ) -> tuple[list[CombatEventHoldout], dict[str, dict[str, float]]]:
        events = ordered_events(primary)
        by_event = maps_by_event(primary)
        unique_maps = list(dict.fromkeys(row.stats.match_map_id for row in primary.prepared_maps))
        rows: list[CombatEventHoldout] = []
        holdout_rmse: dict[str, dict[str, float]] = defaultdict(dict)
        for event_id, name, vlr_id, tier, region in events:
            holdout = set(by_event[event_id])
            others = [
                map_id for map_id in order_maps(primary, unique_maps) if map_id not in holdout
            ]
            if len(others) < MIN_TRAIN_TEAM_MAPS:
                continue
            train_ids, val_ids = chronological_two_way(others, NESTED_TRAIN_FRACTION)
            bundle = self._fit_context(split_ids_arg=(train_ids, val_ids, holdout))
            if bundle is None:
                continue
            applied = self._apply_all(bundle)
            self._collect_fold(applied, coef_folds, pca_kpr, pca_ndpr)
            for kind in LOEO_KINDS:
                model = applied[kind]
                rows.append(
                    CombatEventHoldout(
                        kind=kind,
                        event_id=str(event_id),
                        event_name=name,
                        vlr_event_id=vlr_id,
                        tier=tier,
                        region=region,
                        n_train_maps=len(train_ids),
                        n_holdout_maps=len(holdout),
                        holdout_metrics=model.test_metrics,
                        combat_coefficient=combat_coefficient(kind, model.coefficients),
                        role_median_gap=model.role_gap,
                    )
                )
                if model.test_metrics.rmse is not None:
                    holdout_rmse[str(event_id)][kind] = model.test_metrics.rmse
            uni = univariate_baselines(bundle)
            for baseline in ("kd", "acs", "vlr"):
                rmse = uni[baseline][1].rmse
                if rmse is not None:
                    holdout_rmse[str(event_id)][baseline] = rmse
        return rows, holdout_rmse

    def _tier(
        self,
        coef_folds: dict[str, list[float]],
        pca_kpr: list[float],
        pca_ndpr: list[float],
    ) -> list[CombatTierResult]:
        rows: list[CombatTierResult] = []
        map_tiers = self._map_tiers()
        t1 = {map_id for map_id, tier in map_tiers.items() if tier == "T1"}
        t2 = {map_id for map_id, tier in map_tiers.items() if tier == "T2"}
        protocols: list[tuple[str, CIREvaluationBundle | None, str]] = []
        if len(t1) >= MIN_TRAIN_TEAM_MAPS:
            protocols.append(("T1_only", self._fit_context(eligible_map_ids=t1), "validation"))
        if len(t2) >= MIN_TRAIN_TEAM_MAPS:
            protocols.append(("T2_only", self._fit_context(eligible_map_ids=t2), "validation"))
        if t1 and t2:
            train_t1, val_t1 = chronological_two_way(
                self._ordered_eligible(t1), NESTED_TRAIN_FRACTION
            )
            protocols.append(
                (
                    "train_T1_eval_T2",
                    self._fit_context(split_ids_arg=(train_t1, val_t1, t2)),
                    "test",
                )
            )
            train_t2, val_t2 = chronological_two_way(
                self._ordered_eligible(t2), NESTED_TRAIN_FRACTION
            )
            protocols.append(
                (
                    "train_T2_eval_T1",
                    self._fit_context(split_ids_arg=(train_t2, val_t2, t1)),
                    "test",
                )
            )
        for name, bundle, eval_split in protocols:
            if bundle is None:
                continue
            applied = self._apply_all(bundle)
            self._collect_fold(applied, coef_folds, pca_kpr, pca_ndpr)
            for kind, model in applied.items():
                metrics = model.val_metrics if eval_split == "validation" else model.test_metrics
                value = combat_coefficient(kind, model.coefficients)
                if kind == TWO_FEATURE:
                    kpr = model.coefficients.coefficients.get(KPR_FEATURE)
                    ndpr = model.coefficients.coefficients.get(NEGATIVE_DPR_FEATURE)
                    sign = (
                        "positive"
                        if coefficient_sign(kpr) == "positive"
                        and coefficient_sign(ndpr) == "positive"
                        else "mixed"
                    )
                else:
                    sign = coefficient_sign(value)
                rows.append(
                    CombatTierResult(
                        kind=kind,
                        name=name,
                        n_train_maps=map_count(model.bundle, "train"),
                        n_eval_maps=map_count(model.bundle, eval_split),
                        evaluation_metrics=metrics,
                        combat_coefficient=value,
                        coefficient_sign=sign,
                        kpr_coefficient=(
                            model.coefficients.coefficients.get(KPR_FEATURE)
                            if kind == TWO_FEATURE
                            else None
                        ),
                        negative_dpr_coefficient=(
                            model.coefficients.coefficients.get(NEGATIVE_DPR_FEATURE)
                            if kind == TWO_FEATURE
                            else None
                        ),
                        role_median_gap=model.role_gap,
                    )
                )
        return rows

    def _bootstrap_row(self, kind: str, draws: dict[str, list[float]]) -> CombatBootstrapResult:
        coef = draws["coefficient"]
        return CombatBootstrapResult(
            kind=kind,
            iterations=len(coef),
            coefficient=coefficient_summary(coef),
            interval_2_5=percentile(coef, 2.5) if coef else None,
            interval_97_5=percentile(coef, 97.5) if coef else None,
            rmse=numeric_summary(draws["rmse"]),
            r2=numeric_summary(draws["r2"]),
            spearman=numeric_summary(draws["spearman"]),
            kpr_loading=coefficient_summary(draws["kpr_loading"]),
            ndpr_loading=coefficient_summary(draws["ndpr_loading"]),
            explained_pc1=numeric_summary(draws["explained"]),
        )

    def _ranking(self, applied: dict[str, AppliedCombat]) -> list[CombatRankingComparison]:
        two_scores = applied[TWO_FEATURE].player_scores
        rows: list[CombatRankingComparison] = []
        for kind, model in applied.items():
            full = {str(score.player_id): score for score in model.player_scores.values()}
            two_full = {str(score.player_id): score for score in two_scores.values()}
            for threshold in RANKING_ROUND_THRESHOLDS:
                eligible = [
                    player_id for player_id, score in full.items() if score.rounds >= threshold
                ]
                partial = partial_period_scores(
                    model.bundle,
                    model.coefficients,
                    model.feature_names,
                    threshold,
                    self._shrinkage_k,
                    model.bundle.reference_mean,
                )
                if len(eligible) < 2:
                    rows.append(
                        CombatRankingComparison(
                            kind=kind, round_threshold=threshold, eligible_players=len(eligible)
                        )
                    )
                    continue
                full_order = ordered_player_ids(
                    {player_id: full[player_id].cir for player_id in eligible}
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
                two_order = ordered_player_ids(
                    {
                        player_id: two_full[player_id].cir
                        for player_id in eligible
                        if player_id in two_full
                    }
                )
                vs_two, _tau = ranking_correlations(rank_map(two_order), rank_map(full_order))
                rows.append(
                    CombatRankingComparison(
                        kind=kind,
                        round_threshold=threshold,
                        eligible_players=len(eligible),
                        spearman_vs_full=spearman,
                        kendall_tau=kendall,
                        mean_absolute_rank_movement=mean_move,
                        median_absolute_rank_movement=median_move,
                        top_10_retention=top_n_retention(full_order, partial_order, 10),
                        top_25_retention=top_n_retention(full_order, partial_order, 25),
                        top_50_retention=top_n_retention(full_order, partial_order, 50),
                        spearman_vs_two_feature=vs_two,
                    )
                )
        return rows

    def _player_uncertainty(
        self, applied: dict[str, AppliedCombat]
    ) -> tuple[list[CombatPlayerUncertainty], list[CombatPlayerUncertainty]]:
        primary = applied[TWO_FEATURE].bundle
        means = player_combat_means(primary)
        kpr_vals = [item[0] for item in means.values()]
        ndpr_vals = [item[1] for item in means.values()]
        kpr_median = float(np.median(kpr_vals)) if kpr_vals else 0.0
        ndpr_median = float(np.median(ndpr_vals)) if ndpr_vals else 0.0
        rows: list[CombatPlayerUncertainty] = []
        sensitive: list[CombatPlayerUncertainty] = []
        for kind in (TWO_FEATURE, NET_COMBAT_RATE, PCA_COMBAT_FACTOR, EQUAL_WEIGHT):
            model = applied[kind]
            draws = bootstrap_player_draws(
                model.bundle,
                model.feature_names,
                model.ridge_alpha,
                self._shrinkage_k,
                iterations=min(self._bootstrap_iterations, 80),
                seed=self._bootstrap_seed,
            )
            for score in sorted(model.player_scores.values(), key=lambda item: -item.rounds):
                if score.rounds < 100:
                    continue
                samples = draws.get(score.player_id, [])
                if len(samples) < 5:
                    continue
                combat = means.get(score.player_id)
                profile = None
                mean_kpr = mean_ndpr = None
                if combat is not None:
                    mean_kpr, mean_ndpr, _rounds = combat
                    profile = profile_label(mean_kpr, mean_ndpr, kpr_median, ndpr_median)
                cir_values = [item[0] for item in samples]
                rank_values = [item[1] for item in samples]
                row = CombatPlayerUncertainty(
                    kind=kind,
                    player_id=str(score.player_id),
                    handle=score.handle,
                    rounds=score.rounds,
                    cir_median=percentile(cir_values, 50),
                    cir_p05=percentile(cir_values, 5),
                    cir_p95=percentile(cir_values, 95),
                    rank_median=percentile(rank_values, 50),
                    rank_p05=percentile(rank_values, 5),
                    rank_p95=percentile(rank_values, 95),
                    mean_kpr_residual=mean_kpr,
                    mean_negative_dpr_residual=mean_ndpr,
                    profile=profile,
                )
                if len([item for item in rows if item.kind == kind]) < 20:
                    rows.append(row)
                span = (row.rank_p95 or 0.0) - (row.rank_p05 or 0.0)
                if (
                    profile is not None
                    and score.rounds >= 250
                    and span >= 20
                    and len(sensitive) < 24
                ):
                    sensitive.append(row)
        return rows, sensitive

    def _baselines(
        self,
        bundle: CIREvaluationBundle,
        applied: dict[str, AppliedCombat],
        preserved: dict[str, object] | None,
    ) -> list[CombatBaselineRow]:
        rows = [
            CombatBaselineRow(
                name=kind,
                validation_metrics=applied[kind].val_metrics,
                test_metrics=applied[kind].test_metrics,
                source="combat parameterization on identical maps/split",
            )
            for kind in CANDIDATE_KINDS
        ]
        uni = univariate_baselines(bundle)
        labels = {
            "kd": "team_average_kd",
            "acs": "team_average_acs",
            "vlr": "team_average_vlr_rating",
        }
        for key, name in labels.items():
            rows.append(
                CombatBaselineRow(
                    name=name,
                    validation_metrics=uni[key][0],
                    test_metrics=uni[key][1],
                    source="univariate on identical eligible maps and split",
                )
            )
        if preserved is not None:
            stored = preserved.get("regularization")
            if isinstance(stored, dict):
                metrics = stored.get("validation_metrics")
                if isinstance(metrics, dict):
                    rows.append(
                        CombatBaselineRow(
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

    def _event_wins(
        self, holdout_rmse: dict[str, dict[str, float]], strongest: str
    ) -> tuple[dict[str, int], dict[str, int]]:
        by_kind: dict[str, int] = defaultdict(int)
        for scores in holdout_rmse.values():
            if scores:
                by_kind[min(scores, key=lambda name: scores[name])] += 1
        single = two = vlr = kd = acs = 0
        single_kind = strongest if strongest != TWO_FEATURE else NET_COMBAT_RATE
        for scores in holdout_rmse.values():
            subset = {
                key: scores[key]
                for key in (single_kind, TWO_FEATURE, "vlr", "kd", "acs")
                if key in scores
            }
            if not subset:
                continue
            winner = min(subset, key=lambda name: subset[name])
            if winner == single_kind:
                single += 1
            elif winner == TWO_FEATURE:
                two += 1
            elif winner == "vlr":
                vlr += 1
            elif winner == "kd":
                kd += 1
            elif winner == "acs":
                acs += 1
        return dict(by_kind), {"single": single, "two": two, "vlr": vlr, "kd": kd, "acs": acs}

    def _leakage(self, bundle: CIREvaluationBundle) -> list[LeakageAuditItem]:
        periods = split_periods(bundle)
        train = periods["train"]
        return [
            LeakageAuditItem(
                name="team_elo",
                fit_scope="chronological pre-match snapshots",
                earliest_date=train[0],
                latest_date=train[1],
                notes="Pre-match Elo only.",
            ),
            LeakageAuditItem(
                name="context_v2_expectations",
                fit_scope="train maps",
                earliest_date=train[0],
                latest_date=train[1],
                notes="Frozen train registry. No context retuning.",
            ),
            LeakageAuditItem(
                name="kpr_ndpr_standardization",
                fit_scope="train player-maps",
                earliest_date=train[0],
                latest_date=train[1],
                notes="mu/sigma frozen from train before PCA/equal-weight.",
            ),
            LeakageAuditItem(
                name="net_combat_rate_standardization",
                fit_scope="train player-maps",
                earliest_date=train[0],
                latest_date=train[1],
                notes="NCR mean/std fit on train only.",
            ),
            LeakageAuditItem(
                name="pca_loadings",
                fit_scope="train player-maps",
                earliest_date=train[0],
                latest_date=train[1],
                notes="PCA fitted on train z-scores; val/test use frozen loadings and train mean.",
            ),
            LeakageAuditItem(
                name="ridge_alpha_and_coefficients",
                fit_scope="train design; alpha selected on validation",
                earliest_date=train[0],
                latest_date=periods["validation"][1],
                notes="Test never used for alpha, PCA, or NCR standardization.",
            ),
            LeakageAuditItem(
                name="bootstrap_folds",
                fit_scope="resampled train matches",
                earliest_date=train[0],
                latest_date=train[1],
                notes="Bootstrap never includes validation/test maps.",
            ),
        ]

    def _snapshots(
        self,
        applied: dict[str, AppliedCombat],
        bootstraps: dict[str, dict[str, list[float]]],
        ranking: list[CombatRankingComparison],
        tier_rows: list[CombatTierResult],
        holdouts: list[CombatEventHoldout],
        baselines: list[CombatBaselineRow],
    ) -> list[CombatCandidateSnapshot]:
        two_rmse = applied[TWO_FEATURE].val_metrics.rmse
        snapshots: list[CombatCandidateSnapshot] = []
        for kind, model in applied.items():
            draws = bootstraps[kind]["coefficient"]
            ranking_250 = next(
                (
                    item.spearman_vs_full
                    for item in ranking
                    if item.kind == kind and item.round_threshold == 250
                ),
                None,
            )
            ranking_500 = next(
                (
                    item.spearman_vs_full
                    for item in ranking
                    if item.kind == kind and item.round_threshold == 500
                ),
                None,
            )
            later = [
                item.holdout_metrics.rmse
                for item in holdouts
                if item.kind == kind and item.holdout_metrics.rmse is not None
            ]
            collapse = bool(
                two_rmse is not None
                and any(
                    rmse > two_rmse * LATER_EVENT_RMSE_RATIO_LIMIT
                    for rmse in later
                    if rmse is not None
                )
            )
            signs = [
                item.coefficient_sign
                for item in tier_rows
                if item.kind == kind and item.name in {"T1_only", "T2_only"}
            ]
            tier_ok = bool(signs) and all(sign == "positive" for sign in signs)
            combat_rmse = model.val_metrics.rmse
            baseline_ok = True
            if combat_rmse is not None:
                for name in ("team_average_kd", "team_average_acs", "team_average_vlr_rating"):
                    other = next((item for item in baselines if item.name == name), None)
                    if (
                        other is not None
                        and other.validation_metrics.rmse is not None
                        and combat_rmse >= other.validation_metrics.rmse
                    ):
                        baseline_ok = False
            coef = combat_coefficient(kind, model.coefficients)
            if kind == TWO_FEATURE:
                kpr = model.coefficients.coefficients.get(KPR_FEATURE)
                ndpr = model.coefficients.coefficients.get(NEGATIVE_DPR_FEATURE)
                positive = (kpr or 0) > 0 and (ndpr or 0) > 0
            else:
                positive = coef is not None and coef > 0
            snapshots.append(
                CombatCandidateSnapshot(
                    kind=kind,
                    val_rmse=model.val_metrics.rmse,
                    role_gap=model.role_gap,
                    bootstrap_p025=percentile(draws, 2.5) if draws else None,
                    bootstrap_sign_flips=sum(1 for value in draws if value < 0),
                    bootstrap_draws=len(draws),
                    ranking_spearman_250=ranking_250,
                    ranking_spearman_500=ranking_500,
                    coefficient_positive=positive,
                    temporal_collapse=collapse,
                    tier_sign_stable=tier_ok,
                    baseline_advantage=baseline_ok,
                )
            )
        return snapshots

    def _coef_stability(
        self,
        coef_folds: dict[str, list[float]],
        pca_kpr: list[float],
        pca_ndpr: list[float],
    ) -> list[CombatCoefficientStability]:
        rows: list[CombatCoefficientStability] = []
        for kind in CANDIDATE_KINDS:
            values = coef_folds.get(kind, [])
            pca_load = kind == PCA_COMBAT_FACTOR
            rows.append(
                CombatCoefficientStability(
                    kind=kind,
                    coefficient=coefficient_summary(values),
                    kpr_loading=coefficient_summary(pca_kpr if pca_load else []),
                    ndpr_loading=coefficient_summary(pca_ndpr if pca_load else []),
                    fold_count=len(values),
                )
            )
        return rows

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
        return {row.match_map_id: event_tier(row.match_map.match.event) for row in stats}

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
                f"{CIR_REAL_EXPERIMENT_VERSION} changed during combat-factor experiment"
            )
