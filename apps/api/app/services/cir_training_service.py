from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.metrics.adr_regression import train_adr_regression
from app.metrics.bayesian_clutch import estimate_clutch_prior
from app.metrics.cir_features import extract_cir_input_features, extract_non_context_features
from app.metrics.cir_round_diff import (
    actual_round_diff,
    expected_round_diff_team_a,
    outcome_residual,
)
from app.metrics.cir_scoring import (
    CIRModelCoefficients,
    apply_shrinkage,
    build_team_delta_vector,
    compute_component_contributions,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_standardization import (
    StandardizationParams,
    fit_standardization,
    standardize_features,
)
from app.metrics.cir_v01 import (
    CIR_METRIC_NAME,
    CIR_V01_FEATURE_NAMES,
    CIR_V01_VERSION,
    DEFAULT_RIDGE_ALPHAS,
    DEFAULT_SHRINKAGE_K,
    TRAIN_FRACTION,
    VALIDATION_FRACTION,
)
from app.metrics.context_baselines import (
    ContextObservation,
    adjust_context_observation,
    build_baseline_registry,
)
from app.metrics.derived import safe_ratio
from app.metrics.feature_engine import FeatureEngine
from app.metrics.ridge_regression import (
    fit_ridge,
    predict_ridge,
    r2_score,
    rmse,
    select_ridge_alpha,
)
from app.metrics.stats_engine import player_map_stats_to_raw
from app.models import MetricVersion, PlayerMapStats, PlayerMetricSnapshot
from app.schemas.cir import (
    CIRBaselineEvaluation,
    CIRPlayerScoreExample,
    CIRSplitCounts,
    CIRTrainingEvaluation,
    CIRTrainingResult,
)
from app.services.clutch_coverage import (
    CLUTCH_FEATURE_NAME,
    DEFAULT_MIN_CLUTCH_COVERAGE,
    ClutchCoverage,
    measure_clutch_coverage,
)
from app.services.context_baseline_service import observation_from_player_map_stats
from app.services.map_completeness import (
    MapCompletenessSummary,
    filter_stats_to_complete_maps,
    summarize_map_completeness,
)
from app.services.stats_engine_service import StatsEngineService
from app.services.team_rating_service import TeamRatingService


@dataclass
class _CirDatasetSelection:
    stats: list[PlayerMapStats]
    completeness: MapCompletenessSummary
    clutch: ClutchCoverage
    feature_names: tuple[str, ...]


@dataclass
class _PlayerMapPrepared:
    stats: PlayerMapStats
    split: str
    raw_features: dict[str, float | None]
    standardized_features: dict[str, float] = field(default_factory=dict)
    baseline_level: str | None = None
    non_context_features: dict[str, float | None] = field(default_factory=dict)


@dataclass
class CIREvaluationBundle:
    prepared_maps: list[_PlayerMapPrepared]
    team_maps: list[_TeamMapPrepared]
    standardization: StandardizationParams
    full_coefficients: CIRModelCoefficients
    ridge_alpha: float
    reference_mean: float
    reference_population: list[float]
    shrinkage_k: float


@dataclass
class _TeamMapPrepared:
    match_map_id: UUID
    split: str
    outcome_residual: float
    deltas: dict[str, float]


@dataclass
class _PlayerAggregate:
    player_id: UUID
    handle: str | None
    raw_cir_values: list[tuple[float, int]] = field(default_factory=list)
    combat_values: list[tuple[float, int]] = field(default_factory=list)
    opening_values: list[tuple[float, int]] = field(default_factory=list)
    team_values: list[tuple[float, int]] = field(default_factory=list)
    clutch_values: list[tuple[float, int]] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None


class CIRTrainingService:
    """Train and persist CIR v0.1."""

    def __init__(
        self,
        session: Session,
        *,
        stats_service: StatsEngineService | None = None,
        team_rating_service: TeamRatingService | None = None,
        shrinkage_k: float = DEFAULT_SHRINKAGE_K,
        require_complete_maps: bool = True,
        min_clutch_coverage: float = DEFAULT_MIN_CLUTCH_COVERAGE,
    ) -> None:
        self._session = session
        self._stats_service = stats_service or StatsEngineService(session)
        self._team_rating_service = team_rating_service or TeamRatingService(session)
        self._shrinkage_k = shrinkage_k
        self._require_complete_maps = require_complete_maps
        self._min_clutch_coverage = min_clutch_coverage

    def _select_dataset(self) -> _CirDatasetSelection:
        all_stats = self._stats_service.load_player_map_stats(None)
        completeness = summarize_map_completeness(self._session)
        stats = (
            filter_stats_to_complete_maps(all_stats, completeness.complete_map_ids)
            if self._require_complete_maps
            else all_stats
        )
        if not stats:
            raise ValueError("No player map stats available for CIR training")
        clutch = measure_clutch_coverage(stats, min_coverage=self._min_clutch_coverage)
        feature_names = CIR_V01_FEATURE_NAMES
        if not clutch.clutch_feature_enabled:
            feature_names = tuple(
                name for name in CIR_V01_FEATURE_NAMES if name != CLUTCH_FEATURE_NAME
            )
        return _CirDatasetSelection(
            stats=stats,
            completeness=completeness,
            clutch=clutch,
            feature_names=feature_names,
        )

    def train_cir_v01(self) -> CIRTrainingResult:
        self._team_rating_service.rebuild_team_ratings()
        dataset = self._select_dataset()
        all_stats = dataset.stats

        map_ids = _chronological_map_ids(all_stats)
        train_ids, val_ids, test_ids = _chronological_split(map_ids)
        split_for_map = _split_lookup(train_ids, val_ids, test_ids)

        train_stats = [row for row in all_stats if row.match_map_id in train_ids]
        train_observations = [observation_from_player_map_stats(row) for row in train_stats]
        feature_engine = self._build_feature_engine(train_stats)

        prepared_maps = self._prepare_player_maps(
            all_stats,
            split_for_map=split_for_map,
            train_observations=train_observations,
            feature_engine=feature_engine,
        )

        train_raw = [row.raw_features for row in prepared_maps if row.split == "train"]
        standardization = fit_standardization(train_raw)
        for row in prepared_maps:
            row.standardized_features = standardize_features(row.raw_features, standardization)

        team_maps = self._build_team_maps(prepared_maps, split_for_map)
        train_team_maps = [row for row in team_maps if row.split == "train"]
        val_team_maps = [row for row in team_maps if row.split == "validation"]
        test_team_maps = [row for row in team_maps if row.split == "test"]

        train_design, train_targets = _design_matrix(
            train_team_maps,
            feature_names=dataset.feature_names,
        )
        val_design, val_targets = _design_matrix(
            val_team_maps,
            feature_names=dataset.feature_names,
        )
        test_design, test_targets = _design_matrix(
            test_team_maps,
            feature_names=dataset.feature_names,
        )

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
            coefficients=_coefficients_for_features(dataset.feature_names, weights),
        )

        evaluation = self._evaluate_model(
            coefficients=coefficients,
            train_design=train_design,
            train_targets=train_targets,
            val_design=val_design,
            val_targets=val_targets,
            test_design=test_design,
            test_targets=test_targets,
            prepared_maps=prepared_maps,
            team_maps=team_maps,
            feature_names=dataset.feature_names,
            baseline_stats=all_stats,
        )

        train_players = self._aggregate_players(
            prepared_maps,
            split="train",
            coefficients=coefficients,
        )
        reference_mean = _reference_mean(train_players)
        reference_population = [
            apply_shrinkage(
                round_weighted_mean(player.raw_cir_values) or 0.0,
                sum(weight for _, weight in player.raw_cir_values),
                reference_mean,
                self._shrinkage_k,
            )
            for player in train_players
            if player.raw_cir_values
        ]

        training_start, training_end = _training_period(train_stats)
        metric_version = self._persist_metric_version(
            training_start=training_start,
            training_end=training_end,
            standardization=standardization,
            coefficients=coefficients,
            ridge_alpha=ridge_alpha,
            reference_mean=reference_mean,
            reference_population=reference_population,
        )

        all_players = self._aggregate_players(prepared_maps, split=None, coefficients=coefficients)
        self._persist_player_snapshots(
            metric_version=metric_version,
            players=all_players,
            reference_mean=reference_mean,
            reference_population=reference_population,
        )

        example_players = self._aggregate_players(
            prepared_maps,
            split="test",
            coefficients=coefficients,
        )
        example_scores = self._example_scores(
            players=example_players,
            reference_mean=reference_mean,
            reference_population=reference_population,
        )

        train_player_ids = {row.stats.player_id for row in prepared_maps if row.split == "train"}
        val_player_ids = {row.stats.player_id for row in prepared_maps if row.split == "validation"}
        test_player_ids = {row.stats.player_id for row in prepared_maps if row.split == "test"}

        return CIRTrainingResult(
            metric_version_id=str(metric_version.id),
            name=CIR_METRIC_NAME,
            version=CIR_V01_VERSION,
            split_counts=CIRSplitCounts(
                train_maps=len(train_ids),
                validation_maps=len(val_ids),
                test_maps=len(test_ids),
                train_players=len(train_player_ids),
                validation_players=len(val_player_ids),
                test_players=len(test_player_ids),
            ),
            ridge_alpha=ridge_alpha,
            intercept=intercept,
            coefficients=coefficients.coefficients,
            shrinkage_k=self._shrinkage_k,
            reference_mean=reference_mean,
            evaluation=evaluation,
            example_scores=example_scores,
            maps_total=dataset.completeness.maps_played,
            maps_used_for_cir=dataset.completeness.maps_used_for_cir
            if self._require_complete_maps
            else len(map_ids),
            maps_excluded_from_cir=(
                dataset.completeness.maps_excluded_from_cir if self._require_complete_maps else 0
            ),
            maps_incomplete=dataset.completeness.maps_incomplete,
            maps_empty=dataset.completeness.maps_empty,
            clutch_available_rows=dataset.clutch.clutch_available_rows,
            clutch_missing_rows=dataset.clutch.clutch_missing_rows,
            clutch_coverage_pct=dataset.clutch.clutch_coverage_pct,
            clutch_feature_enabled=dataset.clutch.clutch_feature_enabled,
        )

    def prepare_evaluation_bundle(self) -> CIREvaluationBundle:
        self._team_rating_service.rebuild_team_ratings()
        dataset = self._select_dataset()
        all_stats = dataset.stats

        map_ids = _chronological_map_ids(all_stats)
        train_ids, val_ids, test_ids = _chronological_split(map_ids)
        split_for_map = _split_lookup(train_ids, val_ids, test_ids)

        train_stats = [row for row in all_stats if row.match_map_id in train_ids]
        train_observations = [observation_from_player_map_stats(row) for row in train_stats]
        feature_engine = self._build_feature_engine(train_stats)

        prepared_maps = self._prepare_player_maps(
            all_stats,
            split_for_map=split_for_map,
            train_observations=train_observations,
            feature_engine=feature_engine,
        )

        train_raw = [row.raw_features for row in prepared_maps if row.split == "train"]
        standardization = fit_standardization(train_raw)
        for row in prepared_maps:
            row.standardized_features = standardize_features(row.raw_features, standardization)

        team_maps = self._build_team_maps(prepared_maps, split_for_map)
        train_team_maps = [row for row in team_maps if row.split == "train"]
        val_team_maps = [row for row in team_maps if row.split == "validation"]

        train_design, train_targets = _design_matrix(
            train_team_maps,
            feature_names=dataset.feature_names,
        )
        val_design, val_targets = _design_matrix(
            val_team_maps,
            feature_names=dataset.feature_names,
        )

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
            coefficients=_coefficients_for_features(dataset.feature_names, weights),
        )

        train_players = self._aggregate_players(
            prepared_maps,
            split="train",
            coefficients=coefficients,
        )
        reference_mean = _reference_mean(train_players)
        reference_population = [
            apply_shrinkage(
                round_weighted_mean(player.raw_cir_values) or 0.0,
                sum(weight for _, weight in player.raw_cir_values),
                reference_mean,
                self._shrinkage_k,
            )
            for player in train_players
            if player.raw_cir_values
        ]

        return CIREvaluationBundle(
            prepared_maps=prepared_maps,
            team_maps=team_maps,
            standardization=standardization,
            full_coefficients=coefficients,
            ridge_alpha=ridge_alpha,
            reference_mean=reference_mean,
            reference_population=reference_population,
            shrinkage_k=self._shrinkage_k,
        )

    def _build_feature_engine(self, train_stats: list[PlayerMapStats]) -> FeatureEngine:
        adr_observations: list[tuple[float, float]] = []
        clutch_observations: list[tuple[int, int]] = []
        for row in train_stats:
            raw = player_map_stats_to_raw(row)
            if raw.rounds > 0 and raw.adr is not None:
                kpr = safe_ratio(raw.kills, raw.rounds)
                if kpr is not None:
                    adr_observations.append((kpr, raw.adr))
            if raw.clutch_attempts is not None and raw.clutch_attempts > 0:
                clutch_observations.append((raw.clutch_wins or 0, raw.clutch_attempts))
        return FeatureEngine(
            adr_model=train_adr_regression(adr_observations),
            clutch_prior=estimate_clutch_prior(clutch_observations),
        )

    def _prepare_player_maps(
        self,
        all_stats: list[PlayerMapStats],
        *,
        split_for_map: dict[UUID, str],
        train_observations: list[ContextObservation],
        feature_engine: FeatureEngine,
    ) -> list[_PlayerMapPrepared]:
        from app.metrics.context_baselines import BaselineThresholds

        prepared: list[_PlayerMapPrepared] = []
        thresholds = BaselineThresholds(
            agent_map_tier_min_rounds=1,
            role_map_tier_min_rounds=1,
            role_tier_min_rounds=1,
            tier_min_rounds=1,
        )

        for stats in all_stats:
            observation = observation_from_player_map_stats(stats)
            reference = [
                item
                for item in train_observations
                if item.observation_id != observation.observation_id
                and (
                    observation.played_at is None
                    or item.played_at is None
                    or item.played_at <= observation.played_at
                )
            ]
            registry = build_baseline_registry(reference)
            residual_adr = feature_engine.from_player_map_stats(stats).residual_adr
            adjusted = adjust_context_observation(
                observation,
                residual_adr=residual_adr,
                registry=registry,
                thresholds=thresholds,
            )
            prepared.append(
                _PlayerMapPrepared(
                    stats=stats,
                    split=split_for_map[stats.match_map_id],
                    raw_features=extract_cir_input_features(adjusted),
                    baseline_level=adjusted.baseline_level,
                    non_context_features=extract_non_context_features(stats),
                )
            )
        return prepared

    def _build_team_maps(
        self,
        prepared_maps: list[_PlayerMapPrepared],
        split_for_map: dict[UUID, str],
    ) -> list[_TeamMapPrepared]:
        grouped: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
        for row in prepared_maps:
            grouped[row.stats.match_map_id].append(row)

        team_maps: list[_TeamMapPrepared] = []
        for match_map_id, rows in grouped.items():
            match_map = rows[0].stats.match_map
            match = match_map.match
            if match.team_a_id is None or match.team_b_id is None:
                continue
            actual = actual_round_diff(match_map.team_a_score, match_map.team_b_score)
            if actual is None:
                continue
            rounds_played = match_map.rounds_played or (
                (match_map.team_a_score or 0) + (match_map.team_b_score or 0)
            )
            strength = self._team_rating_service.get_opponent_strength_for_match_team(
                match.id,
                match.team_a_id,
            )
            if strength.expected_team_win_probability is None:
                continue
            expected = expected_round_diff_team_a(
                strength.expected_team_win_probability,
                rounds_played,
            )
            team_a_rows = [row for row in rows if row.stats.team_id == match.team_a_id]
            team_b_rows = [row for row in rows if row.stats.team_id == match.team_b_id]
            deltas = build_team_delta_vector(
                [row.standardized_features for row in team_a_rows],
                [row.standardized_features for row in team_b_rows],
            )
            team_maps.append(
                _TeamMapPrepared(
                    match_map_id=match_map_id,
                    split=split_for_map[match_map_id],
                    outcome_residual=outcome_residual(actual, expected),
                    deltas=deltas,
                )
            )
        return team_maps

    def _evaluate_model(
        self,
        *,
        coefficients: CIRModelCoefficients,
        train_design: NDArray[np.float64],
        train_targets: NDArray[np.float64],
        val_design: NDArray[np.float64],
        val_targets: NDArray[np.float64],
        test_design: NDArray[np.float64],
        test_targets: NDArray[np.float64],
        prepared_maps: list[_PlayerMapPrepared],
        team_maps: list[_TeamMapPrepared],
        feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
        baseline_stats: list[PlayerMapStats] | None = None,
    ) -> CIRTrainingEvaluation:
        weights = np.array(
            [coefficients.coefficients[name] for name in feature_names],
            dtype=np.float64,
        )
        train_predictions = predict_ridge(train_design, coefficients.intercept, weights)
        val_predictions = (
            predict_ridge(val_design, coefficients.intercept, weights)
            if len(val_targets) > 0
            else np.array([])
        )
        test_predictions = (
            predict_ridge(test_design, coefficients.intercept, weights)
            if len(test_targets) > 0
            else np.array([])
        )

        baselines = self._baseline_evaluations(team_maps, stats=baseline_stats)

        return CIRTrainingEvaluation(
            train_rmse=rmse(train_targets, train_predictions) if len(train_targets) else None,
            train_r2=r2_score(train_targets, train_predictions),
            validation_rmse=rmse(val_targets, val_predictions) if len(val_targets) else None,
            validation_r2=r2_score(val_targets, val_predictions) if len(val_targets) else None,
            test_rmse=rmse(test_targets, test_predictions) if len(test_targets) else None,
            test_r2=r2_score(test_targets, test_predictions) if len(test_targets) else None,
            baselines=baselines,
        )

    def _baseline_evaluations(
        self,
        team_maps: list[_TeamMapPrepared],
        *,
        stats: list[PlayerMapStats] | None = None,
    ) -> list[CIRBaselineEvaluation]:
        stats_by_map: dict[UUID, list[PlayerMapStats]] = defaultdict(list)
        rows = stats if stats is not None else self._stats_service.load_player_map_stats(None)
        for row in rows:
            stats_by_map[row.match_map_id].append(row)

        baseline_data: dict[str, dict[str, list[tuple[float, float]]]] = {
            name: {"train": [], "validation": [], "test": []}
            for name in ("team_average_kd", "team_average_acs", "team_average_vlr_rating")
        }

        for team_map in team_maps:
            rows = stats_by_map.get(team_map.match_map_id, [])
            if not rows:
                continue
            match = rows[0].match_map.match
            if match.team_a_id is None or match.team_b_id is None:
                continue
            team_a = [item for item in rows if item.team_id == match.team_a_id]
            team_b = [item for item in rows if item.team_id == match.team_b_id]
            metrics = {
                "team_average_kd": _team_metric_delta(team_a, team_b, _average_kd),
                "team_average_acs": _team_metric_delta(team_a, team_b, _average_acs),
                "team_average_vlr_rating": _team_metric_delta(team_a, team_b, _average_vlr),
            }
            for name, value in metrics.items():
                baseline_data[name][team_map.split].append((value, team_map.outcome_residual))

        evaluations: list[CIRBaselineEvaluation] = []
        for name, splits in baseline_data.items():
            train_pairs = splits["train"]
            if not train_pairs:
                continue
            train_x = [pair[0] for pair in train_pairs]
            train_y = [pair[1] for pair in train_pairs]
            slope, intercept = _fit_univariate(train_x, train_y)
            eval_pairs = splits["validation"] or splits["test"]
            if not eval_pairs:
                continue
            eval_x = [pair[0] for pair in eval_pairs]
            eval_y = [pair[1] for pair in eval_pairs]
            predictions = [slope * x + intercept for x in eval_x]
            evaluations.append(
                CIRBaselineEvaluation(
                    name=name,
                    rmse=rmse(np.array(eval_y), np.array(predictions)),
                    r2=r2_score(np.array(eval_y), np.array(predictions)),
                )
            )
        return evaluations

    def _aggregate_players(
        self,
        prepared_maps: list[_PlayerMapPrepared],
        *,
        split: str | None,
        coefficients: CIRModelCoefficients,
    ) -> list[_PlayerAggregate]:
        players: dict[UUID, _PlayerAggregate] = {}
        for row in prepared_maps:
            if split is not None and row.split != split:
                continue
            stats = row.stats
            player_id = stats.player_id
            if player_id not in players:
                players[player_id] = _PlayerAggregate(
                    player_id=player_id,
                    handle=stats.player.handle,
                )
            aggregate = players[player_id]
            contributions = compute_component_contributions(
                row.standardized_features,
                coefficients,
            )
            raw_cir = compute_raw_cir(row.standardized_features, coefficients)
            rounds = stats.rounds
            aggregate.raw_cir_values.append((raw_cir, rounds))
            aggregate.combat_values.append((contributions.combat, rounds))
            aggregate.opening_values.append((contributions.opening, rounds))
            aggregate.team_values.append((contributions.team, rounds))
            aggregate.clutch_values.append((contributions.clutch, rounds))
            played_at = stats.match_map.match.played_at
            if played_at is not None:
                played_date = played_at.date()
                aggregate.period_start = (
                    played_date
                    if aggregate.period_start is None
                    else min(aggregate.period_start, played_date)
                )
                aggregate.period_end = (
                    played_date
                    if aggregate.period_end is None
                    else max(aggregate.period_end, played_date)
                )
        return list(players.values())

    def _persist_metric_version(
        self,
        *,
        training_start: date | None,
        training_end: date | None,
        standardization: StandardizationParams,
        coefficients: CIRModelCoefficients,
        ridge_alpha: float,
        reference_mean: float,
        reference_population: list[float],
    ) -> MetricVersion:
        self._session.execute(
            delete(MetricVersion).where(
                MetricVersion.name == CIR_METRIC_NAME,
                MetricVersion.version == CIR_V01_VERSION,
            )
        )
        metric_version = MetricVersion(
            name=CIR_METRIC_NAME,
            version=CIR_V01_VERSION,
            training_start=training_start,
            training_end=training_end,
            feature_names=list(CIR_V01_FEATURE_NAMES),
            standardization_parameters=standardization.to_dict(),
            model_coefficients=coefficients.to_dict(),
            regularization_parameters={"alpha": ridge_alpha},
            shrinkage_parameters={"k": self._shrinkage_k, "reference_mean": reference_mean},
            reference_population={"shrunk_raw_cir_values": reference_population},
        )
        self._session.add(metric_version)
        self._session.flush()
        return metric_version

    def _persist_player_snapshots(
        self,
        *,
        metric_version: MetricVersion,
        players: list[_PlayerAggregate],
        reference_mean: float,
        reference_population: list[float],
    ) -> None:
        self._session.execute(
            delete(PlayerMetricSnapshot).where(
                PlayerMetricSnapshot.metric_version_id == metric_version.id
            )
        )
        for player in players:
            raw_cir = round_weighted_mean(player.raw_cir_values)
            rounds = sum(weight for _, weight in player.raw_cir_values)
            maps_played = len(player.raw_cir_values)
            if raw_cir is None:
                continue
            shrunk = apply_shrinkage(raw_cir, rounds, reference_mean, self._shrinkage_k)
            cir_score = empirical_cdf(shrunk, reference_population)
            self._session.add(
                PlayerMetricSnapshot(
                    player_id=player.player_id,
                    metric_version_id=metric_version.id,
                    raw_cir=raw_cir,
                    shrunk_raw_cir=shrunk,
                    cir=cir_score,
                    combat_component=round_weighted_mean(player.combat_values),
                    opening_component=round_weighted_mean(player.opening_values),
                    team_component=round_weighted_mean(player.team_values),
                    clutch_component=round_weighted_mean(player.clutch_values),
                    rounds=rounds,
                    maps_played=maps_played,
                    period_start=player.period_start,
                    period_end=player.period_end,
                )
            )
        self._session.flush()

    def _example_scores(
        self,
        *,
        players: list[_PlayerAggregate],
        reference_mean: float,
        reference_population: list[float],
    ) -> list[CIRPlayerScoreExample]:
        examples: list[CIRPlayerScoreExample] = []
        for player in players[:5]:
            raw_cir = round_weighted_mean(player.raw_cir_values)
            rounds = sum(weight for _, weight in player.raw_cir_values)
            if raw_cir is None:
                continue
            shrunk = apply_shrinkage(raw_cir, rounds, reference_mean, self._shrinkage_k)
            examples.append(
                CIRPlayerScoreExample(
                    player_id=str(player.player_id),
                    handle=player.handle,
                    raw_cir=raw_cir,
                    shrunk_raw_cir=shrunk,
                    cir=empirical_cdf(shrunk, reference_population),
                    rounds=rounds,
                    maps_played=len(player.raw_cir_values),
                )
            )
        return examples


