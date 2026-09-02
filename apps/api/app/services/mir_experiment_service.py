from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir_feature_diagnostics import relative_rmse_delta
from app.metrics.cir_scoring import build_team_delta_vector
from app.metrics.cir_validation_config import CIR_ROLES
from app.metrics.cir_validation_metrics import distribution_summary, mae, spearman_correlation
from app.metrics.mir.mir_config import (
    APR_CONTEXT,
    COMBAT_FEATURES,
    DEFAULT_MIR_SHRINKAGE_K,
    KAST_CONTEXT,
    OPENING_EFFICIENCY_CONTEXT,
    OPENING_EFFICIENCY_UNIQUE,
    OPENING_FEATURES,
    OPENING_FREQUENCY_CONTEXT,
    OPENING_FREQUENCY_UNIQUE,
    ROUND_PARTICIPATION,
    SUPPORT_ASSIST,
    SUPPORT_FEATURES,
    default_mir_subset_matrix,
    mir_context_spec,
)
from app.metrics.mir.mir_economy import economy_is_usable, inspect_economy_availability
from app.metrics.mir.mir_validation import (
    classify_signal,
    evidence_gate,
    mir_readiness,
    select_mir_decision,
    select_mir_subset,
)
from app.metrics.ridge_regression import r2_score, rmse
from app.models import MetricVersion, PlayerMapStats
from app.schemas.context_v2 import SplitMetrics
from app.schemas.mir_experiment import (
    MirBaselineComparison,
    MirComponentEvidence,
    MirExperimentReport,
    MirMarginalExample,
    MirRawVsUniqueComparison,
    MirRecommendation,
    MirRoleFeatureStats,
    MirSubsetResult,
)
from app.services.cir_training_service import _TeamMapPrepared
from app.services.mir_feature_service import MirPlayerMap
from app.services.mir_training_service import (
    MirEvaluationBundle,
    MirTrainingService,
    stability_rows,
)
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION
from app.services.team_rating_service import TeamRatingService


