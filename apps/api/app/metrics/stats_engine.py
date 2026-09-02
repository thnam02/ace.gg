from __future__ import annotations

from uuid import UUID

from app.metrics.derived import aggregate_raw, compute_derived
from app.models import PlayerMapStats
from app.schemas.stats import (
    AggregateStatsRaw,
    MapStatsFeatures,
    MapStatsRaw,
    PlayerStatsAggregate,
)


class StatsEngine:
    """Derive per-map and aggregate player features from raw map stats."""

    def from_raw(self, raw: MapStatsRaw, *, match_map_id: UUID | None = None) -> MapStatsFeatures:
        return MapStatsFeatures(
            raw=raw,
            derived=compute_derived(raw),
            match_map_id=match_map_id,
        )

    def from_player_map_stats(self, stats: PlayerMapStats) -> MapStatsFeatures:
        return self.from_raw(player_map_stats_to_raw(stats), match_map_id=stats.match_map_id)

    def aggregate(
        self,
        rows: list[MapStatsRaw],
        *,
        maps: list[MapStatsFeatures] | None = None,
    ) -> PlayerStatsAggregate:
        aggregated = aggregate_raw(rows)
        derived_input = MapStatsRaw(
            rounds=aggregated.rounds,
            kills=aggregated.kills,
            deaths=aggregated.deaths,
            assists=aggregated.assists,
            first_kills=aggregated.first_kills,
            first_deaths=aggregated.first_deaths,
            clutch_wins=aggregated.clutch_wins,
            clutch_attempts=aggregated.clutch_attempts,
        )
        return PlayerStatsAggregate(
            raw=AggregateStatsRaw(
                rounds=aggregated.rounds,
                maps_played=len(rows),
                kills=aggregated.kills,
                deaths=aggregated.deaths,
                assists=aggregated.assists,
                first_kills=aggregated.first_kills,
                first_deaths=aggregated.first_deaths,
                weighted_adr=aggregated.adr,
                weighted_kast=aggregated.kast_pct,
                weighted_acs=aggregated.acs,
                clutch_wins=aggregated.clutch_wins,
                clutch_attempts=aggregated.clutch_attempts,
            ),
            derived=compute_derived(derived_input),
            maps=maps or [],
        )

    def aggregate_features(self, features: list[MapStatsFeatures]) -> PlayerStatsAggregate:
        return self.aggregate([feature.raw for feature in features], maps=features)


def player_map_stats_to_raw(stats: PlayerMapStats) -> MapStatsRaw:
    return MapStatsRaw(
        rounds=stats.rounds,
        kills=stats.kills,
        deaths=stats.deaths,
        assists=stats.assists,
        first_kills=stats.first_kills,
        first_deaths=stats.first_deaths,
        adr=stats.adr,
        kast_pct=stats.kast_pct,
        clutch_wins=stats.clutch_wins,
        clutch_attempts=stats.clutch_attempts,
        acs=stats.acs,
    )
