from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

import numpy as np

from app.metrics.cir_final_validation import (
    coefficient_summary,
    numeric_summary,
    ordered_player_ids,
    rank_map,
    split_metrics_from_arrays,
)
from app.metrics.cir_final_validation_config import (
    MIN_TRAIN_TEAM_MAPS,
)
from app.metrics.cir_round_diff import actual_round_diff
from app.metrics.cir_scoring import (
    CIRModelCoefficients,
    apply_shrinkage,
    compute_raw_cir,
    empirical_cdf,
    round_weighted_mean,
)
from app.metrics.cir_v01 import DEFAULT_RIDGE_ALPHAS
from app.metrics.cir_validation_metrics import spearman_correlation
from app.metrics.context_v2_diagnostics import role_bias_metrics
from app.metrics.ridge_regression import fit_ridge, predict_ridge, select_ridge_alpha
from app.schemas.cir_final_validation import CoefficientStabilityResult
from app.schemas.context_v2 import SplitMetrics
from app.services.cir_training_service import (
    CIREvaluationBundle,
    _chronological_map_ids,
    _coefficients_for_features,
    _design_matrix,
    _PlayerMapPrepared,
    _TeamMapPrepared,
)
from app.services.scale_event_set import SCALE_EVENT_SET

_REGION_BY_VLR = {item.vlr_event_id: item.region for item in SCALE_EVENT_SET}
_TIER_BY_VLR = {item.vlr_event_id: item.tier for item in SCALE_EVENT_SET}


def event_region(event: object | None) -> str:
    if event is None:
        return "Unknown"
    region = getattr(event, "region", None)
    if region:
        return str(region)
    vlr_id = getattr(event, "vlr_event_id", None)
    if isinstance(vlr_id, int) and vlr_id in _REGION_BY_VLR:
        return _REGION_BY_VLR[vlr_id]
    return "Unknown"


def event_tier(event: object | None) -> str:
    if event is None:
        return "Unknown"
    tier = getattr(event, "tier", None)
    if tier:
        return str(tier)
    vlr_id = getattr(event, "vlr_event_id", None)
    if isinstance(vlr_id, int) and vlr_id in _TIER_BY_VLR:
        return _TIER_BY_VLR[vlr_id]
    return "Unknown"


class PlayerScore:
    def __init__(
        self,
        player_id: UUID,
        handle: str | None,
        cir: float,
        rounds: int,
        maps: int,
        role: str,
        region: str,
    ) -> None:
        self.player_id = player_id
        self.handle = handle
        self.cir = cir
        self.rounds = rounds
        self.maps = maps
        self.role = role
        self.region = region


def split_ids(bundle: CIREvaluationBundle) -> tuple[set[UUID], set[UUID], set[UUID]]:
    train: set[UUID] = set()
    val: set[UUID] = set()
    test: set[UUID] = set()
    for row in bundle.prepared_maps:
        if row.split == "train":
            train.add(row.stats.match_map_id)
        elif row.split == "validation":
            val.add(row.stats.match_map_id)
        else:
            test.add(row.stats.match_map_id)
    return train, val, test


def map_count(bundle: CIREvaluationBundle, split: str) -> int:
    return len({row.stats.match_map_id for row in bundle.prepared_maps if row.split == split})


def split_periods(bundle: CIREvaluationBundle) -> dict[str, tuple[str | None, str | None]]:
    grouped: dict[str, list[datetime]] = defaultdict(list)
    for row in bundle.prepared_maps:
        played_at = row.stats.match_map.match.played_at
        if played_at is not None:
            grouped[row.split].append(played_at)
    periods: dict[str, tuple[str | None, str | None]] = {}
    for name in ("train", "validation", "test"):
        dates = grouped.get(name, [])
        if not dates:
            periods[name] = (None, None)
        else:
            periods[name] = (min(dates).date().isoformat(), max(dates).date().isoformat())
    return periods


def metrics_for_split(
    bundle: CIREvaluationBundle,
    split: str,
    coefficients: CIRModelCoefficients,
    features: tuple[str, ...],
) -> SplitMetrics:
    maps = [row for row in bundle.team_maps if row.split == split]
    return predict_team_maps(maps, coefficients, features)


def predict_team_maps(
    maps: list[_TeamMapPrepared],
    coefficients: CIRModelCoefficients,
    features: tuple[str, ...],
) -> SplitMetrics:
    design, targets = _design_matrix(maps, feature_names=features)
    if len(targets) == 0:
        return SplitMetrics()
    weights = np.array(
        [coefficients.coefficients.get(name, 0.0) for name in features],
        dtype=np.float64,
    )
    return split_metrics_from_arrays(
        targets, predict_ridge(design, coefficients.intercept, weights)
    )


