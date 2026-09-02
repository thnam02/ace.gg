from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdrRegressionModel:
    intercept: float
    slope: float
    sample_count: int

    def predict(self, kpr: float) -> float:
        return self.intercept + self.slope * kpr

    def expected_and_residual(
        self,
        adr: float | None,
        kpr: float | None,
    ) -> tuple[float | None, float | None]:
        if kpr is None:
            return None, None
        expected = self.predict(kpr)
        if adr is None:
            return expected, None
        return expected, adr - expected


def train_adr_regression(observations: list[tuple[float, float]]) -> AdrRegressionModel:
    if not observations:
        return AdrRegressionModel(intercept=0.0, slope=0.0, sample_count=0)

    if len(observations) == 1:
        adr = observations[0][1]
        return AdrRegressionModel(intercept=adr, slope=0.0, sample_count=1)

    kprs = [item[0] for item in observations]
    adrs = [item[1] for item in observations]
    mean_kpr = sum(kprs) / len(kprs)
    mean_adr = sum(adrs) / len(adrs)

    numerator = sum((kpr - mean_kpr) * (adr - mean_adr) for kpr, adr in observations)
    denominator = sum((kpr - mean_kpr) ** 2 for kpr in kprs)

    if denominator == 0:
        return AdrRegressionModel(intercept=mean_adr, slope=0.0, sample_count=len(observations))

    slope = numerator / denominator
    intercept = mean_adr - slope * mean_kpr
    return AdrRegressionModel(intercept=intercept, slope=slope, sample_count=len(observations))
