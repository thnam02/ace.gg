from __future__ import annotations

import pytest

from app.metrics.adr_regression import AdrRegressionModel, train_adr_regression
from app.metrics.bayesian_clutch import ClutchPrior, compute_bayesian_clutch, estimate_clutch_prior
from app.metrics.derived import compute_derived
from app.metrics.feature_engine import FeatureEngine
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
    )


def _adr_model(intercept: float = 100.0, slope: float = 50.0) -> AdrRegressionModel:
    return AdrRegressionModel(intercept=intercept, slope=slope, sample_count=10)


def _clutch_prior(rate: float = 0.3, strength: float = 10.0) -> ClutchPrior:
    return ClutchPrior(
        alpha=rate * strength,
        beta=(1.0 - rate) * strength,
        population_rate=rate,
        prior_strength=strength,
    )


def test_residual_adr_positive_when_above_expected() -> None:
    raw = _raw(rounds=20, kills=20, adr=200.0)
    derived = compute_derived(raw)
    engine = FeatureEngine(_adr_model(intercept=100.0, slope=50.0), _clutch_prior())

    features = engine.from_raw(raw, derived=derived)
    expected = 100.0 + 50.0 * derived.kpr

    assert features.expected_adr == pytest.approx(expected)
    assert features.residual_adr == pytest.approx(200.0 - expected)
    assert features.residual_adr > 0


def test_residual_adr_negative_when_below_expected() -> None:
    raw = _raw(rounds=20, kills=5, adr=80.0)
    derived = compute_derived(raw)
    engine = FeatureEngine(_adr_model(intercept=100.0, slope=50.0), _clutch_prior())

    features = engine.from_raw(raw, derived=derived)
    expected = 100.0 + 50.0 * derived.kpr

    assert features.expected_adr == pytest.approx(expected)
    assert features.residual_adr == pytest.approx(80.0 - expected)
    assert features.residual_adr < 0


def test_residual_adr_missing_when_adr_missing() -> None:
    raw = _raw(adr=None)
    engine = FeatureEngine(_adr_model(), _clutch_prior())

    features = engine.from_raw(raw)
    assert features.expected_adr is not None
    assert features.residual_adr is None


def test_residual_adr_missing_when_kpr_missing() -> None:
    raw = _raw(rounds=0, adr=150.0)
    engine = FeatureEngine(_adr_model(), _clutch_prior())

    features = engine.from_raw(raw)
    assert features.expected_adr is None
    assert features.residual_adr is None


def test_adr_regression_sparse_data_uses_zero_slope() -> None:
    model = train_adr_regression([(0.5, 120.0)])
    assert model.slope == 0.0
    assert model.intercept == pytest.approx(120.0)
    assert model.sample_count == 1


def test_adr_regression_zero_kpr_variance_uses_mean_adr() -> None:
    model = train_adr_regression([(0.5, 100.0), (0.5, 140.0)])
    assert model.slope == 0.0
    assert model.intercept == pytest.approx(120.0)


def test_adr_regression_fits_simple_line() -> None:
    observations = [(0.0, 100.0), (1.0, 150.0)]
    model = train_adr_regression(observations)

    assert model.slope == pytest.approx(50.0)
    assert model.intercept == pytest.approx(100.0)
    assert model.predict(0.5) == pytest.approx(125.0)


def test_zero_clutch_attempts_returns_none_rates() -> None:
    estimate = compute_bayesian_clutch(0, 0, _clutch_prior())
    assert estimate.raw_clutch_rate is None
    assert estimate.bayesian_clutch_rate is None
    assert estimate.clutch_attempts == 0


def test_small_sample_clutch_shrinkage_toward_prior() -> None:
    prior = _clutch_prior(rate=0.3, strength=10.0)
    estimate = compute_bayesian_clutch(1, 2, prior)

    assert estimate.raw_clutch_rate == pytest.approx(0.5)
    assert estimate.bayesian_clutch_rate is not None
    assert estimate.bayesian_clutch_rate < estimate.raw_clutch_rate
    assert estimate.bayesian_clutch_rate > prior.population_rate


def test_large_sample_clutch_converges_to_raw() -> None:
    prior = _clutch_prior(rate=0.3, strength=10.0)
    estimate = compute_bayesian_clutch(150, 200, prior)

    assert estimate.raw_clutch_rate == pytest.approx(0.75)
    assert estimate.bayesian_clutch_rate is not None
    assert abs(estimate.bayesian_clutch_rate - estimate.raw_clutch_rate) < 0.05


def test_missing_clutch_data_returns_none_rates() -> None:
    estimate = compute_bayesian_clutch(None, None, _clutch_prior())
    assert estimate.raw_clutch_rate is None
    assert estimate.bayesian_clutch_rate is None
    assert estimate.effective_sample_size is None


def test_clutch_prior_from_reference_population() -> None:
    prior = estimate_clutch_prior([(1, 4), (3, 6), (0, 2)])
    assert prior.population_rate == pytest.approx(4 / 12)
    assert prior.alpha > 0
    assert prior.beta > 0
    assert prior.prior_strength == pytest.approx(prior.alpha + prior.beta)


def test_aggregated_player_features_use_totals_not_double_count() -> None:
    rows = [
        _raw(rounds=20, kills=10, adr=100.0, kast_pct=60.0, clutch_wins=1, clutch_attempts=2),
        _raw(rounds=30, kills=15, adr=200.0, kast_pct=80.0, clutch_wins=2, clutch_attempts=4),
    ]
    stats_engine = StatsEngine()
    aggregate = stats_engine.aggregate(rows)
    engine = FeatureEngine(
        _adr_model(intercept=50.0, slope=100.0),
        _clutch_prior(rate=0.25, strength=8.0),
    )

    features = engine.from_aggregate(aggregate)

    assert features.kpr == pytest.approx(25 / 50)
    assert features.adr == pytest.approx((100 * 20 + 200 * 30) / 50)
    assert features.kast == pytest.approx((60 * 20 + 80 * 30) / 50)
    assert features.clutch_attempts == 6
    assert features.raw_clutch_rate == pytest.approx(3 / 6)


def test_cir_features_include_all_required_fields() -> None:
    engine = FeatureEngine(_adr_model(), _clutch_prior())
    features = engine.from_raw(_raw())

    for field in (
        "kpr",
        "dpr",
        "apr",
        "fkpr",
        "fdpr",
        "opening_frequency",
        "opening_efficiency",
        "adr",
        "expected_adr",
        "residual_adr",
        "kast",
        "raw_clutch_rate",
        "bayesian_clutch_rate",
    ):
        assert hasattr(features, field)

    assert features.clutch_effective_sample_size is not None