def player_scores(
    bundle: CIREvaluationBundle,
    coefficients: CIRModelCoefficients,
    features: tuple[str, ...],
    shrinkage_k: float,
) -> dict[UUID, PlayerScore]:
    by_player: dict[UUID, list[tuple[float, int]]] = defaultdict(list)
    handles: dict[UUID, str | None] = {}
    roles: dict[UUID, str] = {}
    regions: dict[UUID, str] = {}
    maps: dict[UUID, set[UUID]] = defaultdict(set)
    train_ids: set[UUID] = set()
    for row in bundle.prepared_maps:
        raw = compute_raw_cir(row.standardized_features, coefficients, feature_names=features)
        by_player[row.stats.player_id].append((raw, row.stats.rounds))
        handles[row.stats.player_id] = row.stats.player.handle
        if row.stats.agent is not None:
            roles[row.stats.player_id] = row.stats.agent.role
        event = row.stats.match_map.match.event
        regions[row.stats.player_id] = event_region(event)
        maps[row.stats.player_id].add(row.stats.match_map_id)
        if row.split == "train":
            train_ids.add(row.stats.player_id)
    reference_values: list[float] = []
    raw_means: dict[UUID, tuple[float, int]] = {}
    for player_id, values in by_player.items():
        raw_mean = round_weighted_mean(values)
        rounds = sum(weight for _, weight in values)
        if raw_mean is None:
            continue
        raw_means[player_id] = (raw_mean, rounds)
        if player_id in train_ids:
            reference_values.append(raw_mean)
    reference_mean = float(np.mean(reference_values)) if reference_values else 0.0
    population = [
        apply_shrinkage(raw_mean, rounds, reference_mean, shrinkage_k)
        for player_id, (raw_mean, rounds) in raw_means.items()
        if player_id in train_ids
    ]
    scores: dict[UUID, PlayerScore] = {}
    for player_id, (raw_mean, rounds) in raw_means.items():
        shrunk = apply_shrinkage(raw_mean, rounds, reference_mean, shrinkage_k)
        scores[player_id] = PlayerScore(
            player_id=player_id,
            handle=handles.get(player_id),
            cir=empirical_cdf(shrunk, population or [shrunk]),
            rounds=rounds,
            maps=len(maps.get(player_id, set())),
            role=roles.get(player_id, "Unknown"),
            region=regions.get(player_id, "Unknown"),
        )
    return scores


def gap_from_scores(scores: dict[UUID, PlayerScore]) -> float | None:
    grouped: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for score in scores.values():
        grouped[score.role].append((score.cir, score.rounds))
    return role_bias_metrics(grouped).max_role_median_gap


def ordered_events(
    bundle: CIREvaluationBundle,
) -> list[tuple[UUID, str, int | None, str | None, str | None]]:
    earliest: dict[UUID, datetime] = {}
    meta: dict[UUID, tuple[str, int | None, str | None, str | None]] = {}
    for row in bundle.prepared_maps:
        event = row.stats.match_map.match.event
        if event is None:
            continue
        played_at = row.stats.match_map.match.played_at or datetime.min
        current = earliest.get(event.id)
        if current is None or played_at < current:
            earliest[event.id] = played_at
            meta[event.id] = (
                event.name,
                event.vlr_event_id,
                event_tier(event),
                event_region(event),
            )
    return [
        (event_id, *meta[event_id])
        for event_id, _ in sorted(earliest.items(), key=lambda item: item[1])
    ]


def maps_by_event(bundle: CIREvaluationBundle) -> dict[UUID, list[UUID]]:
    grouped: dict[UUID, list[UUID]] = defaultdict(list)
    seen: set[UUID] = set()
    for row in bundle.prepared_maps:
        event = row.stats.match_map.match.event
        map_id = row.stats.match_map_id
        if event is None or map_id in seen:
            continue
        seen.add(map_id)
        grouped[event.id].append(map_id)
    return grouped


def order_maps(bundle: CIREvaluationBundle, map_ids: list[UUID]) -> list[UUID]:
    wanted = set(map_ids)
    stats = [row.stats for row in bundle.prepared_maps if row.stats.match_map_id in wanted]
    return _chronological_map_ids(stats)


def region_by_map(bundle: CIREvaluationBundle) -> dict[UUID, str]:
    lookup: dict[UUID, str] = {}
    for row in bundle.prepared_maps:
        event = row.stats.match_map.match.event
        lookup[row.stats.match_map_id] = event_region(event)
    return lookup


def match_id_for(bundle: CIREvaluationBundle, match_map_id: UUID) -> UUID | None:
    for row in bundle.prepared_maps:
        if row.stats.match_map_id == match_map_id:
            return row.stats.match_map.match_id
    return None


