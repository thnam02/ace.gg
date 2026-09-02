from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.metrics.derived import aggregate_raw, compute_derived, weighted_average
from app.metrics.stats_engine import StatsEngine, player_map_stats_to_raw
from app.models import Match, Player, PlayerMapStats, PlayerTeamHistory
from app.schemas.player_api import (
    MapAggregatePerformance,
    MatchMapPerformance,
    PlayerCompareEntry,
    PlayerCompareResponse,
    PlayerDashboardStats,
    PlayerDetailResponse,
    PlayerIdentity,
    PlayerMapsResponse,
    PlayerMatchesResponse,
    PlayerStatsResponse,
    PlayerSummary,
    StatsQueryParams,
    TeamRef,
)
from app.schemas.stats import MapStatsRaw, PlayerStatsAggregate
from app.services.stats_engine_service import StatsEngineService


class PlayerNotFoundError(Exception):
    pass


class PlayerQueryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._stats_engine = StatsEngine()
        self._stats_service = StatsEngineService(session, engine=self._stats_engine)

    def list_players(self, filters: StatsQueryParams) -> list[PlayerSummary]:
        players = self._players_with_stats()
        all_rows = self._stats_service.load_player_map_stats(
            None,
            event_id=filters.event_id,
            vlr_event_id=filters.vlr_event_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            min_rounds=filters.min_rounds,
            player_ids=[player.id for player in players],
        )
        rows_by_player = _group_rows_by_player(all_rows)

        summaries: list[PlayerSummary] = []
        for player in players:
            rows = rows_by_player.get(player.id, [])
            aggregate = self._aggregate_rows(rows)
            summaries.append(self._to_summary(player, rows, aggregate))
        return sorted(summaries, key=lambda item: item.handle.lower())

    def get_player(self, player_ref: str, filters: StatsQueryParams) -> PlayerDetailResponse:
        player = self._require_player(player_ref)
        rows = self._load_rows(player.id, filters)
        aggregate = self._aggregate_rows(rows)
        identity = self._to_identity(player)
        return PlayerDetailResponse(
            player=identity,
            stats=self._dashboard_stats(rows, aggregate),
            aggregate=aggregate,
        )

    def get_player_stats(self, player_ref: str, filters: StatsQueryParams) -> PlayerStatsResponse:
        player = self._require_player(player_ref)
        aggregate = self._aggregate_rows(self._load_rows(player.id, filters))
        return PlayerStatsResponse(player_id=str(player.id), aggregate=aggregate)

    def get_player_matches(
        self,
        player_ref: str,
        filters: StatsQueryParams,
        *,
        limit: int = 20,
    ) -> PlayerMatchesResponse:
        player = self._require_player(player_ref)
        rows = self._load_rows(player.id, filters)[:limit]
        performances = [self._to_match_performance(row) for row in rows]
        return PlayerMatchesResponse(player_id=str(player.id), performances=performances)

    def get_player_maps(self, player_ref: str, filters: StatsQueryParams) -> PlayerMapsResponse:
        player = self._require_player(player_ref)
        rows = self._load_rows(player.id, filters)
        grouped: dict[str, list[PlayerMapStats]] = defaultdict(list)
        for row in rows:
            grouped[row.match_map.map_name].append(row)

        map_stats: list[MapAggregatePerformance] = []
        for map_name in sorted(grouped):
            map_rows = grouped[map_name]
            raw_rows = [player_map_stats_to_raw(row) for row in map_rows]
            agg_raw = aggregate_raw(raw_rows)
            derived_input = MapStatsRaw(
                rounds=agg_raw.rounds,
                kills=agg_raw.kills,
                deaths=agg_raw.deaths,
                assists=agg_raw.assists,
                first_kills=agg_raw.first_kills,
                first_deaths=agg_raw.first_deaths,
                clutch_wins=agg_raw.clutch_wins,
                clutch_attempts=agg_raw.clutch_attempts,
            )
            map_stats.append(
                MapAggregatePerformance(
                    map_name=map_name,
                    maps_played=len(map_rows),
                    rounds=agg_raw.rounds,
                    raw=agg_raw,
                    derived=compute_derived(derived_input),
                )
            )

        return PlayerMapsResponse(player_id=str(player.id), maps=map_stats)

    def compare_players(
        self,
        player_refs: list[str],
        filters: StatsQueryParams,
    ) -> PlayerCompareResponse:
        players: list[Player] = []
        unknown_ids: list[str] = []
        for ref in player_refs:
            try:
                players.append(self._require_player(ref))
            except PlayerNotFoundError:
                unknown_ids.append(ref)

        rows_by_player: dict[UUID, list[PlayerMapStats]] = {}
        if players:
            all_rows = self._stats_service.load_player_map_stats(
                None,
                event_id=filters.event_id,
                vlr_event_id=filters.vlr_event_id,
                start_date=filters.start_date,
                end_date=filters.end_date,
                min_rounds=filters.min_rounds,
                player_ids=[player.id for player in players],
            )
            rows_by_player = _group_rows_by_player(all_rows)

        entries: list[PlayerCompareEntry] = []
        sparse: list[str] = []
        for player in players:
            rows = rows_by_player.get(player.id, [])
            if not rows:
                sparse.append(player.handle)
            aggregate = self._aggregate_rows(rows)
            entries.append(
                PlayerCompareEntry(
                    player=self._to_identity(player),
                    stats=self._dashboard_stats(rows, aggregate),
                    aggregate=aggregate,
                )
            )

        notes = "Side-by-side stats from ingested map data."
        if sparse:
            notes = f"{notes} Sparse sample: {', '.join(sparse)}."
        if unknown_ids:
            notes = f"{notes} Unknown player IDs: {', '.join(unknown_ids)}."
        return PlayerCompareResponse(players=entries, notes=notes)

    def _players_with_stats(self) -> list[Player]:
        return list(
            self._session.scalars(
                select(Player)
                .join(PlayerMapStats, PlayerMapStats.player_id == Player.id)
                .distinct()
                .options(
                    selectinload(Player.team_history).selectinload(PlayerTeamHistory.team),
                )
            ).all()
        )

    def _require_player(self, player_ref: str) -> Player:
        player = self._resolve_player(player_ref)
        if player is None:
            raise PlayerNotFoundError(player_ref)
        return player

    def _resolve_player(self, player_ref: str) -> Player | None:
        try:
            player_uuid = UUID(player_ref)
            player = self._session.scalar(
                select(Player)
                .where(Player.id == player_uuid)
                .options(selectinload(Player.team_history).selectinload(PlayerTeamHistory.team))
            )
            if player is not None:
                return player
        except ValueError:
            pass

        if player_ref.isdigit():
            player = self._session.scalar(
                select(Player)
                .where(Player.vlr_player_id == int(player_ref))
                .options(selectinload(Player.team_history).selectinload(PlayerTeamHistory.team))
            )
            if player is not None:
                return player
        return None

    def _load_rows(self, player_id: UUID, filters: StatsQueryParams) -> list[PlayerMapStats]:
        return self._stats_service.load_player_map_stats(
            player_id,
            event_id=filters.event_id,
            vlr_event_id=filters.vlr_event_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            min_rounds=filters.min_rounds,
        )

    def _aggregate_rows(self, rows: list[PlayerMapStats]) -> PlayerStatsAggregate:
        if not rows:
            return self._stats_engine.aggregate([])
        features = [self._stats_engine.from_player_map_stats(row) for row in rows]
        return self._stats_engine.aggregate_features(features)

    def _to_summary(
        self,
        player: Player,
        rows: list[PlayerMapStats],
        aggregate: PlayerStatsAggregate,
    ) -> PlayerSummary:
        return PlayerSummary(
            id=str(player.id),
            vlr_player_id=player.vlr_player_id,
            handle=player.handle,
            real_name=player.real_name,
            country=player.country,
            team=self._current_team_ref(player),
            stats=self._dashboard_stats(rows, aggregate),
        )

    def _to_identity(self, player: Player) -> PlayerIdentity:
        return PlayerIdentity(
            id=str(player.id),
            vlr_player_id=player.vlr_player_id,
            handle=player.handle,
            real_name=player.real_name,
            country=player.country,
            team=self._current_team_ref(player),
        )

    def _current_team_ref(self, player: Player) -> TeamRef | None:
        current = next(
            (entry for entry in player.team_history if entry.is_current),
            None,
        )
        if current is None and player.team_history:
            current = max(player.team_history, key=lambda entry: entry.joined_at or "")
        if current is None:
            return None
        team = current.team
        return TeamRef(
            id=str(team.id),
            vlr_team_id=team.vlr_team_id,
            name=team.name,
            tag=team.tag,
            region=team.region,
        )

    def _dashboard_stats(
        self,
        rows: list[PlayerMapStats],
        aggregate: PlayerStatsAggregate,
    ) -> PlayerDashboardStats:
        return PlayerDashboardStats(
            matches=_distinct_matches(rows),
            maps_played=aggregate.raw.maps_played,
            rounds=aggregate.raw.rounds,
            acs=aggregate.raw.weighted_acs,
            kd=_kill_death_ratio(aggregate.raw.kills, aggregate.raw.deaths),
            hs_percent=_weighted_headshot(rows),
            adr=aggregate.raw.weighted_adr,
            win_rate=_win_rate(rows),
        )

    def _to_match_performance(self, row: PlayerMapStats) -> MatchMapPerformance:
        match = row.match_map.match
        opponent = _opponent_team_name(match, row.team_id)
        features = self._stats_engine.from_player_map_stats(row)
        return MatchMapPerformance(
            match_id=str(match.id),
            vlr_match_id=match.vlr_match_id,
            match_map_id=str(row.match_map_id),
            map_name=row.match_map.map_name,
            map_number=row.match_map.map_number,
            played_at=match.played_at.isoformat() if match.played_at else None,
            event_name=match.event.name if match.event else None,
            opponent_team=opponent,
            won=_map_won(match, row.team_id),
            agent_name=row.agent.name if row.agent else None,
            raw=features.raw,
            derived=features.derived,
        )


