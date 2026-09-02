from __future__ import annotations

from dataclasses import dataclass

from app.metrics.cir_v01 import CIR_V01_FEATURE_NAMES

MIN_STD = 1e-8


@dataclass(frozen=True)
class StandardizationParams:
    means: dict[str, float]
    stds: dict[str, float]

    def to_dict(self) -> dict[str, dict[str, float]]:
        return {"means": self.means, "stds": self.stds}

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, float]]) -> StandardizationParams:
        return StandardizationParams(means=data["means"], stds=data["stds"])


def fit_standardization(
    observations: list[dict[str, float | None]],
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> StandardizationParams:
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    for name in feature_names:
        values = [obs[name] for obs in observations if obs.get(name) is not None]
        if not values:
            means[name] = 0.0
            stds[name] = 1.0
            continue
        float_values: list[float] = []
        for obs in observations:
            value = obs.get(name)
            if value is not None:
                float_values.append(float(value))
        mean = sum(float_values) / len(float_values)
        variance = sum((value - mean) ** 2 for value in float_values) / len(float_values)
        std = variance**0.5
        means[name] = mean
        stds[name] = std if std > MIN_STD else 1.0
    return StandardizationParams(means=means, stds=stds)


def standardize_features(
    features: dict[str, float | None],
    params: StandardizationParams,
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> dict[str, float]:
    standardized: dict[str, float] = {}
    for name in feature_names:
        value = features.get(name)
        if value is None:
            standardized[name] = 0.0
            continue
        mean = params.means[name]
        std = params.stds[name]
        standardized[name] = (value - mean) / std
    return standardized
