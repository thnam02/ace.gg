from __future__ import annotations

from dataclasses import dataclass

from app.metrics.cir_v01 import CIR_V01_COMPONENTS, CIR_V01_FEATURE_NAMES


@dataclass(frozen=True)
class CIRModelCoefficients:
    intercept: float
    coefficients: dict[str, float]

    def to_dict(self) -> dict[str, float | dict[str, float]]:
        return {"intercept": self.intercept, "coefficients": self.coefficients}

    @classmethod
    def from_dict(cls, data: dict[str, float | dict[str, float]]) -> CIRModelCoefficients:
        coefficients_raw = data["coefficients"]
        assert isinstance(coefficients_raw, dict)
        coefficients = {str(key): float(value) for key, value in coefficients_raw.items()}
        intercept_raw = data["intercept"]
        return CIRModelCoefficients(
            intercept=float(intercept_raw) if isinstance(intercept_raw, int | float) else 0.0,
            coefficients=coefficients,
        )


@dataclass(frozen=True)
class CIRComponentContributions:
    combat: float
    opening: float
    team: float
    clutch: float

    @property
    def total(self) -> float:
        return self.combat + self.opening + self.team + self.clutch


def compute_raw_cir(
    standardized_features: dict[str, float],
    coefficients: CIRModelCoefficients,
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> float:
    total = 0.0
    for name in feature_names:
        total += coefficients.coefficients.get(name, 0.0) * standardized_features.get(name, 0.0)
    return total


def compute_component_contributions(
    standardized_features: dict[str, float],
    coefficients: CIRModelCoefficients,
) -> CIRComponentContributions:
    def component_sum(component: str) -> float:
        total = 0.0
        for name in CIR_V01_COMPONENTS[component]:
            total += coefficients.coefficients.get(name, 0.0) * standardized_features.get(name, 0.0)
        return total

    return CIRComponentContributions(
        combat=component_sum("combat"),
        opening=component_sum("opening"),
        team=component_sum("team"),
        clutch=component_sum("clutch"),
    )


def round_weighted_mean(values: list[tuple[float, int]]) -> float | None:
    total_rounds = sum(weight for _, weight in values)
    if total_rounds == 0:
        return None
    return sum(value * weight for value, weight in values) / total_rounds


def apply_shrinkage(
    raw_cir: float,
    rounds: int,
    reference_mean: float,
    shrinkage_k: float,
) -> float:
    if rounds <= 0:
        return reference_mean
    weight = rounds / (rounds + shrinkage_k)
    return weight * raw_cir + (1.0 - weight) * reference_mean


def empirical_cdf(value: float, reference_values: list[float]) -> float:
    if not reference_values:
        return 50.0
    sorted_values = sorted(reference_values)
    count = sum(1 for item in sorted_values if item <= value)
    return 100.0 * count / len(sorted_values)


def build_team_delta_vector(
    team_a_features: list[dict[str, float]],
    team_b_features: list[dict[str, float]],
    feature_names: tuple[str, ...] = CIR_V01_FEATURE_NAMES,
) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for name in feature_names:
        team_a_sum = sum(features.get(name, 0.0) for features in team_a_features)
        team_b_sum = sum(features.get(name, 0.0) for features in team_b_features)
        deltas[name] = team_a_sum - team_b_sum
    return deltas