def _chronological_map_ids(stats: list[PlayerMapStats]) -> list[UUID]:
    grouped: dict[UUID, PlayerMapStats] = {}
    for row in stats:
        grouped[row.match_map_id] = row

    def sort_key(map_id: UUID) -> tuple[datetime, int, UUID]:
        sample = grouped[map_id]
        match = sample.match_map.match
        played_at = match.played_at or datetime.min.replace(tzinfo=UTC)
        return (played_at, match.vlr_match_id, map_id)

    return sorted(grouped.keys(), key=sort_key)


def _chronological_split(map_ids: list[UUID]) -> tuple[set[UUID], set[UUID], set[UUID]]:
    total = len(map_ids)
    if total == 0:
        return set(), set(), set()
    train_end = max(1, int(total * TRAIN_FRACTION))
    val_end = max(train_end + 1, int(total * (TRAIN_FRACTION + VALIDATION_FRACTION)))
    if total == 1:
        return {map_ids[0]}, set(), set()
    if val_end >= total:
        val_end = total - 1 if total > 1 else train_end
    train_ids = set(map_ids[:train_end])
    val_ids = set(map_ids[train_end:val_end])
    test_ids = set(map_ids[val_end:])
    return train_ids, val_ids, test_ids


def _split_lookup(
    train_ids: set[UUID],
    val_ids: set[UUID],
    test_ids: set[UUID],
) -> dict[UUID, str]:
    lookup: dict[UUID, str] = {}
    for map_id in train_ids:
        lookup[map_id] = "train"
    for map_id in val_ids:
        lookup[map_id] = "validation"
    for map_id in test_ids:
        lookup[map_id] = "test"
    return lookup


