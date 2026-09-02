from __future__ import annotations

import pytest

from app.metrics.derived import aggregate_raw, compute_derived, safe_ratio, weighted_average
from app.metrics.stats_engine import StatsEngine
from app.schemas.stats import MapStatsRaw


def _raw(
    *,
    rounds: int = 20,
    kills: int = 10,
    deaths: int = 8,
    assists: int = 4,
    first_kills: int = 3,
    first_deaths: int = 2,
    adr: float | None = 150.0,
    kast_pct: float | None = 70.0,
    clutch_wins: int | None = 1,
    clutch_attempts: int | None = 2,
    acs: float | None = 220.0,
) -> MapStatsRaw:
    return MapStatsRaw(
        rounds=rounds,
        kills=kills,
        deaths=deaths,
        assists=assists,
        first_kills=first_kills,
        first_deaths=first_deaths,
        adr=adr,
        kast_pct=kast_pct,
        clutch_wins=clutch_wins,
        clutch_attempts=clutch_attempts,
        acs=acs,
    )


def test_normal_derived_calculations() -> None:
    raw = _raw(rounds=21, kills=18, deaths=12, assists=4, first_kills=5, first_deaths=2)
    derived = compute_derived(raw)

    assert derived.kpr == pytest.approx(18 / 21)
    assert derived.dpr == pytest.approx(12 / 21)
    assert derived.apr == pytest.approx(4 / 21)
    assert derived.fkpr == pytest.approx(5 / 21)
    assert derived.fdpr == pytest.approx(2 / 21)
    assert derived.opening_frequency == pytest.approx(7 / 21)
    assert derived.opening_efficiency == pytest.approx(5 / 7)
    assert derived.raw_clutch_rate == pytest.approx(0.5)


def test_zero_rounds_returns_none_for_per_round_metrics() -> None:
    derived = compute_derived(_raw(rounds=0))

    assert derived.kpr is None
    assert derived.dpr is None
    assert derived.apr is None
    assert derived.fkpr is None
    assert derived.fdpr is None
    assert derived.opening_frequency is None


def test_zero_opening_duels_returns_none_for_opening_efficiency() -> None:
    derived = compute_derived(_raw(first_kills=0, first_deaths=0))

    assert derived.opening_frequency == 0.0
    assert derived.opening_efficiency is None


def test_zero_clutch_attempts_returns_none_for_raw_clutch_rate() -> None:
    derived = compute_derived(_raw(clutch_attempts=0, clutch_wins=0))
    assert derived.raw_clutch_rate is None

    derived_none = compute_derived(_raw(clutch_attempts=None, clutch_wins=None))
    assert derived_none.raw_clutch_rate is None


def test_missing_optional_values_remain_none_in_raw_and_weighted() -> None:
    raw = _raw(adr=None, kast_pct=None, acs=None, clutch_wins=None, clutch_attempts=None)
    derived = compute_derived(raw)

    assert raw.adr is None
    assert derived.raw_clutch_rate is None
    assert derived.kpr is not None


def test_safe_ratio_handles_zero_denominator() -> None:
    assert safe_ratio(1, 0) is None
    assert safe_ratio(0, 5) == 0.0


def test_weighted_average_uses_round_weights() -> None:
    value = weighted_average([(100.0, 10), (200.0, 30)])
    assert value == pytest.approx(175.0)


def test_multi_map_weighted_aggregation() -> None:
    rows = [
        _raw(rounds=20, kills=10, adr=100.0, kast_pct=60.0, acs=200.0),
        _raw(rounds=30, kills=15, adr=200.0, kast_pct=80.0, acs=300.0),
    ]
    aggregated = aggregate_raw(rows)

    assert aggregated.rounds == 50
    assert aggregated.kills == 25
    assert aggregated.adr == pytest.approx((100 * 20 + 200 * 30) / 50)
    assert aggregated.kast_pct == pytest.approx((60 * 20 + 80 * 30) / 50)
    assert aggregated.acs == pytest.approx((200 * 20 + 300 * 30) / 50)

    aggregate = StatsEngine().aggregate(rows)
    assert aggregate.raw.maps_played == 2
    assert aggregate.raw.weighted_adr == aggregated.adr
    assert aggregate.derived.kpr == pytest.approx(25 / 50)


def test_stats_engine_separates_raw_and_derived() -> None:
    features = StatsEngine().from_raw(_raw())
    assert features.raw.kills == 10
    assert features.derived.kpr is not None
    assert isinstance(features.raw, MapStatsRaw)
    assert isinstance(features.derived.kpr, float)
