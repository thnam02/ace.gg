from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.normalizers.event_tier_resolver import EventTier, EventTierResolver
from app.normalizers.player_identity_resolver import PlayerIdentityResolver
from app.normalizers.rounds_resolver import resolve_map_rounds, resolve_player_rounds
from app.normalizers.vlr_api_match_normalizer import VlrApiMatchNormalizer
from app.normalizers.vlr_api_parsing import clutch_stats_from_advanced
from app.providers.vlr_api_ingestion_provider import (
    CachingVlrApiIngestionProvider,
    StaticVlrApiIngestionProvider,
)
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.schemas.ingestion_diagnostics import IngestionDiagnostics
from app.services.dataset_audit_service import DatasetAuditService
from app.services.event_ingestion import EventIngestionService
from app.services.ingestion_sources import VlrApiEventIngestionSource
from tests.vlrggapi_fixtures import (
    event_91000,
    event_91000_matches,
    match_900001_bo3,
)


def test_rounds_from_player_row() -> None:
    rounds, source = resolve_player_rounds({"rounds": "24"}, map_rounds=22)
    assert rounds == 24
    assert source == "player_row"


def test_rounds_derived_from_map_score() -> None:
    map_rounds = resolve_map_rounds(13, 11)
    assert map_rounds == 24
    rounds, source = resolve_player_rounds({}, map_rounds=map_rounds)
    assert rounds == 24
    assert source == "map_score"


def test_rounds_overtime_from_map_score() -> None:
    rounds, source = resolve_player_rounds({}, map_rounds=resolve_map_rounds(16, 14))
    assert rounds == 30
    assert source == "map_score"


def test_rounds_unresolved() -> None:
    rounds, source = resolve_player_rounds({}, map_rounds=None)
    assert rounds is None
    assert source == "unresolved"


def test_match_normalizer_rejects_unresolved_rounds() -> None:
    match_data = match_900001_bo3()
    match_data["maps"][0]["score"] = {}
    match_data["maps"][0]["players"]["team1"][0].pop("rounds", None)
    diagnostics = IngestionDiagnostics()
    normalizer = VlrApiMatchNormalizer(diagnostics)
    resolver = PlayerIdentityResolver.from_event_teams(event_91000(), diagnostics=diagnostics)
    data = normalizer.normalize(
        match_data,
        event_id=91000,
        identity_resolver=resolver,
    )
    assert diagnostics.missing_rounds > 0
    assert all(stat.rounds is not None for stat in data.maps[0].player_stats)


def test_player_identity_priority() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(event_91000(), diagnostics=diagnostics)
    assert resolver.resolve("TenZ", 99999) == 99999
    assert diagnostics.player_identity.resolved_by_id == 1
    assert resolver.resolve("TenZ", None) == 92001
    assert diagnostics.player_identity.resolved_by_event_roster == 1


def test_ambiguous_player_identity() -> None:
    event_data = {
        "segments": {
            "teams": [
                {
                    "id": "1",
                    "name": "Team A",
                    "players": [
                        {"id": "100", "name": "Ace"},
                        {"id": "101", "name": "ace"},
                    ],
                }
            ]
        }
    }
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(event_data, diagnostics=diagnostics)
    assert resolver.resolve("Ace", None) is None
    assert diagnostics.ambiguous_player_count() == 1


def test_known_handle_name_resolution() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver(
        {},
        known_handles={"legacy": 4242},
        player_teams={4242: {91001}},
        diagnostics=diagnostics,
    )
    assert resolver.resolve("Legacy", None, team_vlr_id=91001) == 4242
    assert diagnostics.player_identity.resolved_by_db_identity == 1


def test_event_tier_resolver() -> None:
    resolver = EventTierResolver()
    assert resolver.resolve(name="Valorant Champions 2024") == EventTier.T1
    assert resolver.resolve(name="VCT Challengers League") == EventTier.T2
    assert resolver.resolve(name="Game Changers Series") == EventTier.OTHER
    assert resolver.resolve(name="Community Cup") == EventTier.UNKNOWN


def test_missing_clutch_stays_none() -> None:
    wins, attempts = clutch_stats_from_advanced({}, "TenZ")
    assert wins is None and attempts is None


def test_clutch_with_explicit_fields() -> None:
    performance = {
        "advanced_stats": [
            {"player": "TenZ", "clutch_1v1": "2", "clutch_1v2": "1"},
        ]
    }
    wins, attempts = clutch_stats_from_advanced(performance, "TenZ")
    assert wins == 2
    assert attempts == 3


def test_raw_json_cache_roundtrip(tmp_path: object) -> None:
    from pathlib import Path

    cache = VlrggApiRawCache(Path(str(tmp_path)))
    payload = {"match_id": "1"}
    cache.save("matches", 1, payload)
    assert cache.load("matches", 1) == payload


def test_caching_provider_reads_existing_cache(tmp_path: object) -> None:
    from pathlib import Path

    cache = VlrggApiRawCache(Path(str(tmp_path)))
    cache.save("matches", 900001, {"from": "cache"})

    class ExplodingProvider(StaticVlrApiIngestionProvider):
        def get_match(self, match_id: int):  # type: ignore[no-untyped-def]
            raise AssertionError("cache should prevent a network fetch")

    provider = CachingVlrApiIngestionProvider(ExplodingProvider({}), cache)
    assert provider.get_match(900001) == {"from": "cache"}
    from pathlib import Path

    static = StaticVlrApiIngestionProvider({900001: match_900001_bo3()})
    cache = VlrggApiRawCache(Path(str(tmp_path)))
    provider = CachingVlrApiIngestionProvider(static, cache)
    provider.get_match(900001)
    assert cache.exists("matches", 900001)