class MirExperimentService:
    """Run MIR residualization experiments without mutating CIR versions."""

    def __init__(
        self,
        session: Session,
        *,
        require_complete_maps: bool = True,
        shrinkage_k: float = DEFAULT_MIR_SHRINKAGE_K,
        persist: bool = False,
    ) -> None:
        self._session = session
        self._require_complete_maps = require_complete_maps
        self._shrinkage_k = shrinkage_k
        self._persist = persist
        self._team_rating_service = TeamRatingService(session)
        self._trainer = MirTrainingService(
            session,
            require_complete_maps=require_complete_maps,
            shrinkage_k=shrinkage_k,
            persist=persist,
            rebuild_ratings=False,
        )

    def run(self) -> MirExperimentReport:
        preserved = self._snapshot_v01_real()
        self._team_rating_service.rebuild_team_ratings()
        economy_rows = inspect_economy_availability()
        economy_enabled = economy_is_usable(economy_rows)
        bundle = self._trainer.prepare_bundle()
        matrix = default_mir_subset_matrix(economy_enabled=economy_enabled)
        subset_results = [
            self._trainer.fit_subset(bundle, name, features) for name, features in matrix.items()
        ]
        selected = select_mir_subset(subset_results)
        by_name = {item.name: item for item in subset_results}
        combat = by_name["combat_only"]

        raw_vs_unique = [
            self._raw_vs_unique(
                "APR",
                "combat_plus_raw_apr",
                "combat_plus_apr_unique",
                SUPPORT_ASSIST,
                combat,
                by_name,
            ),
            self._raw_vs_unique(
                "KAST",
                "combat_plus_raw_kast",
                "combat_plus_kast_unique",
                ROUND_PARTICIPATION,
                combat,
                by_name,
            ),
            self._raw_vs_unique(
                "Opening Frequency",
                "combat_plus_raw_opening",
                "combat_plus_of_unique",
                OPENING_FREQUENCY_UNIQUE,
                combat,
                by_name,
            ),
            self._raw_vs_unique(
                "Opening Efficiency",
                "combat_plus_raw_opening",
                "combat_plus_oe_unique",
                OPENING_EFFICIENCY_UNIQUE,
                combat,
                by_name,
            ),
        ]
        component_evidence = self._component_evidence(combat, by_name, selected)
        support_enabled = any(
            item.component == "support" and item.disposition == "KEEP"
            for item in component_evidence
        ) and any(name in selected.features for name in SUPPORT_FEATURES)
        opening_enabled = any(
            item.component == "opening" and item.disposition == "KEEP"
            for item in component_evidence
        ) and any(name in selected.features for name in OPENING_FEATURES)

        decision = select_mir_decision(
            selected.name,
            support_enabled=support_enabled,
            opening_enabled=opening_enabled,
            economy_enabled=False,
        )
        if decision != "COMBAT_ONLY_REMAINS_BEST" and selected.name == "combat_only":
            decision = "COMBAT_ONLY_REMAINS_BEST"
            support_enabled = False
            opening_enabled = False
        rmse_delta = relative_rmse_delta(
            combat.validation_metrics.rmse,
            selected.validation_metrics.rmse,
        )
        readiness = mir_readiness(decision, rmse_delta)
        stability = []
        for name in {selected.name, "combat_only", "full_mir_candidate"}:
            item = by_name.get(name)
            if item is not None:
                stability.extend(stability_rows(bundle, item, self._shrinkage_k))

        rec = MirRecommendation(
            decision=decision,
            combat=list(COMBAT_FEATURES),
            support=list(SUPPORT_FEATURES) if support_enabled else [],
            opening=list(OPENING_FEATURES) if opening_enabled else [],
            economy="disabled",
            context=(
                "Context v2; lambda=1; tau=500; KPR/DPR=role+tier; "
                "APR=agent+tier; KAST=role+tier; Opening=agent+tier"
            ),
            shrinkage_k=self._shrinkage_k,
            selected_subset=selected.name,
            readiness=readiness,
            reasons=[
                f"Selected {selected.name} from validation RMSE with a 1% simplicity rule.",
                "Test metrics were reported but not used for selection.",
                "APR/KAST/opening are support/opening participation signals, not utility impact.",
                "EconomyContribution is disabled: no retrievable economy fields.",
                "CIR / v0.1-real-2026 was not overwritten. Frontend is unchanged.",
            ],
        )
        persisted_version = None
        if self._persist and readiness == "READY_FOR_FINAL_VALIDATION":
            version = self._trainer.persist_metric_version(bundle, selected)
            persisted_version = version.version

        self._assert_v01_real_unchanged(preserved)
        return MirExperimentReport(
            context_configuration=mir_context_spec().configuration(),
            shrinkage_k=self._shrinkage_k,
            economy=economy_rows,
            economy_enabled=False,
            residualizers=bundle.residualizers.to_dict(),
            subset_results=subset_results,
            selected_subset=selected.name,
            raw_vs_unique=raw_vs_unique,
            component_evidence=component_evidence,
            role_analysis=self._role_analysis(bundle),
            t1_t2_consistency=_t1_t2_table(by_name),
            stability=stability,
            marginal_examples=_marginal_examples(bundle, selected),
            baselines=self._baselines(bundle, combat, selected),
            recommendation=rec,
            preserved_metric_version=CIR_REAL_EXPERIMENT_VERSION,
            persisted_mir_version=persisted_version,
        )

    def _raw_vs_unique(
        self,
        signal: str,
        raw_name: str,
        unique_name: str,
        unique_feature: str,
        combat: MirSubsetResult,
        by_name: dict[str, MirSubsetResult],
    ) -> MirRawVsUniqueComparison:
        raw = by_name.get(raw_name)
        unique = by_name.get(unique_name)
        raw_rmse = raw.validation_metrics.rmse if raw is not None else None
        unique_rmse = unique.validation_metrics.rmse if unique is not None else None
        combat_rmse = combat.validation_metrics.rmse
        unique_vs_raw = relative_rmse_delta(raw_rmse, unique_rmse)
        unique_vs_combat = relative_rmse_delta(combat_rmse, unique_rmse)
        extra = (unique_feature,) if unique is not None else ()
        passed = False
        evidence: list[str] = []
        if unique is not None:
            passed, evidence = evidence_gate(
                combat,
                unique,
                extra_features=extra,
                t1_coefficients=unique.t1_extra_coefficients,
                t2_coefficients=unique.t2_extra_coefficients,
            )
        harmful = unique_vs_combat is not None and unique_vs_combat > 0.002
        role_specific = False
        if unique is not None:
            t1 = unique.t1_extra_coefficients.get(unique_feature)
            t2 = unique.t2_extra_coefficients.get(unique_feature)
            role_specific = t1 is not None and t2 is not None and t1 * t2 < 0
        conclusion = classify_signal(
            unique_vs_combat_delta=unique_vs_combat,
            unique_vs_raw_delta=unique_vs_raw,
            unique_coef=unique.coefficients.get(unique_feature) if unique is not None else None,
            gate_passed=passed,
            role_specific=role_specific,
            harmful_rmse=harmful,
        )
        if unique_vs_raw is not None:
            evidence = [f"unique vs raw RMSE {unique_vs_raw:+.2%}", *evidence]
        return MirRawVsUniqueComparison(
            signal=signal,
            raw_subset=raw_name,
            unique_subset=unique_name,
            raw_validation_rmse=raw_rmse,
            unique_validation_rmse=unique_rmse,
            combat_validation_rmse=combat_rmse,
            unique_improves_on_raw=bool(unique_vs_raw is not None and unique_vs_raw < 0),
            unique_improves_on_combat=bool(unique_vs_combat is not None and unique_vs_combat < 0),
            conclusion=conclusion,
            evidence=evidence,
        )

    def _component_evidence(
        self,
        combat: MirSubsetResult,
        by_name: dict[str, MirSubsetResult],
        selected: MirSubsetResult,
    ) -> list[MirComponentEvidence]:
        rows: list[MirComponentEvidence] = [
            MirComponentEvidence(
                component="combat",
                disposition="KEEP",
                enabled=True,
                conclusion="Validated combat foundation.",
                evidence=[
                    "kpr_context_residual and negative_dpr_context_residual are the MIR baseline."
                ],
            )
        ]
        support = by_name.get("combat_plus_support_unique")
        opening = by_name.get("combat_plus_opening_unique")
        rows.append(self._component_row("support", SUPPORT_FEATURES, combat, support, selected))
        rows.append(self._component_row("opening", OPENING_FEATURES, combat, opening, selected))
        rows.append(
            MirComponentEvidence(
                component="economy",
                disposition="INSUFFICIENT_DATA",
                enabled=False,
                conclusion="INSUFFICIENT_DATA",
                evidence=["No economy/loadout/buy-type fields exist in the canonical dataset."],
            )
        )
        return rows

    def _component_row(
        self,
        name: str,
        features: tuple[str, ...],
        combat: MirSubsetResult,
        candidate: MirSubsetResult | None,
        selected: MirSubsetResult,
    ) -> MirComponentEvidence:
        if candidate is None:
            return MirComponentEvidence(
                component=name,
                disposition="REMOVE",
                enabled=False,
                conclusion="REDUNDANT_WITH_COMBAT",
                evidence=["Subset was not trained."],
            )
        passed, evidence = evidence_gate(
            combat,
            candidate,
            extra_features=features,
            t1_coefficients=candidate.t1_extra_coefficients,
            t2_coefficients=candidate.t2_extra_coefficients,
        )
        in_selected = any(feature in selected.features for feature in features)
        if passed and in_selected:
            disposition = "KEEP"
            conclusion = "UNIQUE_VALUE_CONFIRMED"
            enabled = True
        elif passed and not in_selected:
            disposition = "ROLE_SPECIFIC_CANDIDATE"
            conclusion = "ROLE_SPECIFIC_ONLY"
            enabled = False
        else:
            delta = relative_rmse_delta(
                combat.validation_metrics.rmse,
                candidate.validation_metrics.rmse,
            )
            disposition = "REMOVE"
            conclusion = (
                "HARMFUL" if delta is not None and delta > 0.002 else "REDUNDANT_WITH_COMBAT"
            )
            enabled = False
        return MirComponentEvidence(
            component=name,
            disposition=disposition,
            enabled=enabled,
            conclusion=conclusion,
            evidence=evidence,
        )

    def _role_analysis(
        self,
        bundle: MirEvaluationBundle,
    ) -> dict[str, list[MirRoleFeatureStats]]:
        pairs = {
            "support_assist": (APR_CONTEXT, SUPPORT_ASSIST),
            "round_participation": (KAST_CONTEXT, ROUND_PARTICIPATION),
            "opening_frequency": (OPENING_FREQUENCY_CONTEXT, OPENING_FREQUENCY_UNIQUE),
            "opening_efficiency": (OPENING_EFFICIENCY_CONTEXT, OPENING_EFFICIENCY_UNIQUE),
        }
        report: dict[str, list[MirRoleFeatureStats]] = {}
        train = [row for row in bundle.player_maps if row.split == "train"]
        for label, (raw_name, unique_name) in pairs.items():
            rows: list[MirRoleFeatureStats] = []
            for role in CIR_ROLES:
                role_rows = [row for row in train if row.role == role]
                raw_vals = [
                    value
                    for row in role_rows
                    if (value := row.raw_features.get(raw_name)) is not None
                ]
                unique_vals = [
                    value
                    for row in role_rows
                    if (value := row.raw_features.get(unique_name)) is not None
                ]
                raw_summary = distribution_summary(raw_vals)
                unique_summary = distribution_summary(unique_vals)
                rows.append(
                    MirRoleFeatureStats(
                        role=role,
                        mean_raw=raw_summary["mean"],
                        median_raw=raw_summary["median"],
                        mean_unique=unique_summary["mean"],
                        median_unique=unique_summary["median"],
                        sample_size=len(role_rows),
                    )
                )
            report[label] = rows
        return report

    def _baselines(
        self,
        bundle: MirEvaluationBundle,
        combat: MirSubsetResult,
        selected: MirSubsetResult,
    ) -> list[MirBaselineComparison]:
        rows = [
            MirBaselineComparison(
                name="combat_only_cir_candidate",
                validation_metrics=combat.validation_metrics,
                test_metrics=combat.test_metrics,
                role_median_gap=combat.role_bias_metrics.max_role_median_gap,
                source="live MIR combat_only subset",
            ),
            MirBaselineComparison(
                name="selected_mir",
                validation_metrics=selected.validation_metrics,
                test_metrics=selected.test_metrics,
                role_median_gap=selected.role_bias_metrics.max_role_median_gap,
                source=selected.name,
            ),
        ]
        stats_by_map: dict[UUID, list[PlayerMapStats]] = defaultdict(list)
        for row in bundle.player_maps:
            stats_by_map[row.stats.match_map_id].append(row.stats)
        for metric_name, getter in (
            ("team_average_kd", _kd),
            ("team_average_acs", _acs),
            ("team_average_vlr_rating", _vlr),
        ):
            rows.append(_univariate_baseline(metric_name, bundle.team_maps, stats_by_map, getter))
        cir_real = self._session.scalar(
            select(MetricVersion).where(
                MetricVersion.name == "CIR",
                MetricVersion.version == CIR_REAL_EXPERIMENT_VERSION,
            )
        )
        if cir_real is not None:
            stored = cir_real.regularization_parameters.get("validation_metrics")
            val = SplitMetrics()
            test = SplitMetrics()
            if isinstance(stored, dict):
                val = SplitMetrics(
                    rmse=_as_float(stored.get("validation_rmse")),
                    r2=_as_float(stored.get("validation_r2")),
                )
                test = SplitMetrics(
                    rmse=_as_float(stored.get("test_rmse")),
                    r2=_as_float(stored.get("test_r2")),
                )
            rows.append(
                MirBaselineComparison(
                    name="CIR_v0.1-real-2026",
                    validation_metrics=val,
                    test_metrics=test,
                    source="stored MetricVersion (not retrained)",
                )
            )
        return rows

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
            raise RuntimeError(f"{CIR_REAL_EXPERIMENT_VERSION} changed during the MIR experiment")


