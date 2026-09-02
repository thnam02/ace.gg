from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.metrics.mir.mir_config import (
    APR_CONTEXT,
    DPR_CONTEXT,
    KAST_CONTEXT,
    KPR_CONTEXT,
    OPENING_EFFICIENCY_CONTEXT,
    OPENING_EFFICIENCY_PRIOR_K,
    OPENING_EFFICIENCY_UNIQUE,
    OPENING_FREQUENCY_CONTEXT,
    OPENING_FREQUENCY_UNIQUE,
    ROUND_PARTICIPATION,
    SUPPORT_ASSIST,
)


def _require_float(value: object) -> float:
    assert isinstance(value, int | float)
    return float(value)


@dataclass(frozen=True)
class LinearResidualizer:
    intercept: float
    coefficients: dict[str, float]
    predictors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "intercept": self.intercept,
            "coefficients": dict(self.coefficients),
            "predictors": list(self.predictors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LinearResidualizer:
        raw_coefs = data["coefficients"]
        assert isinstance(raw_coefs, dict)
        predictors_raw = data["predictors"]
        assert isinstance(predictors_raw, list)
        intercept = data["intercept"]
        assert isinstance(intercept, int | float)
        coefficients: dict[str, float] = {}
        for key, value in raw_coefs.items():
            assert isinstance(value, int | float)
            coefficients[str(key)] = float(value)
        return cls(
            intercept=float(intercept),
            coefficients=coefficients,
            predictors=tuple(str(item) for item in predictors_raw),
        )

    def predict(self, predictors: dict[str, float | None]) -> float:
        total = self.intercept
        for name in self.predictors:
            value = predictors.get(name)
            total += self.coefficients.get(name, 0.0) * (0.0 if value is None else float(value))
        return total

    def residual(self, observed: float | None, predictors: dict[str, float | None]) -> float | None:
        if observed is None:
            return None
        return float(observed) - self.predict(predictors)


@dataclass(frozen=True)
class MirResidualizers:
    apr: LinearResidualizer
    kast: LinearResidualizer
    opening_efficiency: LinearResidualizer
    opening_efficiency_prior_k: float = OPENING_EFFICIENCY_PRIOR_K

    def to_dict(self) -> dict[str, object]:
        return {
            "apr": self.apr.to_dict(),
            "kast": self.kast.to_dict(),
            "opening_efficiency": self.opening_efficiency.to_dict(),
            "opening_efficiency_prior_k": self.opening_efficiency_prior_k,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MirResidualizers:
        apr_raw = data["apr"]
        kast_raw = data["kast"]
        oe_raw = data["opening_efficiency"]
        assert isinstance(apr_raw, dict)
        assert isinstance(kast_raw, dict)
        assert isinstance(oe_raw, dict)
        return cls(
            apr=LinearResidualizer.from_dict(apr_raw),
            kast=LinearResidualizer.from_dict(kast_raw),
            opening_efficiency=LinearResidualizer.from_dict(oe_raw),
            opening_efficiency_prior_k=_require_float(data.get("opening_efficiency_prior_k", 8.0)),
        )


def shrink_rate(
    observed: float | None,
    expected: float | None,
    attempts: int,
    prior_k: float,
) -> float | None:
    """Opportunity-weighted shrink of a proportion toward a context expectation."""
    if observed is None:
        return expected
    if attempts <= 0 or prior_k <= 0:
        return expected if attempts <= 0 else observed
    if expected is None:
        return observed
    weight = attempts / (attempts + prior_k)
    return weight * observed + (1.0 - weight) * expected


def damped_context_residual(
    observed: float | None,
    expected: float | None,
    attempts: int,
    prior_k: float,
) -> float | None:
    shrunk = shrink_rate(observed, expected, attempts, prior_k)
    if shrunk is None or expected is None:
        return None if expected is None else shrunk
    return shrunk - expected


def fit_linear_residualizer(
    observed: list[float | None],
    predictor_rows: list[dict[str, float | None]],
    predictors: tuple[str, ...],
) -> LinearResidualizer:
    ys: list[float] = []
    xs: list[list[float]] = []
    for value, row in zip(observed, predictor_rows, strict=True):
        if value is None:
            continue
        xs.append([1.0] + [float(row.get(name) or 0.0) for name in predictors])
        ys.append(float(value))
    if len(ys) < 2:
        return LinearResidualizer(
            intercept=0.0,
            coefficients={name: 0.0 for name in predictors},
            predictors=predictors,
        )
    design = np.asarray(xs, dtype=np.float64)
    target = np.asarray(ys, dtype=np.float64)
    coeffs, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
    coefficient_map = {name: float(coeffs[index + 1]) for index, name in enumerate(predictors)}
    return LinearResidualizer(
        intercept=float(coeffs[0]),
        coefficients=coefficient_map,
        predictors=predictors,
    )


def fit_mir_residualizers(
    train_rows: list[dict[str, float | None]],
    *,
    opening_attempts: list[int] | None = None,
    opening_efficiency_prior_k: float = OPENING_EFFICIENCY_PRIOR_K,
) -> MirResidualizers:
    """Fit unique residualizers on TRAIN rows only. Combat is already context-adjusted."""
    combat = (KPR_CONTEXT, DPR_CONTEXT)
    apr_model = fit_linear_residualizer(
        [row.get(APR_CONTEXT) for row in train_rows],
        train_rows,
        combat,
    )
    apr_unique_rows: list[dict[str, float | None]] = []
    kast_observed: list[float | None] = []
    for row in train_rows:
        updated = dict(row)
        updated[SUPPORT_ASSIST] = apr_model.residual(row.get(APR_CONTEXT), row)
        apr_unique_rows.append(updated)
        kast_observed.append(row.get(KAST_CONTEXT))
    kast_predictors = combat + (SUPPORT_ASSIST,)
    kast_model = fit_linear_residualizer(kast_observed, apr_unique_rows, kast_predictors)

    oe_targets: list[float | None] = []
    if opening_attempts is None:
        opening_attempts = [0] * len(train_rows)
    for row, attempts in zip(train_rows, opening_attempts, strict=True):
        raw = row.get(OPENING_EFFICIENCY_CONTEXT)
        # Context residual is already observed-expected; damp by opportunity count.
        if raw is None:
            oe_targets.append(None)
            continue
        weight = attempts / (attempts + opening_efficiency_prior_k) if attempts > 0 else 0.0
        oe_targets.append(weight * float(raw))
    oe_model = fit_linear_residualizer(oe_targets, train_rows, combat)
    return MirResidualizers(
        apr=apr_model,
        kast=kast_model,
        opening_efficiency=oe_model,
        opening_efficiency_prior_k=opening_efficiency_prior_k,
    )


def apply_mir_residualizers(
    row: dict[str, float | None],
    models: MirResidualizers,
    *,
    opening_attempts: int = 0,
) -> dict[str, float | None]:
    """Apply frozen residualizers. Validation/test must not refit."""
    updated = dict(row)
    combat_predictors = {
        KPR_CONTEXT: row.get(KPR_CONTEXT),
        DPR_CONTEXT: row.get(DPR_CONTEXT),
    }
    apr_unique = models.apr.residual(row.get(APR_CONTEXT), combat_predictors)
    updated[SUPPORT_ASSIST] = apr_unique
    kast_predictors = {**combat_predictors, SUPPORT_ASSIST: apr_unique}
    updated[ROUND_PARTICIPATION] = models.kast.residual(row.get(KAST_CONTEXT), kast_predictors)
    updated[OPENING_FREQUENCY_UNIQUE] = row.get(OPENING_FREQUENCY_CONTEXT)
    oe_context = row.get(OPENING_EFFICIENCY_CONTEXT)
    if oe_context is None:
        damped = None
    elif opening_attempts <= 0:
        damped = 0.0
    else:
        weight = opening_attempts / (opening_attempts + models.opening_efficiency_prior_k)
        damped = weight * float(oe_context)
    updated[OPENING_EFFICIENCY_UNIQUE] = models.opening_efficiency.residual(
        damped,
        combat_predictors,
    )
    return updated
