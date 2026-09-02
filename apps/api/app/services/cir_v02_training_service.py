from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics.cir.combat import combat_factor_metadata
from app.metrics.cir.config import (
    CIR_NAME,
    CIR_V02_FEATURE_NAMES,
    CIR_V02_VERSION,
    CONTEXT_DIMENSIONS,
    ELIGIBLE_MAP_DEFINITION,
    ESTABLISHED_ROUNDS,
    KPR_FEATURE,
    LAMBDA,
    NEGATIVE_DPR_FEATURE,
    PUBLIC_INTERPRETATION,
    SHRINKAGE_K,
    TAU,
    MetricVersionStatus,
    SampleStatus,
    production_context_spec,
)
from app.metrics.cir.context import (
    context_expectation_table,
    expected_rates,
    observed_dpr,
    observed_kpr,
    serialize_combat_registry,
)
from app.metrics.cir.sanity import regression_failures, sanity_failures
from app.metrics.cir.scoring import (
    CirPlayerScore,
    aggregate_player_scores,
    kpr_residual,
    negative_dpr_residual,
    reference_from_train_maps,
    score_observation,
)
from app.metrics.cir_combat_factor_config import EQUAL_WEIGHT
from app.metrics.cir_standardization import fit_standardization
from app.metrics.context_v2 import build_context_v2_registry
from app.metrics.context_v2_config import CONTEXT_MODE_V2
from app.models import MetricVersion
from app.schemas.cir_v02 import CirTrainingGateResult, CirV02TrainingResult
from app.services.cir_combat_factor_support import apply_parameterization, combat_coefficient
from app.services.cir_final_validation_support import (
    match_id_for,
    match_ids_for_maps,
    resample_match_ids,
    split_ids,
)
from app.services.cir_snapshot_service import CirSnapshotService
from app.services.cir_training_service import CIRTrainingService
from app.services.context_baseline_service import observation_from_player_map_stats
from app.services.map_completeness import summarize_map_completeness
from app.services.scale_event_set import SCALE_EVENT_IDS
from app.services.stats_engine_service import StatsEngineService
from app.services.team_rating_service import TeamRatingService


class CirVersionExistsError(RuntimeError):
    pass


