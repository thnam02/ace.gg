from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, Match, PlayerMapStats
from app.normalizers.vlr_api_event_normalizer import VlrApiEventNormalizer
from app.normalizers.vlr_api_match_normalizer import VlrApiMatchNormalizer
from app.providers.vlr_api_ingestion_provider import StaticVlrApiIngestionProvider
from app.providers.vlrggapi_client import VlrggApiClient
from app.providers.vlrggapi_errors import (
    VlrggApiHttpError,
    VlrggApiMalformedResponseError,
    VlrggApiStatusError,
)
from app.services.event_ingestion import EventIngestionService
from app.services.ingestion_sources import VlrApiEventIngestionSource
from app.services.match_ingestion import MatchIngestionService
from tests.vlrggapi_fixtures import (
    event_91000,
    event_91000_matches,
    match_900001_bo3,
    match_900002_bo1,
    match_900003_sparse,
    match_999998_malformed,
)


def _static_provider() -> StaticVlrApiIngestionProvider:
    return StaticVlrApiIngestionProvider(
        {
            900001: match_900001_bo3(),
            900002: match_900002_bo1(),
            900003: match_900003_sparse(),
            999998: match_999998_malformed(),
        },
        events={91000: event_91000()},
        event_matches={91000: event_91000_matches()},
    )


def test_match_normalizer_bo3_structure() -> None:
    normalizer = VlrApiMatchNormalizer()
    data = normalizer.normalize(
        match_900001_bo3(),
        event_id=91000,
        player_id_map={"tenz": 92001},
    )
    assert data.vlr_match_id == 900001
    assert data.team_a.name == "Sentinels"
    assert data.team_b.name == "LOUD"
    assert len(data.maps) == 2
    assert len(data.maps[0].player_stats) == 10
    assert data.maps[0].team_a_score == 13
    assert data.winner_vlr_team_id == 91001


def test_match_normalizer_bo1_structure() -> None:
    data = VlrApiMatchNormalizer().normalize(match_900002_bo1(), event_id=91000)
    assert len(data.maps) == 1
    assert data.best_of == 1


def test_match_normalizer_sparse_optional_stats() -> None:
    data = VlrApiMatchNormalizer().normalize(match_900003_sparse(), event_id=93000)
    ethan = next(
        stat
        for map_row in data.maps
        for stat in map_row.player_stats
        if stat.player.handle == "Ethan"
    )
    assert ethan.acs is None
    assert ethan.agent.name == "Unknown"


def test_event_normalizer_discovers_match_ids() -> None:
    page = VlrApiEventNormalizer().normalize_event_page(
        91000,
        event_91000(),
        event_91000_matches(),
    )
    assert page.event.name == "Champions 2024"
    assert page.event.start_date == date(2024, 8, 1)
    assert page.match_ids == [900001, 900002, 999999, 999998]
    assert len(page.participating_teams) == 2


def test_event_normalizer_player_id_map() -> None:
    player_map = VlrApiEventNormalizer().build_player_id_map(event_91000())
    assert player_map["tenz"] == 92001
    assert player_map["aspas"] == 92006


def test_vlrggapi_client_http_error() -> None:
    class BrokenClient(VlrggApiClient):
        def get_json(self, path: str, *, params: dict[str, str | int] | None = None):
            raise VlrggApiHttpError(500, path)

    client = BrokenClient("http://example.com")
    with pytest.raises(VlrggApiHttpError):
        client.get_data("/v2/match/details", params={"match_id": 1})


def test_vlrggapi_client_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> object:
            return ["not-a-dict"]

    class FakeHttpClient:
        def get(self, path: str, params: dict[str, str | int] | None = None) -> FakeResponse:
            return FakeResponse()

    client = VlrggApiClient("http://example.com", client=FakeHttpClient())
    with pytest.raises(VlrggApiMalformedResponseError):
        client.get_json("/v2/match/details")


def test_vlrggapi_client_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"status": "error"}

    class FakeHttpClient:
        def get(self, path: str, params: dict[str, str | int] | None = None) -> FakeResponse:
            return FakeResponse()

    client = VlrggApiClient("http://example.com", client=FakeHttpClient())
    with pytest.raises(VlrggApiStatusError):
        client.get_data("/v2/match/details")


def test_api_event_ingestion_summary(db_session: Session) -> None:
    source = VlrApiEventIngestionSource(_static_provider())
    summary = EventIngestionService(db_session, source).ingest_event(91000)

    assert summary.matches_discovered == 4
    assert summary.matches_ingested == 2
    assert summary.matches_skipped == 1
    assert summary.matches_failed == 1
    assert summary.player_map_stats_created == 30

    event = db_session.scalar(select(Event).where(Event.vlr_event_id == 91000))
    assert event is not None
    assert event.name == "Champions 2024"


def test_api_event_ingestion_is_idempotent(db_session: Session) -> None:
    source = VlrApiEventIngestionSource(_static_provider())
    service = EventIngestionService(db_session, source)
    first = service.ingest_event(91000)
    second = service.ingest_event(91000)
    assert first.player_map_stats_created == 30
    assert second.player_map_stats_created == 0
    assert db_session.scalar(select(func.count()).select_from(PlayerMapStats)) == 30


def test_one_failed_match_does_not_stop_api_event_ingestion(db_session: Session) -> None:
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(_static_provider()),
    ).ingest_event(91000)
    ingested_ids = {match.vlr_match_id for match in db_session.scalars(select(Match)).all()}
    assert 900001 in ingested_ids
    assert 900002 in ingested_ids
    assert summary.matches_failed == 1
    assert any("999998" in error for error in summary.errors)


def test_direct_match_ingestion_from_normalized_api_data(db_session: Session) -> None:
    provider = _static_provider()
    source = VlrApiEventIngestionSource(provider)
    source.load_event_page(91000)
    data = source.load_match(900003, 91000)
    MatchIngestionService(db_session).ingest(data)
    assert db_session.scalar(select(func.count()).select_from(PlayerMapStats)) == 2


def test_static_provider_team_and_player(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {},
        players={92001: {"info": {"name": "TenZ"}}},
        teams={91001: {"info": {"name": "Sentinels", "tag": "SEN"}}},
    )
    assert provider.get_player(92001)["info"]["name"] == "TenZ"
    assert provider.get_team(91001)["info"]["name"] == "Sentinels"
    with pytest.raises(VlrggApiHttpError):
        provider.get_match(1)