def match_ids_for_maps(bundle: CIREvaluationBundle, map_ids: set[UUID]) -> list[UUID]:
    ids: list[UUID] = []
    seen: set[UUID] = set()
    for row in bundle.prepared_maps:
        if row.stats.match_map_id not in map_ids:
            continue
        match_id = row.stats.match_map.match_id
        if match_id in seen:
            continue
        seen.add(match_id)
        ids.append(match_id)
    return ids


def resample_match_ids(match_ids: list[UUID], rng: np.random.Generator) -> list[UUID]:
    if not match_ids:
        return []
    indices = rng.integers(0, len(match_ids), size=len(match_ids))
    return [match_ids[int(index)] for index in indices]


def fit_ridge_on_maps(
    maps: list[_TeamMapPrepared],
    features: tuple[str, ...],
    alpha: float | None = None,
) -> tuple[CIRModelCoefficients, float]:
    train = [row for row in maps if row.split == "train"] or maps
    val = [row for row in maps if row.split == "validation"] or train
    train_design, train_targets = _design_matrix(train, feature_names=features)
    val_design, val_targets = _design_matrix(val, feature_names=features)
    ridge_alpha = (
        alpha
        if alpha is not None
        else select_ridge_alpha(
            train_design,
            train_targets,
            val_design if len(val_targets) else train_design,
            val_targets if len(val_targets) else train_targets,
            DEFAULT_RIDGE_ALPHAS,
        )
    )
    intercept, weights = fit_ridge(train_design, train_targets, ridge_alpha)
    coefficients = CIRModelCoefficients(
        intercept=intercept,
        coefficients=_coefficients_for_features(features, weights),
    )
    return coefficients, ridge_alpha


def fit_feature_subset(
    bundle: CIREvaluationBundle,
    features: tuple[str, ...],
) -> tuple[CIRModelCoefficients, SplitMetrics, SplitMetrics]:
    coefficients, _alpha = fit_ridge_on_maps(bundle.team_maps, features)
    return (
        coefficients,
        metrics_for_split(bundle, "validation", coefficients, features),
        metrics_for_split(bundle, "test", coefficients, features),
    )


def score_spearman(
    left: dict[UUID, PlayerScore],
    right: dict[UUID, PlayerScore],
) -> float | None:
    shared = [player_id for player_id in left if player_id in right]
    if len(shared) < 2:
        return None
    return spearman_correlation(
        np.array([left[player_id].cir for player_id in shared], dtype=np.float64),
        np.array([right[player_id].cir for player_id in shared], dtype=np.float64),
    )


def team_maps_with_raw_target(bundle: CIREvaluationBundle) -> list[_TeamMapPrepared]:
    lookup = {row.stats.match_map_id: row.stats.match_map for row in bundle.prepared_maps}
    rebuilt: list[_TeamMapPrepared] = []
    for row in bundle.team_maps:
        match_map = lookup.get(row.match_map_id)
        if match_map is None:
            continue
        actual = actual_round_diff(match_map.team_a_score, match_map.team_b_score)
        if actual is None:
            continue
        rebuilt.append(
            _TeamMapPrepared(
                match_map_id=row.match_map_id,
                split=row.split,
                outcome_residual=float(actual),
                deltas=row.deltas,
            )
        )
    return rebuilt


def team_maps_mean_aggregated(bundle: CIREvaluationBundle) -> list[_TeamMapPrepared]:
    grouped: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
    for row in bundle.prepared_maps:
        grouped[row.stats.match_map_id].append(row)
    team_lookup = {row.match_map_id: row for row in bundle.team_maps}
    features = bundle.feature_names
    rebuilt: list[_TeamMapPrepared] = []
    for match_map_id, rows in grouped.items():
        original = team_lookup.get(match_map_id)
        if original is None:
            continue
        match = rows[0].stats.match_map.match
        if match.team_a_id is None or match.team_b_id is None:
            continue
        team_a = [row.standardized_features for row in rows if row.stats.team_id == match.team_a_id]
        team_b = [row.standardized_features for row in rows if row.stats.team_id == match.team_b_id]
        deltas: dict[str, float] = {}
        for name in features:
            left = sum(item.get(name, 0.0) for item in team_a) / len(team_a) if team_a else 0.0
            right = sum(item.get(name, 0.0) for item in team_b) / len(team_b) if team_b else 0.0
            deltas[name] = left - right
        rebuilt.append(
            _TeamMapPrepared(
                match_map_id=match_map_id,
                split=original.split,
                outcome_residual=original.outcome_residual,
                deltas=deltas,
            )
        )
    return rebuilt