class CirV02TrainingService:
    """Fit and persist frozen CIR v0.2. Scoring != retraining after this point."""

    def __init__(
        self,
        session: Session,
        *,
        stats_service: StatsEngineService | None = None,
        team_rating_service: TeamRatingService | None = None,
        require_complete_maps: bool = True,
        bootstrap_iterations: int = 0,
        persist_version: str = CIR_V02_VERSION,
        allow_production: bool = True,
        events_used: list[int] | None = None,
    ) -> None:
        self._session = session
        self._stats_service = stats_service or StatsEngineService(session)
        self._team_rating_service = team_rating_service or TeamRatingService(session)
        self._require_complete_maps = require_complete_maps
        self._bootstrap_iterations = bootstrap_iterations
        self._persist_version = persist_version
        self._allow_production = allow_production
        self._events_used = list(events_used or SCALE_EVENT_IDS)
        self._snapshot_service = CirSnapshotService(
            session,
            stats_service=self._stats_service,
            require_complete_maps=require_complete_maps,
        )

    def train(
        self,
        *,
        dry_run: bool = False,
        force_new_version: bool = False,
    ) -> CirV02TrainingResult:
        existing = self._existing_version()
        if existing is not None and not dry_run and not force_new_version:
            raise CirVersionExistsError(
                f"{CIR_NAME} {self._persist_version} already exists "
                f"({existing.id}). Pass force_new_version to replace only this version."
            )
        if existing is not None and force_new_version and not dry_run:
            if existing.version != self._persist_version or existing.name != CIR_NAME:
                raise CirVersionExistsError(
                    "Refusing to delete a MetricVersion that is not CIR v0.2"
                )
            self._session.delete(existing)
            self._session.flush()

        spec = production_context_spec()
        trainer = CIRTrainingService(
            self._session,
            stats_service=self._stats_service,
            team_rating_service=self._team_rating_service,
            shrinkage_k=SHRINKAGE_K,
            require_complete_maps=self._require_complete_maps,
            persist_version=self._persist_version,
            events_used=self._events_used,
            context_mode=CONTEXT_MODE_V2,
            context_spec=spec,
            persist=False,
            rebuild_ratings=True,
            feature_names=CIR_V02_FEATURE_NAMES,
        )
        _result, bundle = trainer.fit_cir_v01()

        train_ids, _val_ids, _test_ids = split_ids(bundle)
        train_stats = [row.stats for row in bundle.prepared_maps if row.split == "train"]
        train_observations = [observation_from_player_map_stats(row) for row in train_stats]
        registry = build_context_v2_registry(train_observations)

        train_residual_rows: list[dict[str, float | None]] = []
        for stats in train_stats:
            observation = observation_from_player_map_stats(stats)
            kpr = observed_kpr(observation.kills, observation.rounds)
            dpr = observed_dpr(observation.deaths, observation.rounds)
            expected_kpr, expected_dpr = expected_rates(registry, observation, tau=TAU)
            if kpr is None or dpr is None or expected_kpr is None or expected_dpr is None:
                continue
            train_residual_rows.append(
                {
                    KPR_FEATURE: kpr_residual(kpr, expected_kpr),
                    NEGATIVE_DPR_FEATURE: negative_dpr_residual(dpr, expected_dpr),
                }
            )
        standardization = fit_standardization(
            train_residual_rows, feature_names=CIR_V02_FEATURE_NAMES
        )

        map_scores = []
        for row in bundle.prepared_maps:
            stats = row.stats
            observation = observation_from_player_map_stats(stats)
            event = stats.match_map.match.event
            scored = score_observation(
                observation,
                registry=registry,
                standardization=standardization,
                player_id=stats.player_id,
                handle=stats.player.handle if stats.player is not None else None,
                match_map_id=stats.match_map_id,
                event_id=event.id if event is not None else None,
                vlr_event_id=event.vlr_event_id if event is not None else None,
                agent_name=stats.agent.name if stats.agent is not None else None,
                tau=TAU,
            )
            if scored is not None:
                map_scores.append(scored)

        train_player_ids = {
            row.stats.player_id for row in bundle.prepared_maps if row.split == "train"
        }
        reference_mean, reference_population = reference_from_train_maps(
            map_scores, train_player_ids, shrinkage_k=SHRINKAGE_K
        )
        players = aggregate_player_scores(
            map_scores,
            reference_mean=reference_mean,
            reference_population=reference_population,
            shrinkage_k=SHRINKAGE_K,
        )

        applied = apply_parameterization(bundle, EQUAL_WEIGHT, SHRINKAGE_K)
        val_rmse = applied.val_metrics.rmse
        test_rmse = applied.test_metrics.rmse
        role_gap = applied.role_gap
        sign_flips = self._bootstrap_sign_flips(bundle)

        context_rows = context_expectation_table(registry, tau=TAU)
        sanity = sanity_failures(
            players=players,
            standardization=standardization,
            reference_population=reference_population,
            context_rows=context_rows,
        )
        regression = regression_failures(
            val_rmse=val_rmse,
            test_rmse=test_rmse,
            role_gap=role_gap,
            bootstrap_sign_flips=sign_flips,
            team_map_count=len(bundle.team_maps),
        )
        gates_passed = not sanity and not regression
        if gates_passed and self._allow_production:
            status = MetricVersionStatus.PRODUCTION.value
        else:
            status = MetricVersionStatus.VALIDATED.value

        completeness = summarize_map_completeness(self._session)
        training_start = _min_date(train_stats)
        training_end = _max_date(train_stats)
        metric_version_id: str | None = None
        if not dry_run:
            metric_version = self._persist_metric_version(
                status=status if gates_passed else MetricVersionStatus.VALIDATED.value,
                training_start=training_start,
                training_end=training_end,
                standardization=standardization,
                registry_payload=serialize_combat_registry(registry),
                context_rows=context_rows,
                reference_mean=reference_mean,
                reference_population=reference_population,
                val_rmse=val_rmse,
                test_rmse=test_rmse,
                role_gap=role_gap,
                bootstrap_sign_flips=sign_flips,
                dataset_summary={
                    "maps_total": completeness.maps_played,
                    "maps_used": len({row.stats.match_map_id for row in bundle.prepared_maps}),
                    "maps_incomplete": completeness.maps_incomplete,
                    "maps_empty": completeness.maps_empty,
                    "train_maps": len(train_ids),
                    "player_snapshots": len(players),
                    "events_used": list(self._events_used),
                },
            )
            self._snapshot_service.upsert_snapshots(metric_version=metric_version, players=players)
            if gates_passed and self._allow_production:
                metric_version.status = MetricVersionStatus.PRODUCTION.value
                self._session.flush()
            metric_version_id = str(metric_version.id)
            status = metric_version.status

        return CirV02TrainingResult(
            metric_version_id=metric_version_id,
            name=CIR_NAME,
            version=self._persist_version,
            status=status if not dry_run else MetricVersionStatus.RESEARCH.value,
            dry_run=dry_run,
            maps_used=len({row.match_map_id for row in map_scores}),
            player_snapshots=len(players),
            reference_size=len(reference_population),
            reference_mean=reference_mean,
            shrinkage_k=SHRINKAGE_K,
            mu_kpr=standardization.means.get(KPR_FEATURE),
            sigma_kpr=standardization.stds.get(KPR_FEATURE),
            mu_negative_dpr=standardization.means.get(NEGATIVE_DPR_FEATURE),
            sigma_negative_dpr=standardization.stds.get(NEGATIVE_DPR_FEATURE),
            val_rmse=val_rmse,
            test_rmse=test_rmse,
            role_gap=role_gap,
            bootstrap_sign_flips=sign_flips,
            sample_counts=_sample_counts(players),
            gates=CirTrainingGateResult(
                passed=gates_passed,
                failures=sanity,
                regression_failures=regression,
            ),
            context_expectations=context_rows,
            top_established=_top_established(players),
            cir_summary=_cir_summary(players),
        )

    def _existing_version(self) -> MetricVersion | None:
        return self._session.scalar(
            select(MetricVersion).where(
                MetricVersion.name == CIR_NAME,
                MetricVersion.version == self._persist_version,
            )
        )

    def _bootstrap_sign_flips(self, bundle: Any) -> int | None:
        if self._bootstrap_iterations <= 0:
            return None
        train_ids, _, _ = split_ids(bundle)
        match_ids = match_ids_for_maps(bundle, train_ids)
        if len(match_ids) < 2:
            return 0
        rng = np.random.default_rng(42)
        flips = 0
        for _ in range(self._bootstrap_iterations):
            sampled = set(resample_match_ids(match_ids, rng))
            ridge_maps = [
                row
                for row in bundle.team_maps
                if row.split == "train" and match_id_for(bundle, row.match_map_id) in sampled
            ]
            if len(ridge_maps) < 2:
                continue
            applied = apply_parameterization(
                bundle, EQUAL_WEIGHT, SHRINKAGE_K, ridge_maps=ridge_maps
            )
            coef = combat_coefficient(EQUAL_WEIGHT, applied.coefficients)
            if coef is not None and coef < 0:
                flips += 1
        return flips

    def _persist_metric_version(
        self,
        *,
        status: str,
        training_start: Any,
        training_end: Any,
        standardization: Any,
        registry_payload: dict[str, Any],
        context_rows: list[dict[str, Any]],
        reference_mean: float,
        reference_population: list[float],
        val_rmse: float | None,
        test_rmse: float | None,
        role_gap: float | None,
        bootstrap_sign_flips: int | None,
        dataset_summary: dict[str, Any],
    ) -> MetricVersion:
        std_dict = standardization.to_dict()
        metric_version = MetricVersion(
            name=CIR_NAME,
            version=self._persist_version,
            status=status,
            training_start=training_start,
            training_end=training_end,
            feature_names=list(CIR_V02_FEATURE_NAMES),
            standardization_parameters={
                **std_dict,
                "mu_kpr": standardization.means.get(KPR_FEATURE),
                "sigma_kpr": standardization.stds.get(KPR_FEATURE),
                "mu_negative_dpr": standardization.means.get(NEGATIVE_DPR_FEATURE),
                "sigma_negative_dpr": standardization.stds.get(NEGATIVE_DPR_FEATURE),
            },
            model_coefficients={
                **combat_factor_metadata(),
                "weights": {
                    KPR_FEATURE: 0.5,
                    NEGATIVE_DPR_FEATURE: 0.5,
                },
                "intercept": 0.0,
                "interpretation": PUBLIC_INTERPRETATION,
            },
            regularization_parameters={
                "lambda": LAMBDA,
                "tau": TAU,
                "context_type": "context_v2",
                "context_dimensions": list(CONTEXT_DIMENSIONS),
                "events_used": list(self._events_used),
                "eligible_map_definition": ELIGIBLE_MAP_DEFINITION,
                "context_registry": registry_payload,
                "context_expectations": context_rows,
                "ranking_policy": {
                    "default_sample_status": SampleStatus.ESTABLISHED.value,
                    "established_rounds": ESTABLISHED_ROUNDS,
                    "sort": ["cir_desc", "rounds_desc", "handle_asc"],
                },
                "validation_metrics": {
                    "validation_rmse": val_rmse,
                    "test_rmse": test_rmse,
                    "role_median_gap": role_gap,
                    "bootstrap_sign_flips": bootstrap_sign_flips,
                },
                "robustness_metrics": {
                    "bootstrap_sign_flips": bootstrap_sign_flips,
                    "role_median_gap": role_gap,
                },
                "dataset_summary": dataset_summary,
                "scoring_is_not_retraining": True,
            },
            shrinkage_parameters={"k": SHRINKAGE_K, "reference_mean": reference_mean},
            reference_population={"shrunk_raw_cir_values": reference_population},
        )
        self._session.add(metric_version)
        self._session.flush()
        return metric_version


