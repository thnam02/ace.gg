from __future__ import annotations

from app.schemas.stats import MapStatsDerived, MapStatsRaw


def safe_ratio(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def compute_derived(raw: MapStatsRaw) -> MapStatsDerived:
    rounds = raw.rounds
    opening_duels = raw.first_kills + raw.first_deaths

    return MapStatsDerived(
        kpr=safe_ratio(raw.kills, rounds),
        dpr=safe_ratio(raw.deaths, rounds),
        apr=safe_ratio(raw.assists, rounds),
        fkpr=safe_ratio(raw.first_kills, rounds),
        fdpr=safe_ratio(raw.first_deaths, rounds),
        opening_frequency=safe_ratio(opening_duels, rounds),
        opening_efficiency=safe_ratio(raw.first_kills, opening_duels),
        raw_clutch_rate=_raw_clutch_rate(raw.clutch_wins, raw.clutch_attempts),
    )


def _raw_clutch_rate(clutch_wins: int | None, clutch_attempts: int | None) -> float | None:
    if clutch_attempts is None or clutch_attempts == 0:
        return None
    if clutch_wins is None:
        return None
    return clutch_wins / clutch_attempts


def weighted_average(values: list[tuple[float, int]]) -> float | None:
    total_weight = sum(weight for _, weight in values)
    if total_weight == 0:
        return None
    return sum(value * weight for value, weight in values) / total_weight


def aggregate_raw(rows: list[MapStatsRaw]) -> MapStatsRaw:
    if not rows:
        return MapStatsRaw(
            rounds=0,
            kills=0,
            deaths=0,
            assists=0,
            first_kills=0,
            first_deaths=0,
        )

    adr_values = [(row.adr, row.rounds) for row in rows if row.adr is not None]
    kast_values = [(row.kast_pct, row.rounds) for row in rows if row.kast_pct is not None]
    acs_values = [(row.acs, row.rounds) for row in rows if row.acs is not None]

    clutch_wins_total: int | None = None
    clutch_attempts_total: int | None = None
    if any(row.clutch_wins is not None for row in rows):
        clutch_wins_total = sum(row.clutch_wins or 0 for row in rows)
    if any(row.clutch_attempts is not None for row in rows):
        clutch_attempts_total = sum(row.clutch_attempts or 0 for row in rows)

    return MapStatsRaw(
        rounds=sum(row.rounds for row in rows),
        kills=sum(row.kills for row in rows),
        deaths=sum(row.deaths for row in rows),
        assists=sum(row.assists for row in rows),
        first_kills=sum(row.first_kills for row in rows),
        first_deaths=sum(row.first_deaths for row in rows),
        adr=weighted_average(adr_values),
        kast_pct=weighted_average(kast_values),
        acs=weighted_average(acs_values),
        clutch_wins=clutch_wins_total,
        clutch_attempts=clutch_attempts_total,
    )