def _t1_t2_table(by_name: dict[str, MirSubsetResult]) -> dict[str, dict[str, float | None]]:
    table: dict[str, dict[str, float | None]] = {}
    for name in (
        "combat_plus_apr_unique",
        "combat_plus_kast_unique",
        "combat_plus_of_unique",
        "combat_plus_oe_unique",
        "combat_plus_support_unique",
        "combat_plus_opening_unique",
    ):
        item = by_name.get(name)
        if item is None:
            continue
        table[name] = {}
        for feature, coef in item.coefficients.items():
            if feature in COMBAT_FEATURES:
                continue
            table[name][f"{feature}_global"] = coef
            table[name][f"{feature}_T1"] = item.t1_extra_coefficients.get(feature)
            table[name][f"{feature}_T2"] = item.t2_extra_coefficients.get(feature)
    return table


def _marginal_examples(
    bundle: MirEvaluationBundle,
    subset: MirSubsetResult,
) -> list[MirMarginalExample]:
    features = tuple(subset.features)
    coefficients = subset.coefficients
    grouped: dict[UUID, list[MirPlayerMap]] = defaultdict(list)
    for row in bundle.player_maps:
        grouped[row.stats.match_map_id].append(row)
    examples: list[MirMarginalExample] = []
    for team_map in bundle.team_maps:
        if team_map.split != "validation":
            continue
        rows = grouped.get(team_map.match_map_id, [])
        if len(rows) < 2:
            continue
        match = rows[0].stats.match_map.match
        if match.team_a_id is None or match.team_b_id is None:
            continue
        team_a = [row for row in rows if row.stats.team_id == match.team_a_id]
        team_b = [row for row in rows if row.stats.team_id == match.team_b_id]
        full_delta = build_team_delta_vector(
            [row.standardized_features for row in team_a],
            [row.standardized_features for row in team_b],
            feature_names=features,
        )
        prediction_full = sum(
            coefficients.get(name, 0.0) * full_delta.get(name, 0.0) for name in features
        )
        for row in rows:
            if row.stats.team_id == match.team_a_id:
                without_a = [item for item in team_a if item.stats.player_id != row.stats.player_id]
                without_b = team_b
            else:
                without_a = team_a
                without_b = [item for item in team_b if item.stats.player_id != row.stats.player_id]
            if not without_a or not without_b:
                continue
            delta = build_team_delta_vector(
                [item.standardized_features for item in without_a],
                [item.standardized_features for item in without_b],
                feature_names=features,
            )
            prediction_without = sum(
                coefficients.get(name, 0.0) * delta.get(name, 0.0) for name in features
            )
            examples.append(
                MirMarginalExample(
                    player_handle=row.stats.player.handle if row.stats.player is not None else None,
                    role=row.role,
                    map_name=row.stats.match_map.map_name,
                    split=row.split,
                    prediction_full=prediction_full,
                    prediction_without_player=prediction_without,
                    marginal_contribution=prediction_full - prediction_without,
                )
            )
    examples.sort(key=lambda item: abs(item.marginal_contribution or 0.0), reverse=True)
    return examples[:6]


