from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Event, Match, MatchMap, Player, PlayerMapStats, Team
from app.schemas.ingestion import (
    NormalizedAgent,
    NormalizedEvent,
    NormalizedMatchData,
    NormalizedMatchMap,
    NormalizedPlayer,
    NormalizedPlayerMapStats,
    NormalizedTeam,
)


class MatchIngestionService:
    """Upsert normalized match data. Safe to run twice for the same VLR match."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ingest(self, data: NormalizedMatchData) -> Match:
        event = self._upsert_event(data.event)
        team_a = self._upsert_team(data.team_a)
        team_b = self._upsert_team(data.team_b)
        winner = self._team_by_vlr_id(data.winner_vlr_team_id)

        match = self._upsert_match(data, event, team_a, team_b, winner)
        for map_data in data.maps:
            self._upsert_match_map(match, map_data, team_a, team_b)
        self._session.flush()
        return match

    def _upsert_event(self, data: NormalizedEvent) -> Event:
        event = self._session.scalar(select(Event).where(Event.vlr_event_id == data.vlr_event_id))
        if event is None:
            event = Event(vlr_event_id=data.vlr_event_id, name=data.name)
            self._session.add(event)

        event.name = data.name
        if data.region is not None:
            event.region = data.region
        if data.tier is not None:
            event.tier = data.tier
        if data.start_date is not None:
            event.start_date = data.start_date
        if data.end_date is not None:
            event.end_date = data.end_date
        if data.season_year is not None:
            event.season_year = data.season_year
        if data.status is not None:
            event.status = data.status
        self._session.flush()
        return event

    def upsert_event(self, data: NormalizedEvent) -> Event:
        return self._upsert_event(data)

    def upsert_team(self, data: NormalizedTeam) -> Team:
        return self._upsert_team(data)

    def _upsert_team(self, data: NormalizedTeam) -> Team:
        team = self._session.scalar(select(Team).where(Team.vlr_team_id == data.vlr_team_id))
        if team is None:
            team = Team(vlr_team_id=data.vlr_team_id, name=data.name, tag=data.tag)
            self._session.add(team)

        team.name = data.name
        team.tag = data.tag
        team.country = data.country
        team.region = data.region
        self._session.flush()
        return team

    def _upsert_player(self, data: NormalizedPlayer) -> Player:
        player = self._session.scalar(
            select(Player).where(Player.vlr_player_id == data.vlr_player_id)
        )
        if player is None:
            player = Player(vlr_player_id=data.vlr_player_id, handle=data.handle)
            self._session.add(player)

        player.handle = data.handle
        player.real_name = data.real_name
        player.country = data.country
        self._session.flush()
        return player

    def _upsert_agent(self, data: NormalizedAgent) -> Agent:
        agent = self._session.scalar(select(Agent).where(Agent.name == data.name))
        if agent is None:
            agent = Agent(name=data.name, role=data.role)
            self._session.add(agent)
        elif agent.role == "Unknown" and data.role != "Unknown":
            agent.role = data.role
        self._session.flush()
        return agent

    def _upsert_match(
        self,
        data: NormalizedMatchData,
        event: Event,
        team_a: Team,
        team_b: Team,
        winner: Team | None,
    ) -> Match:
        match = self._session.scalar(select(Match).where(Match.vlr_match_id == data.vlr_match_id))
        if match is None:
            match = Match(
                vlr_match_id=data.vlr_match_id,
                event_id=event.id,
                team_a_id=team_a.id,
                team_b_id=team_b.id,
            )
            self._session.add(match)

        match.event_id = event.id
        match.team_a_id = team_a.id
        match.team_b_id = team_b.id
        match.winner_team_id = winner.id if winner is not None else None
        match.played_at = data.played_at
        match.best_of = data.best_of
        match.status = data.status
        self._session.flush()
        return match

    def _upsert_match_map(
        self,
        match: Match,
        data: NormalizedMatchMap,
        team_a: Team,
        team_b: Team,
    ) -> MatchMap:
        match_map = self._session.scalar(
            select(MatchMap).where(
                MatchMap.match_id == match.id,
                MatchMap.map_number == data.map_number,
            )
        )
        winner = None
        if data.winner_vlr_team_id == team_a.vlr_team_id:
            winner = team_a
        elif data.winner_vlr_team_id == team_b.vlr_team_id:
            winner = team_b

        if match_map is None:
            match_map = MatchMap(
                match_id=match.id,
                map_number=data.map_number,
                map_name=data.map_name,
            )
            self._session.add(match_map)

        match_map.map_name = data.map_name
        match_map.team_a_score = data.team_a_score
        match_map.team_b_score = data.team_b_score
        match_map.winner_team_id = winner.id if winner is not None else None
        match_map.rounds_played = data.rounds_played
        self._session.flush()

        for stats in data.player_stats:
            self._upsert_player_map_stats(match_map, stats)
        return match_map

    def _upsert_player_map_stats(
        self,
        match_map: MatchMap,
        data: NormalizedPlayerMapStats,
    ) -> PlayerMapStats:
        player = self._upsert_player(data.player)
        team = self._team_by_vlr_id(data.team_vlr_id)
        if team is None:
            raise ValueError(f"Unknown team VLR ID {data.team_vlr_id} for player stats")
        agent = self._upsert_agent(data.agent)

        stats = self._session.scalar(
            select(PlayerMapStats).where(
                PlayerMapStats.match_map_id == match_map.id,
                PlayerMapStats.player_id == player.id,
            )
        )
        if stats is None:
            stats = PlayerMapStats(
                match_map_id=match_map.id,
                player_id=player.id,
                team_id=team.id,
                agent_id=agent.id,
            )
            self._session.add(stats)

        stats.team_id = team.id
        stats.agent_id = agent.id
        stats.rounds = data.rounds
        stats.kills = data.kills
        stats.deaths = data.deaths
        stats.assists = data.assists
        stats.first_kills = data.first_kills
        stats.first_deaths = data.first_deaths
        stats.adr = data.adr
        stats.kast_pct = data.kast_pct
        stats.acs = data.acs
        stats.vlr_rating = data.vlr_rating
        stats.headshot_pct = data.headshot_pct
        stats.clutch_wins = data.clutch_wins
        stats.clutch_attempts = data.clutch_attempts
        stats.max_kills = data.max_kills
        self._session.flush()
        return stats

    def _team_by_vlr_id(self, vlr_team_id: int | None) -> Team | None:
        if vlr_team_id is None:
            return None
        return self._session.scalar(select(Team).where(Team.vlr_team_id == vlr_team_id))