def test_dry_run_ingestion(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: match_900001_bo3()},
        events={91000: event_91000()},
        event_matches={91000: event_91000_matches()},
    )
    source = VlrApiEventIngestionSource(provider)
    summary = EventIngestionService(db_session, source, dry_run=True).ingest_event(91000)
    assert summary.dry_run
    assert summary.matches_ingested == 1
    assert summary.player_map_stats_created == 0


def test_cli_single_event_ingestion(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: match_900001_bo3()},
        events={91000: event_91000()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    source = VlrApiEventIngestionSource(provider)
    service = EventIngestionService(db_session, source)
    summary = service.ingest_event(91000)
    assert summary.matches_ingested == 1
    assert summary.player_map_stats_created == 20


def test_idempotent_rerun(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: match_900001_bo3()},
        events={91000: event_91000()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    source = VlrApiEventIngestionSource(provider)
    service = EventIngestionService(db_session, source)
    first = service.ingest_event(91000)
    second = service.ingest_event(91000)
    assert first.player_map_stats_created == 20
    assert second.player_map_stats_created == 0


def test_dataset_audit_empty(db_session: Session) -> None:
    report = DatasetAuditService().audit(db_session)
    assert report.players == 0
    text = DatasetAuditService().format_report(report)
    assert "player_map_stats: 0" in text


def test_continue_on_error_multi_event(db_session: Session) -> None:
    from app.schemas.ingestion import EventIngestionSummary

    ok_provider = StaticVlrApiIngestionProvider(
        {900001: match_900001_bo3()},
        events={91000: event_91000()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    bad_provider = StaticVlrApiIngestionProvider({}, events={}, event_matches={})
    summaries: list[EventIngestionSummary] = []
    for event_id, provider in [(91000, ok_provider), (99999, bad_provider)]:
        try:
            source = VlrApiEventIngestionSource(provider)
            summaries.append(EventIngestionService(db_session, source).ingest_event(event_id))
        except Exception:
            summaries.append(
                EventIngestionSummary(
                    event_id=event_id,
                    matches_failed=1,
                    errors=[f"event_id={event_id}: ingestion failed"],
                )
            )
    assert len(summaries) == 2
    assert summaries[0].event_id == 91000
    assert summaries[1].event_id == 99999
    assert summaries[1].matches_failed == 1


def test_event_page_tier_stored(db_session: Session) -> None:
    from app.models import Event

    provider = StaticVlrApiIngestionProvider(
        {},
        events={91000: event_91000()},
        event_matches={91000: {"matches": []}},
    )
    EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(provider),
    ).ingest_event(91000)
    event = db_session.scalar(select(Event).where(Event.vlr_event_id == 91000))
    assert event is not None
    assert event.tier == "T1"


def test_live_event_matches_use_segments() -> None:
    from app.normalizers.vlr_api_event_normalizer import VlrApiEventNormalizer

    page = VlrApiEventNormalizer().normalize_event_page(
        2765,
        {
            "segments": {
                "event": {"name": "Valorant Masters London 2026", "dates": "Jun 6–21, 2026"},
                "teams": [],
            }
        },
        {"status": 200, "segments": [{"match_id": "684613"}, {"match_id": "684610"}]},
    )
    assert page.match_ids == [684613, 684610]
    assert page.event.start_date is not None
    assert page.event.end_date is not None


def test_live_match_envelope_and_flat_scores() -> None:
    from app.normalizers.player_identity_resolver import PlayerIdentityResolver
    from app.normalizers.vlr_api_match_normalizer import VlrApiMatchNormalizer
    from app.schemas.ingestion_diagnostics import IngestionDiagnostics

    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(
        {
            "segments": {
                "teams": [
                    {"id": "1", "name": "A", "players": [{"id": "10", "name": "Alpha"}]},
                    {"id": "2", "name": "B", "players": [{"id": "20", "name": "Bravo"}]},
                ]
            }
        },
        diagnostics=diagnostics,
    )
    payload = {
        "status": 200,
        "segments": [
            {
                "match_id": "111",
                "status": "final",
                "teams": [
                    {"id": "1", "name": "Team A", "score": "0"},
                    {"id": "2", "name": "Team B", "score": "1"},
                ],
                "maps": [
                    {
                        "map_name": "Pearl",
                        "score": {"team1": 6, "team2": 13},
                        "players": {
                            "team1": [{"name": "Alpha", "agent": "Jett", "kills": "8"}],
                            "team2": [{"name": "Bravo", "agent": "Omen", "kills": "12"}],
                        },
                    }
                ],
            }
        ],
    }
    data = VlrApiMatchNormalizer(diagnostics).normalize(
        payload,
        event_id=2765,
        identity_resolver=resolver,
    )
    assert data.vlr_match_id == 111
    assert data.maps[0].team_a_score == 6
    assert data.maps[0].team_b_score == 13
    assert data.maps[0].rounds_played == 19
    assert data.maps[0].player_stats[0].rounds == 19
    assert data.maps[0].player_stats[0].player.vlr_player_id == 10
