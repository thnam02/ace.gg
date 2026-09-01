from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models import (
    Agent,
    Event,
    Match,
    MatchMap,
    Player,
    PlayerMapStats,
    PlayerTeamHistory,
    Team,
)


def seed_match_graph(session: Session) -> dict[str, object]:
    player = Player(vlr_player_id=2615, handle="TenZ", real_name="Tyson Ngo", country="CA")
    teammate = Player(vlr_player_id=2, handle="zekken", country="US")
    team_a = Team(vlr_team_id=2, name="Sentinels", tag="SEN", country="US", region="NA")
    team_b = Team(vlr_team_id=2406, name="Paper Rex", tag="PRX", region="AP")
    agent = Agent(name="Jett", role="Duelist")
    event = Event(
        vlr_event_id=1188,
        name="Champions 2024",
        region="INTL",
        tier="S",
        start_date=date(2024, 8, 1),
        end_date=date(2024, 8, 25),
        season_year=2024,
    )
    session.add_all([player, teammate, team_a, team_b, agent, event])
    session.flush()

    history = PlayerTeamHistory(
        player_id=player.id,
        team_id=team_a.id,
        joined_at=datetime(2023, 1, 1, tzinfo=UTC),
        is_current=True,
    )
    match = Match(
        vlr_match_id=50001,
        event_id=event.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        winner_team_id=team_a.id,
        played_at=datetime(2024, 8, 10, 18, 0, tzinfo=UTC),
        best_of=3,
        status="completed",
    )
    session.add_all([history, match])
    session.flush()

    match_map = MatchMap(
        match_id=match.id,
        map_number=1,
        map_name="Bind",
        team_a_score=13,
        team_b_score=8,
        winner_team_id=team_a.id,
        rounds_played=21,
    )
    session.add(match_map)
    session.flush()

    stats = PlayerMapStats(
        match_map_id=match_map.id,
        player_id=player.id,
        team_id=team_a.id,
        agent_id=agent.id,
        rounds=21,
        kills=18,
        deaths=12,
        assists=4,
        first_kills=5,
        first_deaths=2,
        adr=162.4,
        kast_pct=76.2,
        clutch_wins=1,
        clutch_attempts=2,
        acs=248.0,
        vlr_rating=1.21,
        headshot_pct=27.5,
        max_kills=4,
    )
    session.add(stats)
    session.flush()

    return {
        "player": player,
        "teammate": teammate,
        "team_a": team_a,
        "team_b": team_b,
        "agent": agent,
        "event": event,
        "history": history,
        "match": match,
        "match_map": match_map,
        "stats": stats,
    }
