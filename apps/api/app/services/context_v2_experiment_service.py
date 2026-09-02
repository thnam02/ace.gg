from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_scoring import (
    apply_shrinkage,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_v01 import DEFAULT_SHRINKAGE_K
from app.metrics.cir_validation_metrics import mae, spearman_correlation
from app.metrics.context_v2_config import (
    CONTEXT_MODE_NONE,
    CONTEXT_SHRINKAGE_K_CANDIDATES,
    TAU_CANDIDATES,
    ContextExperimentSpec,
    default_context_experiment_matrix,
)
from app.metrics.context_v2_diagnostics import (
    decide_context_recommendation,
    diagnose_controller_shift,
    feature_dispositions,
    feature_stat_summary,
    role_bias_metrics,
    select_context_configuration,
)
from app.metrics.ridge_regression import r2_score, rmse
from app.models import MetricVersion
from app.schemas.context_v2 import (
    ContextExperimentResult,
    ContextV2ExperimentReport,
    ContextV2Recommendation,
    ControllerShiftDiagnosis,
    SplitMetrics,
)
from app.services.cir_training_service import (
    CIREvaluationBundle,
    CIRTrainingService,
    _design_matrix,
    _PlayerMapPrepared,
)
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from app.services.team_rating_service import TeamRatingService


class ContextV2ExperimentService:
    """Run context-adjustment experiments without mutating CIR v0.1-real-2026."""

    def __init__(
        self,
        session: Session,
        *,
        require_complete_maps: bool = True,
        matrix: dict[str, ContextExperimentSpec] | None = None,
        shrinkage_k: float = DEFAULT_SHRINKAGE_K,
    ) -> None:
        self._session = session
        self._require_complete_maps = require_complete_maps
        self._matrix = matrix if matrix is not None else default_context_experiment_matrix()
        self._shrinkage_k = shrinkage_k
        self._team_rating_service = TeamRatingService(session)

    def run(self) -> ContextV2ExperimentReport:
        preserved = self._snapshot_v01_real()
        self._team_rating_service.rebuild_team_ratings()

        results: list[ContextExperimentResult] = []
        bundles: dict[str, CIREvaluationBundle] = {}
        for spec in self._matrix.values():
            resolved = self._resolve_spec(spec)
            result, bundle = self._run_spec(resolved)
            results.append(result)
            bundles[result.name] = bundle

        winner = select_context_configuration(results)
        winner_bundle = bundles[winner.name]
        k_rows, recommended_k = self._tune_shrinkage_k(winner_bundle)
        winner.selected_shrinkage_k = recommended_k

        diagnosis_rows = [
            (
                row.stats.agent.role if row.stats.agent is not None else "Unknown",
                row.stats.rounds,
                row.adjusted,
            )
            for row in winner_bundle.prepared_maps
            if row.adjusted is not None
        ]
        controller = diagnose_controller_shift(
            diagnosis_rows,
            winner.coefficients,
        )
        dispositions = feature_dispositions(winner.coefficients, winner.feature_stats)
        decision = decide_context_recommendation(winner)
        raw_rules = winner.configuration.get("feature_rules") or {}
        feature_rules = (
            {str(key): str(value) for key, value in raw_rules.items()}
            if isinstance(raw_rules, dict)
            else {}
        )
        recommendation = ContextV2Recommendation(
            decision=decision,
            feature_rules=feature_rules,
            selected_lambda=winner.selected_lambda,
            selected_tau=winner.selected_tau,
            selected_shrinkage_k=recommended_k,
            feature_dispositions=dispositions,
            reasons=self._reasons(winner, results, controller, recommended_k, decision),
        )

        self._assert_v01_real_unchanged(preserved)
        return ContextV2ExperimentReport(
            experiments=results,
            best_validation_configuration=winner.name,
            final_test_result=winner.test_metrics,
            controller_diagnosis=controller,
            shrinkage_k_results=k_rows,
            recommendations=recommendation,
            preserved_metric_version=CIR_REAL_EXPERIMENT_VERSION,
        )

    def _resolve_spec(self, spec: ContextExperimentSpec) -> ContextExperimentSpec:
        if spec.tune_tau:
            return self._tune_tau(spec)
        if spec.tune_lambda:
            return self._tune_lambda(spec)
        return spec

    def _tune_tau(self, spec: ContextExperimentSpec) -> ContextExperimentSpec:
        best_tau = spec.tau
        best_rmse = float("inf")
        for tau in TAU_CANDIDATES:
            candidate = ContextExperimentSpec(
                name=spec.name,
                mode=spec.mode,
                lam=spec.lam,
                tau=tau,
                hierarchical=True,
                tune_tau=False,
                rules=spec.rules,
                simplicity_rank=spec.simplicity_rank,
            )
            result, _bundle = self._run_spec(candidate)
            rmse_value = result.validation_metrics.rmse
            if rmse_value is not None and rmse_value < best_rmse:
                best_rmse = rmse_value
                best_tau = tau
        return ContextExperimentSpec(
            name=spec.name,
            mode=spec.mode,
            lam=spec.lam,
            tau=best_tau,
            hierarchical=True,
            tune_tau=False,
            rules=spec.rules,
            simplicity_rank=spec.simplicity_rank,
        )

    def _tune_lambda(self, spec: ContextExperimentSpec) -> ContextExperimentSpec:
        from app.metrics.context_v2_config import LAMBDA_CANDIDATES

        best_lambda = spec.lam
        best_rmse = float("inf")
        for lam in LAMBDA_CANDIDATES:
            candidate = ContextExperimentSpec(
                name=spec.name,
                mode=spec.mode,
                lam=lam,
                tau=spec.tau,
                hierarchical=spec.hierarchical,
                tune_lambda=False,
                rules=spec.rules,
                simplicity_rank=spec.simplicity_rank,
            )
            result, _bundle = self._run_spec(candidate)
            rmse_value = result.validation_metrics.rmse
            if rmse_value is not None and rmse_value < best_rmse:
                best_rmse = rmse_value
                best_lambda = lam
        return ContextExperimentSpec(
            name=spec.name,
            mode=spec.mode,
            lam=best_lambda,
            tau=spec.tau,
            hierarchical=spec.hierarchical,
            tune_lambda=False,
            rules=spec.rules,
            simplicity_rank=spec.simplicity_rank,
        )

    def _run_spec(
        self,
        spec: ContextExperimentSpec,
    ) -> tuple[ContextExperimentResult, CIREvaluationBundle]:
        trainer = CIRTrainingService(
            self._session,
            require_complete_maps=self._require_complete_maps,
            persist=False,
            rebuild_ratings=False,
            context_mode=spec.mode,
            context_spec=spec,
            shrinkage_k=self._shrinkage_k,
        )
        training, bundle = trainer.fit_cir_v01()
        val_metrics = self._metrics_for_split(bundle, "validation")
        test_metrics = self._metrics_for_split(bundle, "test")
        role_values = self._player_role_scores(bundle)
        roles = role_bias_metrics(role_values)
        train_features = [row.raw_features for row in bundle.prepared_maps if row.split == "train"]
        stats = feature_stat_summary(train_features, training.coefficients, bundle.feature_names)
        usage = _context_usage(bundle.prepared_maps)
        configuration = spec.configuration()
        configuration["simplicity_rank"] = spec.simplicity_rank
        if spec.mode == CONTEXT_MODE_NONE:
            configuration["feature_rules"] = {
                name: "none"
                for name in (
                    "kpr",
                    "dpr",
                    "apr",
                    "kast",
                    "opening_frequency",
                    "opening_efficiency",
                    "residual_adr",
                    "clutch",
                )
            }
            configuration["lambda"] = 0.0
            configuration["tau"] = 0.0
        result = ContextExperimentResult(
            name=spec.name,
            configuration=configuration,
            validation_metrics=val_metrics,
            test_metrics=test_metrics,
            role_bias_metrics=roles,
            coefficients=training.coefficients,
            feature_stats=stats,
            context_usage=usage,
            selected_lambda=spec.lam,
            selected_tau=spec.tau,
            selected_shrinkage_k=self._shrinkage_k,
            ridge_alpha=training.ridge_alpha,
        )
        return result, bundle

    def _metrics_for_split(self, bundle: CIREvaluationBundle, split: str) -> SplitMetrics:
        team_maps = [row for row in bundle.team_maps if row.split == split]
        design, targets = _design_matrix(team_maps, feature_names=bundle.feature_names)
        if len(targets) == 0:
            return SplitMetrics()
        weights = np.array(
            [bundle.full_coefficients.coefficients.get(name, 0.0) for name in bundle.feature_names],
            dtype=np.float64,
        )
        predictions = bundle.full_coefficients.intercept + design[:, 1:] @ weights
        return SplitMetrics(
            rmse=rmse(targets, predictions),
            mae=mae(targets, predictions),
            r2=r2_score(targets, predictions),
            spearman=spearman_correlation(targets, predictions),
        )

    def _player_role_scores(
        self,
        bundle: CIREvaluationBundle,
        shrinkage_k: float | None = None,
    ) -> dict[str, list[tuple[float, int]]]:
        k = self._shrinkage_k if shrinkage_k is None else shrinkage_k
        by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
        roles: dict[UUID, str] = {}
        for row in bundle.prepared_maps:
            raw = compute_raw_cir(
                row.standardized_features,
                bundle.full_coefficients,
                feature_names=bundle.feature_names,
            )
            by_player[row.stats.player_id].append((raw, row.stats.rounds))
            if row.stats.agent is not None:
                roles[row.stats.player_id] = row.stats.agent.role
        grouped: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for player_id, values in by_player.items():
            raw_mean = round_weighted_mean(values)
            rounds = sum(weight for _, weight in values)
            if raw_mean is None:
                continue
            shrunk = apply_shrinkage(raw_mean, rounds, bundle.reference_mean, k)
            cir = empirical_cdf(shrunk, bundle.reference_population)
            role = roles.get(player_id, "Unknown")
            grouped[role].append((cir, rounds))
        return grouped

    def _tune_shrinkage_k(
        self,
        bundle: CIREvaluationBundle,
    ) -> tuple[list[dict[str, float | None]], float]:
        rows: list[dict[str, float | None]] = []
        best_k = CONTEXT_SHRINKAGE_K_CANDIDATES[0]
        best_score = float("-inf")
        for k in CONTEXT_SHRINKAGE_K_CANDIDATES:
            role_values = self._player_role_scores(bundle, shrinkage_k=k)
            bias = role_bias_metrics(role_values)
            association = self._validation_team_cir_spearman(bundle, k)
            scores = [score for pairs in role_values.values() for score, _ in pairs]
            std = float(np.std(np.array(scores, dtype=np.float64))) if scores else None
            rows.append(
                {
                    "k": k,
                    "score_std": std,
                    "max_role_median_gap": bias.max_role_median_gap,
                    "validation_spearman": association,
                }
            )
            if association is not None and association > best_score:
                best_score = association
                best_k = k
        return rows, best_k

    def _validation_team_cir_spearman(
        self,
        bundle: CIREvaluationBundle,
        shrinkage_k: float,
    ) -> float | None:
        player_cir: dict[UUID, float] = {}
        by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
        for row in bundle.prepared_maps:
            raw = compute_raw_cir(
                row.standardized_features,
                bundle.full_coefficients,
                feature_names=bundle.feature_names,
            )
            by_player[row.stats.player_id].append((raw, row.stats.rounds))
        for player_id, values in by_player.items():
            raw_mean = round_weighted_mean(values)
            rounds = sum(weight for _, weight in values)
            if raw_mean is None:
                continue
            shrunk = apply_shrinkage(raw_mean, rounds, bundle.reference_mean, shrinkage_k)
            player_cir[player_id] = empirical_cdf(shrunk, bundle.reference_population)

        deltas: list[float] = []
        outcomes: list[float] = []
        prepared_by_map: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
        for row in bundle.prepared_maps:
            prepared_by_map[row.stats.match_map_id].append(row)
        for team_map in bundle.team_maps:
            if team_map.split != "validation":
                continue
            rows = prepared_by_map.get(team_map.match_map_id, [])
            if not rows:
                continue
            match = rows[0].stats.match_map.match
            if match.team_a_id is None or match.team_b_id is None:
                continue
            team_a = [
                player_cir[row.stats.player_id]
                for row in rows
                if row.stats.team_id == match.team_a_id and row.stats.player_id in player_cir
            ]
            team_b = [
                player_cir[row.stats.player_id]
                for row in rows
                if row.stats.team_id == match.team_b_id and row.stats.player_id in player_cir
            ]
            if not team_a or not team_b:
                continue
            deltas.append(float(np.mean(team_a) - np.mean(team_b)))
            outcomes.append(team_map.outcome_residual)
        if len(deltas) < 2:
            return None
        return spearman_correlation(
            np.array(deltas, dtype=np.float64),
            np.array(outcomes, dtype=np.float64),
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
                f"{CIR_REAL_EXPERIMENT_VERSION} changed during the context v2 experiment"
            )

    def _reasons(
        self,
        winner: ContextExperimentResult,
        results: list[ContextExperimentResult],
        controller: ControllerShiftDiagnosis,
        recommended_k: float,
        decision: str,
    ) -> list[str]:
        reasons = [
            f"Selected {winner.name} from validation RMSE/R²/Spearman with a simplicity "
            "tie-break; test metrics were not used for selection.",
            (
                f"Validation RMSE={winner.validation_metrics.rmse} "
                f"R²={winner.validation_metrics.r2} "
                f"Spearman={winner.validation_metrics.spearman}."
            ),
            (
                f"max_role_median_gap={winner.role_bias_metrics.max_role_median_gap} "
                f"Controller vs Initiator="
                f"{winner.role_bias_metrics.controller_vs_initiator_gap}."
            ),
            f"Recommended player shrinkage k={recommended_k} from validation association only.",
            f"Decision={decision}. CIR v0.2 was not implemented.",
        ]
        for line in controller.evidence[:4]:
            reasons.append(line)
        by_name = {item.name: item for item in results}
        if "no_context" in by_name and "context_v1" in by_name:
            none_rmse = by_name["no_context"].validation_metrics.rmse
            v1_rmse = by_name["context_v1"].validation_metrics.rmse
            if none_rmse is not None and v1_rmse is not None:
                reasons.append(
                    f"no_context validation RMSE={none_rmse:.4f} vs context_v1 {v1_rmse:.4f}."
                )
        return reasons


def _context_usage(prepared_maps: list[_PlayerMapPrepared]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in prepared_maps:
        if row.adjusted is not None and row.adjusted.feature_baseline_levels:
            for level in row.adjusted.feature_baseline_levels.values():
                counts[level] += 1
        elif row.baseline_level:
            counts[row.baseline_level] += 1
    return dict(counts)
