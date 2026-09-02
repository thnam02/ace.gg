from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from app.metrics.cir.combat import equal_weight_combat_factor
from app.metrics.cir.config import (
    KPR_FEATURE,
    NEGATIVE_DPR_FEATURE,
    SHRINKAGE_K,
    TAU,
)
from app.metrics.cir.context import expected_rates, observed_dpr, observed_kpr
from app.metrics.cir.reliability import (
    reliability_for_rounds,
    reliability_pct,
    sample_status_for_rounds,
    sample_weight,
)
from app.metrics.cir_scoring import apply_shrinkage, empirical_cdf, round_weighted_mean
from app.metrics.cir_standardization import StandardizationParams, standardize_features
from app.metrics.context_baselines import ContextObservation
from app.metrics.context_v2 import ContextV2Registry
from app.metrics.derived import safe_ratio


@dataclass
class CirMapScore:
    player_id: UUID
    handle: str | None
    match_map_id: UUID
    rounds: int
    role: str
    agent_name: str | None
    tier: str | None
    event_id: UUID | None
    vlr_event_id: int | None
    played_on: date | None
    kpr: float
    dpr: float
    expected_kpr: float
    expected_dpr: float
    kpr_residual: float
    negative_dpr_residual: float
    z_kpr: float
    z_negative_dpr: float
    combat_factor: float


@dataclass
class CirPlayerScore:
    player_id: UUID
    handle: str | None
    raw_cir: float
    shrunk_raw_cir: float
    cir: float
    combat_factor: float
    rounds: int
    maps: int
    events: int
    sample_weight: float
    sample_status: str
    reliability: str
    reliability_pct: float
    kpr: float | None
    dpr: float | None
    expected_kpr: float | None
    expected_dpr: float | None
    kpr_residual: float | None
    negative_dpr_residual: float | None
    z_kpr: float | None
    z_negative_dpr: float | None
    role: str | None
    primary_agent: str | None
    tier: str | None
    event_ids: list[str] = field(default_factory=list)
    vlr_event_ids: list[int] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None

    def details(self) -> dict[str, Any]:
        return {
            "kpr": self.kpr,
            "dpr": self.dpr,
            "expected_kpr": self.expected_kpr,
            "expected_dpr": self.expected_dpr,
            "kpr_residual": self.kpr_residual,
            "negative_dpr_residual": self.negative_dpr_residual,
            "z_kpr": self.z_kpr,
            "z_negative_dpr": self.z_negative_dpr,
            "role": self.role,
            "primary_agent": self.primary_agent,
            "tier": self.tier,
            "event_ids": self.event_ids,
            "vlr_event_ids": self.vlr_event_ids,
            "reliability_pct": self.reliability_pct,
        }


def kpr_residual(kpr: float, expected_kpr: float) -> float:
    return kpr - expected_kpr


def negative_dpr_residual(dpr: float, expected_dpr: float) -> float:
    return -(dpr - expected_dpr)


def score_observation(
    observation: ContextObservation,
    *,
    registry: ContextV2Registry,
    standardization: StandardizationParams,
    player_id: UUID,
    handle: str | None,
    match_map_id: UUID,
    event_id: UUID | None,
    vlr_event_id: int | None,
    agent_name: str | None,
    tau: float = TAU,
) -> CirMapScore | None:
    if observation.rounds <= 0:
        return None
    kpr = observed_kpr(observation.kills, observation.rounds)
    dpr = observed_dpr(observation.deaths, observation.rounds)
    if kpr is None or dpr is None:
        return None
    expected_kpr, expected_dpr = expected_rates(registry, observation, tau=tau)
    if expected_kpr is None or expected_dpr is None:
        return None
    kpr_res = kpr_residual(kpr, expected_kpr)
    ndpr_res = negative_dpr_residual(dpr, expected_dpr)
    standardized = standardize_features(
        {KPR_FEATURE: kpr_res, NEGATIVE_DPR_FEATURE: ndpr_res},
        standardization,
        feature_names=(KPR_FEATURE, NEGATIVE_DPR_FEATURE),
    )
    z_kpr = standardized[KPR_FEATURE]
    z_ndpr = standardized[NEGATIVE_DPR_FEATURE]
    played_on = observation.played_at.date() if observation.played_at is not None else None
    return CirMapScore(
        player_id=player_id,
        handle=handle,
        match_map_id=match_map_id,
        rounds=observation.rounds,
        role=observation.role,
        agent_name=agent_name,
        tier=observation.tier,
        event_id=event_id,
        vlr_event_id=vlr_event_id,
        played_on=played_on,
        kpr=kpr,
        dpr=dpr,
        expected_kpr=expected_kpr,
        expected_dpr=expected_dpr,
        kpr_residual=kpr_res,
        negative_dpr_residual=ndpr_res,
        z_kpr=z_kpr,
        z_negative_dpr=z_ndpr,
        combat_factor=equal_weight_combat_factor(z_kpr, z_ndpr),
    )


