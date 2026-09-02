from __future__ import annotations

import pytest

from app.parsers.event_parser import EventParser
from tests.vlr_fixtures import load_event_html


def test_event_metadata_parsing() -> None:
    data = EventParser().parse(load_event_html("91000_champions_2024.html"), event_id=91000)

    assert data.event.vlr_event_id == 91000
    assert data.event.name == "Champions 2024"
    assert data.event.region == "NA"
    assert data.event.tier == "S-Tier"
    assert data.event.status == "completed"
    assert data.event.season_year == 2024
    assert data.event.start_date is not None
    assert data.event.end_date is not None
    assert data.event.start_date.month == 8
    assert data.event.end_date.day == 25

    teams = {team.vlr_team_id: team.name for team in data.participating_teams}
    assert teams[91001] == "Sentinels"
    assert teams[91002] == "LOUD"


def test_discover_match_ids_from_event_matches_fixture() -> None:
    parser = EventParser()
    ids = parser.discover_match_ids(load_event_html("91000_matches.html"), event_id=91000)

    assert ids == [900001, 900002, 999999, 999998]


def test_duplicate_match_ids_are_removed() -> None:
    ids = EventParser().discover_match_ids(load_event_html("91000_matches.html"), event_id=91000)
    assert ids.count(900001) == 1


def test_malformed_event_html_raises() -> None:
    with pytest.raises(ValueError):
        EventParser().parse(" ")
    with pytest.raises(ValueError):
        EventParser().parse("<html><body>no event</body></html>")