def partial_period_scores(
    bundle: CIREvaluationBundle,
    coefficients: CIRModelCoefficients,
    features: tuple[str, ...],
    threshold: int,
    shrinkage_k: float,
    reference_mean: float,
) -> dict[UUID, float]:
    grouped: dict[UUID, list[_PlayerMapPrepared]] = defaultdict(list)
    for row in bundle.prepared_maps:
        grouped[row.stats.player_id].append(row)
    for rows in grouped.values():
        rows.sort(
            key=lambda item: (
                item.stats.match_map.match.played_at or datetime.min,
                item.stats.match_map.match.vlr_match_id,
                item.stats.match_map_id,
            )
        )
    raw_means: dict[UUID, tuple[float, int]] = {}
    train_raw: list[float] = []
    for player_id, rows in grouped.items():
        cumulative = 0
        values: list[tuple[float, int]] = []
        for row in rows:
            if cumulative >= threshold:
                break
            raw = compute_raw_cir(row.standardized_features, coefficients, feature_names=features)
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
        raw_means[player_id] = (raw_mean, cumulative)
        if any(row.split == "train" for row in rows):
            train_raw.append(raw_mean)
    mean = float(np.mean(train_raw)) if train_raw else reference_mean
    population = [
        apply_shrinkage(raw_mean, rounds, mean, shrinkage_k)
        for raw_mean, rounds in raw_means.values()
    ]
    return {
        player_id: empirical_cdf(
            apply_shrinkage(raw_mean, rounds, mean, shrinkage_k),
            population,
        )
        for player_id, (raw_mean, rounds) in raw_means.items()
    }


def bootstrap_player_draws(
    bundle: CIREvaluationBundle,
    features: tuple[str, ...],
    ridge_alpha: float,
    shrinkage_k: float,
    iterations: int,
    seed: int,
) -> dict[UUID, list[tuple[float, float]]]:
    train_maps = [row for row in bundle.team_maps if row.split == "train"]
    ids = match_ids_for_maps(bundle, {row.match_map_id for row in train_maps})
    maps_by_match: dict[UUID, list[_TeamMapPrepared]] = defaultdict(list)
    for row in train_maps:
        match_id = match_id_for(bundle, row.match_map_id)
        if match_id is not None:
            maps_by_match[match_id].append(row)
    usable = [match_id for match_id in ids if match_id in maps_by_match]
    if len(usable) < 2:
        return {}
    rng = np.random.default_rng(seed)
    draws: list[dict[UUID, float]] = []
    for _ in range(iterations):
        sampled = resample_match_ids(usable, rng)
        boot_maps = [row for match_id in sampled for row in maps_by_match[match_id]]
        if len(boot_maps) < MIN_TRAIN_TEAM_MAPS:
            continue
        try:
            model, _alpha = fit_ridge_on_maps(boot_maps, features, alpha=ridge_alpha)
        except np.linalg.LinAlgError:
            continue
        scores = player_scores(bundle, model, features, shrinkage_k)
        draws.append({player_id: score.cir for player_id, score in scores.items()})
    ranked: dict[UUID, list[tuple[float, float]]] = defaultdict(list)
    for snapshot in draws:
        order = ordered_player_ids({str(player_id): value for player_id, value in snapshot.items()})
        ranks = rank_map(order)
        for player_id, value in snapshot.items():
            ranked[player_id].append((value, float(ranks[str(player_id)])))
    return ranked


def role_outcome_corr(
    bundle: CIREvaluationBundle,
    coefficients: CIRModelCoefficients,
    role: str,
) -> float | None:
    lookup = {row.match_map_id: row.outcome_residual for row in bundle.team_maps}
    xs: list[float] = []
    ys: list[float] = []
    for row in bundle.prepared_maps:
        row_role = row.stats.agent.role if row.stats.agent is not None else "Unknown"
        if row_role != role:
            continue
        residual = lookup.get(row.stats.match_map_id)
        if residual is None:
            continue
        match = row.stats.match_map.match
        signed = residual if row.stats.team_id == match.team_a_id else -residual
        xs.append(
            compute_raw_cir(
                row.standardized_features, coefficients, feature_names=bundle.feature_names
            )
        )
        ys.append(signed)
    if len(xs) < 2:
        return None
    return spearman_correlation(np.array(xs, dtype=np.float64), np.array(ys, dtype=np.float64))


def coef_stability(
    kpr: list[float],
    ndpr: list[float],
    alphas: list[float],
) -> CoefficientStabilityResult:
    return CoefficientStabilityResult(
        kpr=coefficient_summary(kpr),
        negative_dpr=coefficient_summary(ndpr),
        ridge_alpha=numeric_summary(alphas),
        fold_count=len(kpr),
    )


def as_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