def aggregate_player_scores(
    maps: list[CirMapScore],
    *,
    reference_mean: float,
    reference_population: list[float],
    shrinkage_k: float = SHRINKAGE_K,
) -> list[CirPlayerScore]:
    grouped: dict[UUID, list[CirMapScore]] = {}
    for row in maps:
        grouped.setdefault(row.player_id, []).append(row)
    players: list[CirPlayerScore] = []
    for player_id, rows in grouped.items():
        score = score_player_from_maps(
            rows,
            reference_mean=reference_mean,
            reference_population=reference_population,
            shrinkage_k=shrinkage_k,
        )
        if score is not None:
            players.append(score)
    return players


def score_player_from_maps(
    rows: list[CirMapScore],
    *,
    reference_mean: float,
    reference_population: list[float],
    shrinkage_k: float = SHRINKAGE_K,
) -> CirPlayerScore | None:
    combat_pairs = [(row.combat_factor, row.rounds) for row in rows if row.rounds > 0]
    raw_cir = round_weighted_mean(combat_pairs)
    rounds = sum(row.rounds for row in rows)
    if raw_cir is None or rounds <= 0:
        return None
    weight = sample_weight(rounds, shrinkage_k)
    shrunk = apply_shrinkage(raw_cir, rounds, reference_mean, shrinkage_k)
    cir = max(0.0, min(100.0, empirical_cdf(shrunk, reference_population)))
    dates = [row.played_on for row in rows if row.played_on is not None]
    event_ids = sorted({str(row.event_id) for row in rows if row.event_id is not None})
    vlr_event_ids = sorted({row.vlr_event_id for row in rows if row.vlr_event_id is not None})
    return CirPlayerScore(
        player_id=rows[0].player_id,
        handle=rows[0].handle,
        raw_cir=raw_cir,
        shrunk_raw_cir=shrunk,
        cir=cir,
        combat_factor=raw_cir,
        rounds=rounds,
        maps=len({row.match_map_id for row in rows}),
        events=len(event_ids) if event_ids else len(vlr_event_ids),
        sample_weight=weight,
        sample_status=sample_status_for_rounds(rounds).value,
        reliability=reliability_for_rounds(rounds).value,
        reliability_pct=reliability_pct(rounds),
        kpr=_weighted(rows, "kpr"),
        dpr=_weighted(rows, "dpr"),
        expected_kpr=_weighted(rows, "expected_kpr"),
        expected_dpr=_weighted(rows, "expected_dpr"),
        kpr_residual=_weighted(rows, "kpr_residual"),
        negative_dpr_residual=_weighted(rows, "negative_dpr_residual"),
        z_kpr=_weighted(rows, "z_kpr"),
        z_negative_dpr=_weighted(rows, "z_negative_dpr"),
        role=_majority(rows, "role"),
        primary_agent=_majority(rows, "agent_name"),
        tier=_majority(rows, "tier"),
        event_ids=event_ids,
        vlr_event_ids=vlr_event_ids,
        period_start=min(dates) if dates else None,
        period_end=max(dates) if dates else None,
    )


def reference_from_train_maps(
    maps: list[CirMapScore],
    train_player_ids: set[UUID],
    *,
    shrinkage_k: float = SHRINKAGE_K,
) -> tuple[float, list[float]]:
    train_maps = [row for row in maps if row.player_id in train_player_ids]
    grouped: dict[UUID, list[CirMapScore]] = {}
    for row in train_maps:
        grouped.setdefault(row.player_id, []).append(row)
    raw_values: list[float] = []
    for rows in grouped.values():
        raw = round_weighted_mean([(row.combat_factor, row.rounds) for row in rows])
        if raw is not None:
            raw_values.append(raw)
    reference_mean = sum(raw_values) / len(raw_values) if raw_values else 0.0
    population = [
        apply_shrinkage(
            round_weighted_mean([(row.combat_factor, row.rounds) for row in rows]) or 0.0,
            sum(row.rounds for row in rows),
            reference_mean,
            shrinkage_k,
        )
        for rows in grouped.values()
        if any(row.rounds > 0 for row in rows)
    ]
    return reference_mean, sorted(population)


def _weighted(rows: list[CirMapScore], field_name: str) -> float | None:
    pairs = [(float(getattr(row, field_name)), row.rounds) for row in rows]
    return round_weighted_mean(pairs)


def _majority(rows: list[CirMapScore], field_name: str) -> str | None:
    totals: dict[str, int] = {}
    for row in rows:
        value = getattr(row, field_name)
        if not value:
            continue
        totals[str(value)] = totals.get(str(value), 0) + row.rounds
    if not totals:
        return None
    return max(totals, key=lambda name: (totals[name], name))


def rate_or_none(numerator: int, denominator: int) -> float | None:
    return safe_ratio(numerator, denominator)