def _group_rows_by_player(rows: list[PlayerMapStats]) -> dict[UUID, list[PlayerMapStats]]:
    grouped: dict[UUID, list[PlayerMapStats]] = defaultdict(list)
    for row in rows:
        grouped[row.player_id].append(row)
    return grouped


def _distinct_matches(rows: list[PlayerMapStats]) -> int:
    return len({row.match_map.match_id for row in rows})


def _kill_death_ratio(kills: int, deaths: int) -> float | None:
    if deaths == 0:
        return float(kills) if kills else None
    return kills / deaths


def _weighted_headshot(rows: list[PlayerMapStats]) -> float | None:
    values = [(row.headshot_pct, row.rounds) for row in rows if row.headshot_pct is not None]
    return weighted_average(values)


def _win_rate(rows: list[PlayerMapStats]) -> float | None:
    won_matches: set[UUID] = set()
    played_matches: set[UUID] = set()
    for row in rows:
        match = row.match_map.match
        played_matches.add(match.id)
        if match.winner_team_id is not None and match.winner_team_id == row.team_id:
            won_matches.add(match.id)
    if not played_matches:
        return None
    return len(won_matches) / len(played_matches)


def _opponent_team_name(match: Match, team_id: UUID) -> str | None:
    if match.team_a_id == team_id:
        return match.team_b.name
    if match.team_b_id == team_id:
        return match.team_a.name
    return None


def _map_won(match: Match, team_id: UUID) -> bool | None:
    if match.winner_team_id is None:
        return None
    return match.winner_team_id == team_id
