from __future__ import annotations

from dataclasses import dataclass

from app.models import PlayerMapStats

DEFAULT_MIN_CLUTCH_COVERAGE = 0.5
CLUTCH_FEATURE_NAME = "clutch_rate_adjusted"


@dataclass
class ClutchCoverage:
    clutch_available_rows: int
    clutch_missing_rows: int
    clutch_coverage_pct: float
    clutch_feature_enabled: bool

    @property
    def total_rows(self) -> int:
        return self.clutch_available_rows + self.clutch_missing_rows


def row_has_clutch(stats: PlayerMapStats) -> bool:
    return stats.clutch_attempts is not None


def measure_clutch_coverage(
    stats: list[PlayerMapStats],
    *,
    min_coverage: float = DEFAULT_MIN_CLUTCH_COVERAGE,
) -> ClutchCoverage:
    available = sum(1 for row in stats if row_has_clutch(row))
    total = len(stats)
    missing = total - available
    coverage = (available / total) if total else 0.0
    return ClutchCoverage(
        clutch_available_rows=available,
        clutch_missing_rows=missing,
        clutch_coverage_pct=100.0 * coverage,
        clutch_feature_enabled=coverage >= min_coverage if total else False,
    )
