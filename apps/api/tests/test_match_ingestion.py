from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Agent, Event, Match, MatchMap, Player, PlayerMapStats, Team
from app.parsers.match_parser import MatchParser
from app.providers.vlr_provider import FileVLRProvider
from app.services.match_ingestion import MatchIngestionService
from tests.vlr_fixtures import FIXTURES_DIR


def _ingest_fixture(db_session: Session, match_id: int) -> Match:
    html = FileVLRProvider(FIXTURES_DIR).get_match(match_id)
    data = MatchParser().parse(html)
    return MatchIngestionService(db_session).ingest(data)


def test_ingestion_is_idempotent(db_session: Session) -> None:
    service_match = _ingest_fixture(db_session, 900001)
    first_id = service_match.id
    _ingest_fixture(db_session, 900001)

    assert db_session.scalar(select(func.count()).select_from(Match)) == 1
    assert db_session.scalar(select(func.count()).select_from(Event)) == 1
    assert db_session.scalar(select(func.count()).select_from(Team)) == 2
    assert db_session.scalar(select(func.count()).select_from(Player)) == 10
    assert db_session.scalar(select(func.count()).select_from(MatchMap)) == 2
    assert db_session.scalar(select(func.count()).select_from(PlayerMapStats)) == 20
    assert db_session.scalar(select(func.count()).select_from(Agent)) >= 1

    match = db_session.scalar(select(Match).where(Match.vlr_match_id == 900001))
    assert match is not None
    assert match.id == first_id


def test_reingest_updates_existing_stats(db_session: Session) -> None:
    html = FileVLRProvider(FIXTURES_DIR).get_match(900001)
    parser = MatchParser()
    data = parser.parse(html)
    service = MatchIngestionService(db_session)
    service.ingest(data)

    tenz_stats = next(
        row
        for match_map in data.maps
        for row in match_map.player_stats
        if row.player.handle == "TenZ" and match_map.map_number == 1
    )
    tenz_stats.kills = 99
    service.ingest(data)

    stored = db_session.scalar(
        select(PlayerMapStats)
        .join(Player)
        .join(MatchMap)
        .where(Player.handle == "TenZ", MatchMap.map_number == 1)
    )
    assert stored is not None
    assert stored.kills == 99
    assert db_session.scalar(select(func.count()).select_from(PlayerMapStats)) == 20


def test_ingested_relationships_are_valid(db_session: Session) -> None:
    _ingest_fixture(db_session, 900002)

    match = db_session.scalar(
        select(Match)
        .options(
            selectinload(Match.maps).selectinload(MatchMap.player_stats),
            selectinload(Match.team_a),
            selectinload(Match.team_b),
            selectinload(Match.event),
        )
        .where(Match.vlr_match_id == 900002)
    )
    assert match is not None
    assert match.event.name == "Masters Madrid 2024"
    assert match.team_a.name == "Gen.G"
    assert match.team_b.name == "Paper Rex"
    assert len(match.maps) == 1
    stats = match.maps[0].player_stats
    assert len(stats) == 10
    assert len({row.player_id for row in stats}) == 10
    assert all(row.team_id in {match.team_a_id, match.team_b_id} for row in stats)
    assert all(row.agent_id is not None for row in stats)
    assert all(row.match_map_id == match.maps[0].id for row in stats)


def test_sparse_match_ingests_without_optional_stats(db_session: Session) -> None:
    _ingest_fixture(db_session, 900003)
    ethan = db_session.scalar(select(Player).where(Player.handle == "Ethan"))
    assert ethan is not None
    stats = db_session.scalar(
        select(PlayerMapStats)
        .options(selectinload(PlayerMapStats.agent))
        .where(PlayerMapStats.player_id == ethan.id)
    )
    assert stats is not None
    assert stats.acs is None
    assert stats.first_kills == 0
    assert stats.agent.name == "Unknown"
