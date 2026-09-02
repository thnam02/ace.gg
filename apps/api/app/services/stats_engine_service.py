from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.metrics.stats_engine import StatsEngine
from app.models import Event, Match, MatchMap, PlayerMapStats
from app.schemas.stats import MapStatsFeatures, PlayerStatsAggregate, PlayerStatsScope


class StatsEngineService:
    """Load PlayerMapStats rows and compute derived features."""

    def __init__(self, session: Session, *, engine: StatsEngine | None = None) -> None:
        self._session = session
        self._engine = engine or StatsEngine()

    def for_player_map_stats(self, stats: PlayerMapStats) -> MapStatsFeatures:
        return self._engine.from_player_map_stats(stats)

    def for_player(
        self,
        player_id: UUID,
        *,
        event_id: UUID | None = None,
        vlr_event_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rounds: int | None = None,
    ) -> PlayerStatsAggregate:
        rows = self._load_player_map_stats(
            player_id,
            event_id=event_id,
            vlr_event_id=vlr_event_id,
            start_date=start_date,
            end_date=end_date,
            min_rounds=min_rounds,
        )
        features = [self._engine.from_player_map_stats(row) for row in rows]
        return self._engine.aggregate_features(features)

    def for_scope(self, scope: PlayerStatsScope) -> PlayerStatsAggregate:
        return self.for_player(
            scope.player_id,
            event_id=scope.event_id,
            vlr_event_id=scope.vlr_event_id,
            start_date=scope.start_date,
            end_date=scope.end_date,
        )

    def load_player_map_stats(
        self,
        player_id: UUID | None,
        *,
        event_id: UUID | None = None,
        vlr_event_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rounds: int | None = None,
        player_ids: list[UUID] | None = None,
    ) -> list[PlayerMapStats]:
        return self._load_player_map_stats(
            player_id,
            event_id=event_id,
            vlr_event_id=vlr_event_id,
            start_date=start_date,
            end_date=end_date,
            min_rounds=min_rounds,
            player_ids=player_ids,
        )

    def _load_player_map_stats(
        self,
        player_id: UUID | None,
        *,
        event_id: UUID | None,
        vlr_event_id: int | None,
        start_date: date | None,
        end_date: date | None,
        min_rounds: int | None = None,
        player_ids: list[UUID] | None = None,
    ) -> list[PlayerMapStats]:
        query: Select[tuple[PlayerMapStats]] = (
            select(PlayerMapStats)
            .join(MatchMap, PlayerMapStats.match_map_id == MatchMap.id)
            .join(Match, MatchMap.match_id == Match.id)
            .options(
                selectinload(PlayerMapStats.match_map)
                .selectinload(MatchMap.match)
                .selectinload(Match.event),
                selectinload(PlayerMapStats.match_map)
                .selectinload(MatchMap.match)
                .selectinload(Match.team_a),
                selectinload(PlayerMapStats.match_map)
                .selectinload(MatchMap.match)
                .selectinload(Match.team_b),
                selectinload(PlayerMapStats.agent),
                selectinload(PlayerMapStats.team),
                selectinload(PlayerMapStats.player),
            )
            .order_by(Match.played_at.desc(), MatchMap.map_number)
        )

        if player_id is not None:
            query = query.where(PlayerMapStats.player_id == player_id)
        if player_ids is not None:
            query = query.where(PlayerMapStats.player_id.in_(player_ids))

        if event_id is not None:
            query = query.where(Match.event_id == event_id)
        if vlr_event_id is not None:
            query = query.join(Event, Match.event_id == Event.id).where(
                Event.vlr_event_id == vlr_event_id
            )
        if start_date is not None:
            query = query.where(
                Match.played_at >= datetime.combine(start_date, time.min, tzinfo=UTC)
            )
        if end_date is not None:
            query = query.where(
                Match.played_at <= datetime.combine(end_date, time.max, tzinfo=UTC)
            )
        if min_rounds is not None:
            query = query.where(PlayerMapStats.rounds >= min_rounds)

        return list(self._session.scalars(query).all())
