from __future__ import annotations

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import MatchMap, Player, PlayerMapStats, PlayerTeamHistory, Team
from tests.factories import seed_match_graph


def test_seeded_graph_relationships(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    player = data["player"]
    team_a = data["team_a"]
    match = data["match"]
    match_map = data["match_map"]
    stats = data["stats"]

    db_session.refresh(player)
    db_session.refresh(team_a)
    db_session.refresh(match)
    db_session.refresh(match_map)

    assert player.handle == "TenZ"
    assert player.team_history[0].team.tag == "SEN"
    assert player.team_history[0].is_current is True
    assert match.team_a.name == "Sentinels"
    assert match.winner_team is team_a
    assert match.maps[0].map_name == "Bind"
    assert match_map.player_stats[0].kills == 18
    assert stats.player.handle == "TenZ"
    assert stats.agent.name == "Jett"
    assert stats.adr == pytest.approx(162.4)


def test_player_vlr_id_is_unique(db_session: Session) -> None:
    db_session.add(Player(vlr_player_id=10, handle="first"))
    db_session.flush()
    db_session.add(Player(vlr_player_id=10, handle="second"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_map_unique_constraint(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    match = data["match"]
    db_session.add(
        MatchMap(match_id=match.id, map_number=1, map_name="Haven"),
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_player_map_stats_unique_constraint(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    db_session.add(
        PlayerMapStats(
            match_map_id=data["match_map"].id,
            player_id=data["player"].id,
            team_id=data["team_a"].id,
            agent_id=data["agent"].id,
            rounds=10,
            kills=1,
            deaths=1,
            assists=0,
            first_kills=0,
            first_deaths=0,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_player_is_restricted_when_stats_exist(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    db_session.delete(data["player"])
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_team_is_restricted_when_stats_exist(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    db_session.delete(data["team_a"])
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_match_cascades_maps_and_stats(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    stats_id = data["stats"].id
    map_id = data["match_map"].id
    player_id = data["player"].id

    db_session.delete(data["match"])
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(MatchMap, map_id) is None
    assert db_session.get(PlayerMapStats, stats_id) is None
    assert db_session.get(Player, player_id) is not None


def test_deleting_player_is_restricted_when_team_history_exists(db_session: Session) -> None:
    player = Player(vlr_player_id=99, handle="leaf")
    team = Team(vlr_team_id=99, name="NRG", tag="NRG")
    db_session.add_all([player, team])
    db_session.flush()
    db_session.add(PlayerTeamHistory(player_id=player.id, team_id=team.id, is_current=True))
    db_session.flush()

    db_session.delete(player)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_expected_indexes_exist(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())
    player_indexes = {index["name"] for index in inspector.get_indexes("players")}
    match_indexes = {index["name"] for index in inspector.get_indexes("matches")}
    stats_indexes = {index["name"] for index in inspector.get_indexes("player_map_stats")}

    assert "ix_players_vlr_player_id" in player_indexes
    assert "ix_matches_played_at" in match_indexes
    assert "ix_player_map_stats_player_id" in stats_indexes


def test_derived_metric_columns_are_not_stored(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())
    stats_columns = {column["name"] for column in inspector.get_columns("player_map_stats")}
    forbidden = {"kpr", "dpr", "apr", "fkpr", "fdpr", "kd", "opening_efficiency", "cir"}
    assert stats_columns.isdisjoint(forbidden)


def test_query_player_stats_by_player_id(db_session: Session) -> None:
    data = seed_match_graph(db_session)
    rows = db_session.scalars(
        select(PlayerMapStats).where(PlayerMapStats.player_id == data["player"].id)
    ).all()
    assert len(rows) == 1
    assert rows[0].acs == pytest.approx(248.0)
