from __future__ import annotations

DEFAULT_BASELINE_RATING = 1500.0
DEFAULT_K_FACTOR = 32.0


def expected_win_probability(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_rating(rating: float, score: float, expected: float, k_factor: float) -> float:
    return rating + k_factor * (score - expected)