def _coefficients_for_features(
    feature_names: tuple[str, ...],
    weights: NDArray[np.float64],
) -> dict[str, float]:
    coefficients = {name: 0.0 for name in CIR_V01_FEATURE_NAMES}
    for index, name in enumerate(feature_names):
        coefficients[name] = float(weights[index])
    return coefficients


def _design_matrix(
    team_maps: list[_TeamMapPrepared],
    *,
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if not team_maps:
        return np.empty((0, len(feature_names) + 1)), np.empty(0)
    rows = [
        [1.0] + [team_map.deltas.get(name, 0.0) for name in feature_names] for team_map in team_maps
    ]
    targets = [team_map.outcome_residual for team_map in team_maps]
    return np.array(rows, dtype=np.float64), np.array(targets, dtype=np.float64)


def _reference_mean(players: list[_PlayerAggregate]) -> float:
    values: list[float] = []
    for player in players:
        value = round_weighted_mean(player.raw_cir_values)
        if value is not None:
            values.append(value)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _training_period(train_stats: list[PlayerMapStats]) -> tuple[date | None, date | None]:
    dates: list[date] = []
    for row in train_stats:
        played_at = row.match_map.match.played_at
        if played_at is not None:
            dates.append(played_at.date())
    if not dates:
        return None, None
    return min(dates), max(dates)


def _average_kd(stats: PlayerMapStats) -> float:
    return safe_ratio(stats.kills, stats.deaths) or 0.0


def _average_acs(stats: PlayerMapStats) -> float:
    return stats.acs or 0.0


def _average_vlr(stats: PlayerMapStats) -> float:
    return stats.vlr_rating or 0.0


def _team_metric_delta(
    team_a: list[PlayerMapStats],
    team_b: list[PlayerMapStats],
    metric_fn: Callable[[PlayerMapStats], float],
) -> float:
    if not team_a or not team_b:
        return 0.0
    team_a_value = sum(metric_fn(item) for item in team_a) / len(team_a)
    team_b_value = sum(metric_fn(item) for item in team_b) / len(team_b)
    return team_a_value - team_b_value


def _fit_univariate(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
    if not x_values or not y_values:
        return 0.0, 0.0
    x = np.array(x_values, dtype=np.float64)
    y = np.array(y_values, dtype=np.float64)
    if len(x) == 1:
        return 0.0, float(y[0])
    if np.allclose(x, x[0]):
        return 0.0, float(np.mean(y))
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)
