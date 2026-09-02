from __future__ import annotations

from app.metrics.cir.config import (
    ESTABLISHED_ROUNDS,
    LOW_SAMPLE_ROUNDS,
    SHRINKAGE_K,
    ReliabilityLabel,
    SampleStatus,
)


def sample_status_for_rounds(rounds: int) -> SampleStatus:
    if rounds < LOW_SAMPLE_ROUNDS:
        return SampleStatus.LOW_SAMPLE
    if rounds < ESTABLISHED_ROUNDS:
        return SampleStatus.PROVISIONAL
    return SampleStatus.ESTABLISHED


def reliability_for_rounds(rounds: int) -> ReliabilityLabel:
    status = sample_status_for_rounds(rounds)
    if status == SampleStatus.LOW_SAMPLE:
        return ReliabilityLabel.LOW
    if status == SampleStatus.PROVISIONAL:
        return ReliabilityLabel.MEDIUM
    return ReliabilityLabel.HIGH


def reliability_pct(rounds: int) -> float:
    if rounds <= 0:
        return 0.0
    return min(100.0, rounds / ESTABLISHED_ROUNDS * 100.0)


def sample_weight(rounds: int, shrinkage_k: float = SHRINKAGE_K) -> float:
    if rounds <= 0:
        return 0.0
    return rounds / (rounds + shrinkage_k)
