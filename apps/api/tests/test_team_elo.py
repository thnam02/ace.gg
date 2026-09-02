from __future__ import annotations

import pytest

from app.metrics.team_elo import (
    DEFAULT_BASELINE_RATING,
    DEFAULT_K_FACTOR,
    expected_win_probability,
    update_rating,
)


def test_expected_win_probability_equal_ratings() -> None:
    assert expected_win_probability(1500.0, 1500.0) == pytest.approx(0.5)


def test_expected_win_probability_higher_rating_favored() -> None:
    probability = expected_win_probability(1600.0, 1400.0)
    assert probability > 0.5
    assert probability == pytest.approx(1.0 / (1.0 + 10 ** (-0.5)))


def test_update_rating_win_increases_rating() -> None:
    updated = update_rating(1500.0, 1.0, 0.5, DEFAULT_K_FACTOR)
    assert updated > 1500.0
    assert updated == pytest.approx(1500.0 + DEFAULT_K_FACTOR * 0.5)


def test_update_rating_loss_decreases_rating() -> None:
    updated = update_rating(1500.0, 0.0, 0.5, DEFAULT_K_FACTOR)
    assert updated < 1500.0
    assert updated == pytest.approx(1500.0 - DEFAULT_K_FACTOR * 0.5)


def test_baseline_rating_constant() -> None:
    assert DEFAULT_BASELINE_RATING == 1500.0