def _sample_counts(players: list[CirPlayerScore]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for player in players:
        counts[player.sample_status] += 1
    return dict(counts)


def _top_established(players: list[CirPlayerScore], limit: int = 20) -> list[dict[str, object]]:
    established = [
        player for player in players if player.sample_status == SampleStatus.ESTABLISHED.value
    ]
    established.sort(
        key=lambda player: (-(player.cir or 0.0), -player.rounds, (player.handle or "").lower())
    )
    return [
        {
            "handle": player.handle,
            "cir": player.cir,
            "rounds": player.rounds,
            "reliability": player.reliability,
            "role": player.role,
        }
        for player in established[:limit]
    ]


def _cir_summary(players: list[CirPlayerScore]) -> dict[str, float | None]:
    values = [player.cir for player in players]
    if not values:
        return {"min": None, "max": None, "mean": None, "p50": None}
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2.0
    return {
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "p50": median,
    }


def _min_date(stats: list[Any]) -> Any:
    dates = [
        row.match_map.match.played_at.date()
        for row in stats
        if row.match_map.match.played_at is not None
    ]
    return min(dates) if dates else None


def _max_date(stats: list[Any]) -> Any:
    dates = [
        row.match_map.match.played_at.date()
        for row in stats
        if row.match_map.match.played_at is not None
    ]
    return max(dates) if dates else None
