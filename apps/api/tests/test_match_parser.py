from __future__ import annotations

import pytest

from app.parsers.match_parser import MatchParser
from tests.vlr_fixtures import load_match_html, match_fixture_names


@pytest.mark.parametrize("fixture_name", match_fixture_names())
def test_parser_handles_all_saved_fixtures(fixture_name: str) -> None:
    html = load_match_html(fixture_name)
    data = MatchParser().parse(html)

    assert data.vlr_match_id > 0
    assert data.team_a.vlr_team_id != data.team_b.vlr_team_id
    assert data.event.vlr_event_id > 0
    assert data.maps
    for match_map in data.maps:
        assert match_map.map_name
        assert 8 <= len(match_map.player_stats) <= 12


def test_bo3_extracts_teams_maps_and_player_stats() -> None:
    data = MatchParser().parse(load_match_html("900001_bo3_completed.html"))

    assert data.vlr_match_id == 900001
    assert data.event.name == "Champions 2024"
    assert data.event.season_year == 2024
    assert data.team_a.name == "Sentinels"
    assert data.team_b.name == "LOUD"
    assert data.best_of == 3
    assert data.status == "completed"
    assert data.winner_vlr_team_id == data.team_a.vlr_team_id
    assert [item.map_name for item in data.maps] == ["Bind", "Haven"]
    assert data.maps[0].team_a_score == 13
    assert data.maps[0].team_b_score == 8
    assert data.maps[0].rounds_played == 21

    bind_stats = data.maps[0].player_stats
    assert len(bind_stats) == 10
    tenz = next(row for row in bind_stats if row.player.handle == "TenZ")
    assert tenz.player.vlr_player_id == 92001
    assert tenz.agent.name == "Jett"
    assert tenz.kills == 18
    assert tenz.deaths == 12
    assert tenz.assists == 4
    assert tenz.acs == pytest.approx(248)
    assert tenz.adr == pytest.approx(162)
    assert tenz.kast_pct == pytest.approx(76)
    assert tenz.first_kills == 5
    assert tenz.first_deaths == 2
    assert tenz.headshot_pct == pytest.approx(27)
    assert tenz.vlr_rating == pytest.approx(1.31)
    assert tenz.team_vlr_id == data.team_a.vlr_team_id


def test_bo1_uses_a_different_match_structure() -> None:
    data = MatchParser().parse(load_match_html("900002_bo1_completed.html"))

    assert data.vlr_match_id == 900002
    assert data.best_of == 1
    assert data.team_a.name == "Gen.G"
    assert data.team_b.name == "Paper Rex"
    assert len(data.maps) == 1
    assert data.maps[0].map_name == "Sunset"
    assert len(data.maps[0].player_stats) == 10
    handles = {row.player.handle for row in data.maps[0].player_stats}
    assert "t3xture" in handles
    assert "Jinggg" in handles


def test_sparse_optional_fields_do_not_crash_parsing() -> None:
    data = MatchParser().parse(load_match_html("900003_sparse_optional.html"))

    assert data.vlr_match_id == 900003
    assert data.played_at is None
    assert data.winner_vlr_team_id == data.team_b.vlr_team_id
    assert len(data.maps) == 1
    assert len(data.maps[0].player_stats) == 10

    ethan = next(row for row in data.maps[0].player_stats if row.player.handle == "Ethan")
    assert ethan.acs is None
    assert ethan.first_kills == 0
    assert ethan.first_deaths == 0
    assert ethan.kast_pct is None
    assert ethan.agent.name == "Unknown"

    victor = next(row for row in data.maps[0].player_stats if row.player.handle == "Victor")
    assert victor.headshot_pct is None


def test_malformed_html_raises_for_required_fields() -> None:
    parser = MatchParser()
    with pytest.raises(ValueError):
        parser.parse(" ")
    with pytest.raises(ValueError):
        parser.parse("<html><body>no match data</body></html>")


def test_disabled_and_all_maps_tabs_are_ignored() -> None:
    data = MatchParser().parse(load_match_html("900001_bo3_completed.html"))
    assert len(data.maps) == 2