def _univariate_baseline(
    name: str,
    team_maps: list[_TeamMapPrepared],
    stats_by_map: dict[UUID, list[PlayerMapStats]],
    getter: Callable[[PlayerMapStats], float],
) -> MirBaselineComparison:
    train_x: list[float] = []
    train_y: list[float] = []
    val_x: list[float] = []
    val_y: list[float] = []
    test_x: list[float] = []
    test_y: list[float] = []
    for team_map in team_maps:
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
        delta = sum(getter(item) for item in team_a) / len(team_a) - sum(
            getter(item) for item in team_b
        ) / len(team_b)
        if team_map.split == "train":
            train_x.append(delta)
            train_y.append(team_map.outcome_residual)
        elif team_map.split == "validation":
            val_x.append(delta)
            val_y.append(team_map.outcome_residual)
        else:
            test_x.append(delta)
            test_y.append(team_map.outcome_residual)
    slope, intercept = _fit_univariate(train_x, train_y)

    def metrics(xs: list[float], ys: list[float]) -> SplitMetrics:
        if not xs:
            return SplitMetrics()
        preds = np.array([slope * x + intercept for x in xs], dtype=np.float64)
        targets = np.array(ys, dtype=np.float64)
        return SplitMetrics(
            rmse=rmse(targets, preds),
            mae=mae(targets, preds),
            r2=r2_score(targets, preds),
            spearman=spearman_correlation(targets, preds),
        )

    return MirBaselineComparison(
        name=name,
        validation_metrics=metrics(val_x, val_y),
        test_metrics=metrics(test_x, test_y),
        source="univariate on identical MIR team-maps",
    )


def _fit_univariate(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
    if not x_values or not y_values:
        return 0.0, 0.0
    x = np.array(x_values, dtype=np.float64)
    y = np.array(y_values, dtype=np.float64)
    if len(x) == 1 or np.allclose(x, x[0]):
        return 0.0, float(np.mean(y))
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def _kd(stats: PlayerMapStats) -> float:
    if stats.deaths == 0:
        return float(stats.kills)
    return stats.kills / stats.deaths


def _acs(stats: PlayerMapStats) -> float:
    return stats.acs or 0.0


def _vlr(stats: PlayerMapStats) -> float:
    return stats.vlr_rating or 0.0


def _as_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
