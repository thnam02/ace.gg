from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Event, Match, MatchMap, PlayerMapStats
from app.services.stats_engine_service import StatsEngineService
from tests.factories import seed_match_graph


def _add_second_map(session: Session, graph: dict[str, object]) -> PlayerMapStats:
    match = graph["match"]
    player = graph["player"]
    team_a = graph["team_a"]
    agent = graph["agent"]

    second_map = MatchMap(
        match_id=match.id,
        map_number=2,
        map_name="Haven",
        team_a_score=13,
        team_b_score=11,
        winner_team_id=team_a.id,
        rounds_played=24,
    )
    session.add(second_map)
    session.flush()

    stats = PlayerMapStats(
        match_map_id=second_map.id,
        player_id=player.id,
        team_id=team_a.id,
        agent_id=agent.id,
        rounds=24,
        kills=20,
        deaths=16,
        assists=6,
        first_kills=4,
        first_deaths=4,
        adr=180.0,
        kast_pct=80.0,
        clutch_wins=2,
        clutch_attempts=3,
        acs=260.0,
    )
    session.add(stats)
    session.flush()
    return stats


def test_service_for_single_player_map_stats_row(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    features = StatsEngineService(db_session).for_player_map_stats(graph["stats"])

    assert features.raw.rounds == 21
    assert features.raw.kills == 18
    assert features.derived.kpr == pytest.approx(18 / 21)
    assert features.match_map_id == graph["match_map"].id


def test_service_aggregates_multiple_maps_for_player(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    _add_second_map(db_session, graph)

    aggregate = StatsEngineService(db_session).for_player(graph["player"].id)

    assert aggregate.raw.maps_played == 2
    assert aggregate.raw.rounds == 45
    assert aggregate.raw.kills == 38
    assert aggregate.raw.weighted_adr == pytest.approx((162.4 * 21 + 180.0 * 24) / 45)
    assert aggregate.derived.kpr == pytest.approx(38 / 45)
    assert len(aggregate.maps) == 2


def test_service_filters_by_event_and_date_range(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    player = graph["player"]
    event = graph["event"]

    other_event = Event(
        vlr_event_id=9999,
        name="Other Event",
        start_date=date(2024, 9, 1),
        end_date=date(2024, 9, 30),
    )
    db_session.add(other_event)
    db_session.flush()

    other_match = Match(
        vlr_match_id=50002,
        event_id=other_event.id,
        team_a_id=graph["team_a"].id,
        team_b_id=graph["team_b"].id,
        played_at=datetime(2024, 9, 5, 12, 0, tzinfo=UTC),
        status="completed",
    )
    db_session.add(other_match)
    db_session.flush()

    other_map = MatchMap(
        match_id=other_match.id,
        map_number=1,
        map_name="Split",
        rounds_played=20,
    )
    db_session.add(other_map)
    db_session.flush()

    db_session.add(
        PlayerMapStats(
            match_map_id=other_map.id,
            player_id=player.id,
            team_id=graph["team_a"].id,
            agent_id=graph["agent"].id,
            rounds=20,
            kills=12,
            deaths=10,
            assists=2,
            first_kills=1,
            first_deaths=1,
            adr=140.0,
            kast_pct=65.0,
            acs=210.0,
        )
    )
    db_session.flush()

    service = StatsEngineService(db_session)
    by_event = service.for_player(player.id, event_id=event.id)
    assert by_event.raw.maps_played == 1
    assert by_event.raw.kills == 18

    by_vlr_event = service.for_player(player.id, vlr_event_id=event.vlr_event_id)
    assert by_vlr_event.raw.maps_played == 1

    by_date = service.for_player(
        player.id,
        start_date=date(2024, 8, 1),
        end_date=date(2024, 8, 31),
    )
    assert by_date.raw.maps_played == 1

    all_maps = service.for_player(player.id)
    assert all_maps.raw.maps_played == 2
    assert all_maps.raw.kills == 30
