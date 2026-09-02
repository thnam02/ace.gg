from __future__ import annotations

from dataclasses import dataclass

from app.metrics.derived import safe_ratio


@dataclass(frozen=True)
class ClutchPrior:
    alpha: float
    beta: float
    population_rate: float
    prior_strength: float


@dataclass(frozen=True)
class BayesianClutchEstimate:
    raw_clutch_rate: float | None
    bayesian_clutch_rate: float | None
    clutch_attempts: int | None
    clutch_wins: int | None
    effective_sample_size: float | None
    prior_strength: float | None


def estimate_beta_prior(success_fail_pairs: list[tuple[int, int]]) -> ClutchPrior:
    if not success_fail_pairs:
        return ClutchPrior(alpha=1.0, beta=1.0, population_rate=0.5, prior_strength=2.0)

    total_successes = sum(successes for successes, _ in success_fail_pairs)
    total_failures = sum(failures for _, failures in success_fail_pairs)
    total_trials = total_successes + total_failures
    if total_trials == 0:
        return ClutchPrior(alpha=1.0, beta=1.0, population_rate=0.5, prior_strength=2.0)

    population_rate = total_successes / total_trials
    avg_trials = total_trials / len(success_fail_pairs)
    prior_strength = max(2.0, min(20.0, avg_trials))
    alpha = population_rate * prior_strength
    beta = (1.0 - population_rate) * prior_strength
    return ClutchPrior(
        alpha=alpha,
        beta=beta,
        population_rate=population_rate,
        prior_strength=prior_strength,
    )


def estimate_clutch_prior(observations: list[tuple[int, int]]) -> ClutchPrior:
    pairs = [(wins, attempts - wins) for wins, attempts in observations if attempts > 0]
    return estimate_beta_prior(pairs)


def estimate_beta_prior_from_exposure(
    successes: int,
    failures: int,
    observation_count: int,
) -> ClutchPrior:
    total_trials = successes + failures
    if total_trials == 0 or observation_count == 0:
        return ClutchPrior(alpha=1.0, beta=1.0, population_rate=0.5, prior_strength=2.0)

    population_rate = successes / total_trials
    avg_trials = total_trials / observation_count
    prior_strength = max(2.0, min(20.0, avg_trials))
    alpha = population_rate * prior_strength
    beta = (1.0 - population_rate) * prior_strength
    return ClutchPrior(
        alpha=alpha,
        beta=beta,
        population_rate=population_rate,
        prior_strength=prior_strength,
    )


def bayesian_rate(
    successes: int,
    failures: int,
    prior: ClutchPrior,
) -> float | None:
    total = successes + failures
    if total == 0:
        return None
    denominator = total + prior.alpha + prior.beta
    if denominator == 0:
        return None
    return (successes + prior.alpha) / denominator


def compute_bayesian_clutch(
    clutch_wins: int | None,
    clutch_attempts: int | None,
    prior: ClutchPrior,
) -> BayesianClutchEstimate:
    if clutch_attempts is None or clutch_attempts == 0:
        return BayesianClutchEstimate(
            raw_clutch_rate=None,
            bayesian_clutch_rate=None,
            clutch_attempts=clutch_attempts,
            clutch_wins=clutch_wins,
            effective_sample_size=None,
            prior_strength=prior.prior_strength,
        )

    wins = clutch_wins or 0
    raw_rate = safe_ratio(wins, clutch_attempts)
    denominator = clutch_attempts + prior.alpha + prior.beta
    bayesian_rate = (wins + prior.alpha) / denominator if denominator > 0 else None

    return BayesianClutchEstimate(
        raw_clutch_rate=raw_rate,
        bayesian_clutch_rate=bayesian_rate,
        clutch_attempts=clutch_attempts,
        clutch_wins=clutch_wins,
        effective_sample_size=denominator,
        prior_strength=prior.prior_strength,
    )
