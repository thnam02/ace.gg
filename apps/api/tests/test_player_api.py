from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Match, MatchMap, Player, PlayerMapStats, PlayerTeamHistory
from tests.factories import seed_match_graph


def _seed_compare_graph(db_session: Session) -> dict[str, object]:
    graph = seed_match_graph(db_session)
    teammate = graph["teammate"]
    team_a = graph["team_a"]
    team_b = graph["team_b"]
    agent = graph["agent"]

    history = PlayerTeamHistory(
        player_id=teammate.id,
        team_id=team_a.id,
        joined_at=datetime(2023, 1, 1, tzinfo=UTC),
        is_current=True,
    )
    match = Match(
        vlr_match_id=50002,
        event_id=graph["event"].id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        winner_team_id=team_b.id,
        played_at=datetime(2024, 8, 11, 18, 0, tzinfo=UTC),
        status="completed",
    )
    db_session.add_all([history, match])
    db_session.flush()

    match_map = MatchMap(
        match_id=match.id,
        map_number=1,
        map_name="Haven",
        team_a_score=10,
        team_b_score=13,
        winner_team_id=team_b.id,
        rounds_played=23,
    )
    db_session.add(match_map)
    db_session.flush()

    stats = PlayerMapStats(
        match_map_id=match_map.id,
        player_id=teammate.id,
        team_id=team_a.id,
        agent_id=agent.id,
        rounds=23,
        kills=14,
        deaths=18,
        assists=3,
        first_kills=2,
        first_deaths=4,
        adr=140.0,
        kast_pct=68.0,
        clutch_wins=0,
        clutch_attempts=1,
        acs=210.0,
        headshot_pct=22.0,
    )
    db_session.add(stats)
    db_session.flush()
    graph["teammate_stats"] = stats
    return graph


def test_list_players_returns_dashboard_summaries(client: TestClient, db_session: Session) -> None:
    _seed_compare_graph(db_session)
    response = client.get("/players")
    assert response.status_code == 200
    players = response.json()
    assert len(players) == 2
    tenz = next(item for item in players if item["handle"] == "TenZ")
    assert tenz["stats"]["maps_played"] == 1
    assert tenz["stats"]["acs"] == pytest.approx(248.0)
    assert tenz["team"]["tag"] == "SEN"


def test_get_player_detail(client: TestClient, db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    player = graph["player"]
    response = client.get(f"/players/{player.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["handle"] == "TenZ"
    assert payload["stats"]["kd"] == pytest.approx(1.5)
    assert payload["aggregate"]["raw"]["maps_played"] == 1


def test_get_player_stats_with_filters(client: TestClient, db_session: Session) -> None:
    graph = _seed_compare_graph(db_session)
    player = graph["player"]
    response = client.get(
        f"/players/{player.id}/stats",
        params={"start_date": "2024-08-01", "end_date": "2024-08-31"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["aggregate"]["raw"]["kills"] == 18


def test_get_player_matches(client: TestClient, db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    player = graph["player"]
    response = client.get(f"/players/{player.id}/matches")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["performances"]) == 1
    assert payload["performances"][0]["map_name"] == "Bind"
    assert payload["performances"][0]["derived"]["kpr"] is not None


def test_get_player_maps(client: TestClient, db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    player = graph["player"]
    response = client.get(f"/players/{player.id}/maps")
    assert response.status_code == 200
    payload = response.json()
    assert payload["maps"][0]["map_name"] == "Bind"
    assert payload["maps"][0]["maps_played"] == 1


def test_compare_players(client: TestClient, db_session: Session) -> None:
    graph = _seed_compare_graph(db_session)
    player = graph["player"]
    teammate = graph["teammate"]
    response = client.get(
        "/players/compare",
        params={"player_ids": [str(player.id), str(teammate.id)]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["players"]) == 2
    handles = {entry["player"]["handle"] for entry in payload["players"]}
    assert handles == {"TenZ", "zekken"}


def test_empty_player_without_stats(client: TestClient, db_session: Session) -> None:
    seed_match_graph(db_session)
    empty_player = Player(vlr_player_id=999, handle="EmptyPlayer")
    db_session.add(empty_player)
    db_session.flush()

    response = client.get(f"/players/{empty_player.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["maps_played"] == 0
    assert payload["stats"]["acs"] is None


def test_invalid_player_id_returns_404(client: TestClient) -> None:
    response = client.get("/players/not-a-real-player")
    assert response.status_code == 404


def test_compare_skips_unknown_player_ids(client: TestClient, db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    response = client.get(
        "/players/compare",
        params={"player_ids": [str(graph["player"].id), "not-valid"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["players"]) == 1
    assert payload["players"][0]["player"]["handle"] == "TenZ"
    assert "Unknown player IDs: not-valid" in payload["notes"]


def test_compare_accepts_comma_separated_player_ids(
    client: TestClient, db_session: Session
) -> None:
    graph = _seed_compare_graph(db_session)
    response = client.get(
        "/players/compare",
        params={
            "player_ids": f"{graph['player'].id},{graph['teammate'].id}",
        },
    )
    assert response.status_code == 200
    handles = {entry["player"]["handle"] for entry in response.json()["players"]}
    assert handles == {"TenZ", "zekken"}
