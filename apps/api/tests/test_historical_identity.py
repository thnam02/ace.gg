from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, MatchMap, Player, PlayerMapStats, PlayerTeamHistory, Team
from app.normalizers.player_identity_resolver import PlayerIdentityResolver
from app.providers.vlr_api_ingestion_provider import (
    CachingVlrApiIngestionProvider,
    StaticVlrApiIngestionProvider,
)
from app.providers.vlrggapi_errors import VlrggApiHttpError
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.schemas.ingestion_diagnostics import IngestionDiagnostics
from app.services.dataset_audit_service import DatasetAuditReport, DatasetAuditService
from app.services.dataset_scale_readiness import (
    NOT_READY,
    READY_TO_SCALE,
    DatasetScaleReadinessService,
)
from app.services.event_ingestion import EventIngestionService, load_player_team_history_index
from app.services.historical_player_identity import (
    HistoricalPlayerIdentityResolver,
    IdentityLookupStatus,
)
from app.services.ingestion_sources import VlrApiEventIngestionSource
from app.services.map_completeness import summarize_map_completeness
from tests.factories import seed_match_graph
from tests.test_data_quality import (
    LOUD_ROSTER,
    SEN_ROSTER,
    _event_without_players,
    _nameless_match,
    _team_profile,
)


def _search_players(*players: tuple[int, str]) -> dict[str, Any]:
    return {
        "segments": {
            "query": players[0][1] if players else "",
            "results": {
                "players": [{"id": str(player_id), "name": name} for player_id, name in players]
            },
        }
    }


def _profile(
    handle: str,
    *,
    current: tuple[str, str] | None = None,
    past: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "segments": [
            {
                "name": handle,
                "current_team": (
                    {"name": current[0], "tag": current[1]} if current is not None else {}
                ),
                "past_teams": [{"name": name, "tag": tag} for name, tag in (past or [])],
            }
        ]
    }


def _lookup_provider(
    *,
    searches: dict[str, dict[str, Any]] | None = None,
    players: dict[int, dict[str, Any]] | None = None,
) -> StaticVlrApiIngestionProvider:
    return StaticVlrApiIngestionProvider({}, searches=searches, players=players)


def _all_search_payloads() -> dict[str, dict[str, Any]]:
    return {
        handle.lower(): _search_players((player_id, handle))
        for player_id, handle in SEN_ROSTER + LOUD_ROSTER
    }


def _all_profiles() -> dict[int, dict[str, Any]]:
    profiles: dict[int, dict[str, Any]] = {}
    for player_id, handle in SEN_ROSTER:
        profiles[player_id] = _profile(handle, current=("Sentinels", "SEN"))
    for player_id, handle in LOUD_ROSTER:
        profiles[player_id] = _profile(handle, current=("LOUD", "LOUD"))
    return profiles


def test_historical_identity_unique_search_with_team() -> None:
    provider = _lookup_provider(
        searches={"tenz": _search_players((9, "TenZ"))},
        players={9: _profile("TenZ", current=("Sentinels", "SEN"))},
    )
    result = HistoricalPlayerIdentityResolver(provider).lookup(
        "TenZ",
        match_team_id=2,
        team_name="Sentinels",
        team_tag="SEN",
    )
    assert result.status is IdentityLookupStatus.RESOLVED
    assert result.vlr_player_id == 9
    assert result.resolution_method == "search"
    assert result.candidate_count == 1
    assert "match team" in result.confidence_reason


def test_historical_identity_unique_search_without_conflict() -> None:
    provider = _lookup_provider(
        searches={"tenz": _search_players((9, "TenZ"))},
        players={9: _profile("TenZ")},
    )
    result = HistoricalPlayerIdentityResolver(provider).lookup(
        "TenZ",
        team_name="Sentinels",
        team_tag="SEN",
    )
    assert result.status is IdentityLookupStatus.RESOLVED
    assert result.vlr_player_id == 9
    assert "no conflicting" in result.confidence_reason


def test_historical_identity_does_not_pick_first_search_result() -> None:
    provider = _lookup_provider(
        searches={"ace": _search_players((100, "Ace"), (101, "Ace"))},
        players={
            100: _profile("Ace", current=("Team A", "A")),
            101: _profile("Ace", current=("Team B", "B")),
        },
    )
    result = HistoricalPlayerIdentityResolver(provider).lookup("Ace")
    assert result.status is IdentityLookupStatus.AMBIGUOUS
    assert result.vlr_player_id is None
    assert result.candidate_count == 2


def test_historical_identity_ambiguous_without_team_evidence() -> None:
    provider = _lookup_provider(
        searches={"ace": _search_players((100, "Ace"), (101, "Ace"))},
        players={
            100: _profile("Ace"),
            101: _profile("Ace"),
        },
    )
    result = HistoricalPlayerIdentityResolver(provider).lookup(
        "Ace",
        team_name="Sentinels",
        team_tag="SEN",
    )
    assert result.status is IdentityLookupStatus.AMBIGUOUS
    assert result.vlr_player_id is None


def test_profile_verification_rejects_conflicting_team() -> None:
    provider = _lookup_provider(
        searches={"tenz": _search_players((9, "TenZ"))},
        players={9: _profile("TenZ", current=("Cloud9", "C9"))},
    )
    result = HistoricalPlayerIdentityResolver(provider).lookup(
        "TenZ",
        team_name="Sentinels",
        team_tag="SEN",
    )
    assert result.status is IdentityLookupStatus.UNRESOLVED
    assert result.vlr_player_id is None
    assert "conflict" in result.confidence_reason


def test_profile_verification_selects_unique_team_among_duplicates() -> None:
    provider = _lookup_provider(
        searches={"ace": _search_players((100, "Ace"), (101, "Ace"))},
        players={
            100: _profile("Ace", current=("Team A", "A")),
            101: _profile("Ace", current=("Team B", "B"), past=[("Old Team", "OLD")]),
        },
    )
    result = HistoricalPlayerIdentityResolver(provider).lookup(
        "Ace",
        team_name="Team B",
        team_tag="B",
    )
    assert result.status is IdentityLookupStatus.RESOLVED
    assert result.vlr_player_id == 101


def test_team_history_resolution() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver(
        {},
        history_index={("legacy", 91001): {4242}},
        diagnostics=diagnostics,
    )
    assert resolver.resolve("Legacy", team_vlr_id=91001) == 4242
    assert diagnostics.player_identity.resolved_by_history == 1
    assert resolver.resolve("Legacy", team_vlr_id=99999) is None


def test_history_beats_search() -> None:
    provider = _lookup_provider(searches={"legacy": _search_players((999, "Legacy"))})
    lookup = HistoricalPlayerIdentityResolver(provider)
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver(
        {},
        history_index={("legacy", 91001): {4242}},
        identity_lookup=lookup,
        diagnostics=diagnostics,
    )
    assert resolver.resolve("Legacy", team_vlr_id=91001, team_name="Sentinels") == 4242
    assert diagnostics.player_identity.resolved_by_history == 1
    assert diagnostics.player_identity.resolved_by_search == 0
    assert lookup.searches_fetched == 0


class CountingLookupProvider(StaticVlrApiIngestionProvider):
    def __init__(self) -> None:
        super().__init__(
            {},
            searches={"tenz": _search_players((9, "TenZ"))},
            players={9: _profile("TenZ", current=("Sentinels", "SEN"))},
        )
        self.search_calls = 0
        self.profile_calls = 0

    def search(self, query: str) -> dict[str, Any]:
        self.search_calls += 1
        return super().search(query)

    def get_player(self, player_id: int) -> dict[str, Any]:
        self.profile_calls += 1
        return super().get_player(player_id)


def test_search_cache_reuse_within_run() -> None:
    provider = CountingLookupProvider()
    lookup = HistoricalPlayerIdentityResolver(provider)
    first = lookup.lookup("TenZ", team_name="Sentinels", team_tag="SEN")
    second = lookup.lookup("TenZ", team_name="Sentinels", team_tag="SEN")
    assert first.vlr_player_id == second.vlr_player_id == 9
    assert provider.search_calls == 1
    assert provider.profile_calls == 1
    assert lookup.searches_cached == 1
    assert lookup.profiles_cached == 1


def test_raw_cache_reuses_search_and_profile(tmp_path: Any) -> None:
    inner = CountingLookupProvider()
    cache = VlrggApiRawCache(tmp_path)
    provider = CachingVlrApiIngestionProvider(inner, cache)
    HistoricalPlayerIdentityResolver(provider).lookup(
        "TenZ",
        team_name="Sentinels",
        team_tag="SEN",
    )
    HistoricalPlayerIdentityResolver(provider).lookup(
        "TenZ",
        team_name="Sentinels",
        team_tag="SEN",
    )
    assert inner.search_calls == 1
    assert inner.profile_calls == 1
    assert cache.exists_key("player_search", "TenZ")
    assert cache.exists("players", 9)


def test_rate_limit_safe_search_does_not_crash_ingest(db_session: Session) -> None:
    class RateLimitedProvider(StaticVlrApiIngestionProvider):
        def search(self, query: str) -> dict[str, Any]:
            raise VlrggApiHttpError(429, f"/v2/search?q={query}")

    provider = RateLimitedProvider(
        {900001: _nameless_match()},
        events={91000: _event_without_players()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, []),
            91002: _team_profile(91002, []),
        },
    )
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(
            provider,
            identity_lookup=HistoricalPlayerIdentityResolver(provider),
        ),
    ).ingest_event(91000)
    assert summary.matches_failed == 0
    assert summary.unresolved_players == 10
    assert summary.player_map_stats_created == 0


def test_player_team_history_enrichment_and_idempotence(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: _nameless_match()},
        events={91000: _event_without_players()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, SEN_ROSTER),
            91002: _team_profile(91002, LOUD_ROSTER),
        },
    )
    EventIngestionService(db_session, VlrApiEventIngestionSource(provider)).ingest_event(91000)
    history_count = int(db_session.scalar(select(func.count()).select_from(PlayerTeamHistory)) or 0)
    assert history_count == 10

    tenz = db_session.scalar(select(Player).where(Player.vlr_player_id == 92001))
    sen = db_session.scalar(select(Team).where(Team.vlr_team_id == 91001))
    assert tenz is not None and sen is not None
    db_session.add(
        PlayerTeamHistory(
            player_id=tenz.id,
            team_id=sen.id,
            is_current=True,
            joined_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    db_session.flush()

    EventIngestionService(db_session, VlrApiEventIngestionSource(provider)).ingest_event(91000)
    rows = list(
        db_session.scalars(
            select(PlayerTeamHistory).where(
                PlayerTeamHistory.player_id == tenz.id,
                PlayerTeamHistory.team_id == sen.id,
            )
        ).all()
    )
    assert len(rows) == 2
    assert any(row.is_current for row in rows)


def test_idempotent_search_reingestion_does_not_duplicate(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: _nameless_match()},
        events={91000: _event_without_players()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, []),
            91002: _team_profile(91002, []),
        },
        searches=_all_search_payloads(),
        players=_all_profiles(),
    )
    lookup = HistoricalPlayerIdentityResolver(provider)
    first = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(provider, identity_lookup=lookup),
    ).ingest_event(91000)
    second = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(provider, identity_lookup=lookup),
    ).ingest_event(91000)
    assert first.player_map_stats_created == 10
    assert second.player_map_stats_created == 0
    assert int(db_session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0) == 10
    assert int(db_session.scalar(select(func.count()).select_from(MatchMap)) or 0) == 1


def test_t2_incomplete_map_recovery_via_search(db_session: Session) -> None:
    event = _event_without_players()
    event["segments"]["event"]["name"] = "Challengers NA ACE Stage 2"
    searches = {
        handle.lower(): _search_players((player_id, handle)) for player_id, handle in SEN_ROSTER
    }
    players = {
        player_id: _profile(handle, past=[("Sentinels", "SEN")]) for player_id, handle in SEN_ROSTER
    }
    provider = StaticVlrApiIngestionProvider(
        {900001: _nameless_match()},
        events={91000: event},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, []),
            91002: _team_profile(91002, LOUD_ROSTER),
        },
        searches=searches,
        players=players,
    )
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(
            provider,
            identity_lookup=HistoricalPlayerIdentityResolver(provider),
        ),
    ).ingest_event(91000)
    assert summary.maps_complete == 1
    assert summary.resolved_by_search == 5
    assert summary.resolved_by_team_roster == 5
    assert summary.unresolved_players == 0
    completeness = summarize_map_completeness(db_session)
    assert completeness.maps_complete == 1
    assert completeness.complete_map_pct == 100.0


def test_unresolved_identity_is_preserved(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: _nameless_match()},
        events={91000: _event_without_players()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, []),
            91002: _team_profile(91002, []),
        },
        searches={},
        players={},
    )
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(
            provider,
            identity_lookup=HistoricalPlayerIdentityResolver(provider),
        ),
    ).ingest_event(91000)
    assert summary.unresolved_players == 10
    assert summary.player_map_stats_created == 0
    assert int(db_session.scalar(select(func.count()).select_from(Player)) or 0) == 0
    assert db_session.scalar(select(Player).where(Player.handle == "TenZ")) is None


def test_history_index_feeds_later_event(db_session: Session) -> None:
    first_provider = StaticVlrApiIngestionProvider(
        {900001: _nameless_match()},
        events={91000: _event_without_players()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, SEN_ROSTER),
            91002: _team_profile(91002, LOUD_ROSTER),
        },
    )
    EventIngestionService(db_session, VlrApiEventIngestionSource(first_provider)).ingest_event(
        91000
    )
    history_index, player_teams = load_player_team_history_index(db_session)
    assert ("tenz", 91001) in history_index

    second_match = deepcopy(_nameless_match())
    second_match["match_id"] = "900012"
    second_provider = StaticVlrApiIngestionProvider(
        {900012: second_match},
        events={91001: _event_without_players()},
        event_matches={91001: {"matches": [{"match_id": "900012"}]}},
        teams={
            91001: _team_profile(91001, []),
            91002: _team_profile(91002, []),
        },
    )
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(
            second_provider,
            history_index=history_index,
            player_teams=player_teams,
        ),
    ).ingest_event(91001)
    assert summary.resolved_by_history == 10
    assert summary.maps_complete == 1
    assert int(db_session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0) == 20


def test_map_completeness_by_tier(db_session: Session) -> None:
    seed_match_graph(db_session)
    event = db_session.scalar(select(Event))
    assert event is not None
    event.tier = "T2"
    db_session.flush()
    summary = summarize_map_completeness(db_session)
    assert summary.by_tier["T2"].maps_incomplete == 1
    assert summary.by_tier["T2"].complete_map_pct == 0.0


def test_readiness_gate_requires_t2_completeness() -> None:
    report = DatasetAuditReport(
        player_map_stats=1000,
        maps=100,
        maps_complete=90,
        maps_incomplete=10,
        maps_empty=0,
        complete_map_pct=90.0,
        unresolved_identity_slots_pct=5.0,
        maps_eligible_for_cir=90,
        observations_by_role={
            "Duelist": 10,
            "Initiator": 10,
            "Controller": 10,
            "Sentinel": 10,
        },
        observations_by_tier={"T1": 500, "T2": 500},
        t1_maps_played=40,
        t1_maps_complete=38,
        t1_complete_map_pct=95.0,
        t2_maps_played=60,
        t2_maps_complete=27,
        t2_complete_map_pct=45.0,
        missing_clutch=1000,
    )
    scale = DatasetScaleReadinessService().assess(report)
    assert scale.status == NOT_READY
    assert scale.t2_status == NOT_READY
    assert any("T2 complete maps" in item for item in scale.blockers)


def test_readiness_gate_ready_when_t1_and_t2_pass() -> None:
    report = DatasetAuditReport(
        player_map_stats=1000,
        maps=100,
        maps_complete=90,
        maps_incomplete=10,
        maps_empty=0,
        complete_map_pct=90.0,
        unresolved_identity_slots_pct=5.0,
        maps_eligible_for_cir=90,
        observations_by_role={
            "Duelist": 10,
            "Initiator": 10,
            "Controller": 10,
            "Sentinel": 10,
        },
        observations_by_tier={"T1": 500, "T2": 500},
        t1_maps_played=40,
        t1_maps_complete=38,
        t1_complete_map_pct=95.0,
        t2_maps_played=60,
        t2_maps_complete=52,
        t2_complete_map_pct=86.7,
        missing_clutch=1000,
    )
    scale = DatasetScaleReadinessService().assess(report)
    assert scale.status == READY_TO_SCALE
    assert scale.t2_status == READY_TO_SCALE
    assert scale.recommended_events


def test_audit_report_includes_identity_and_tier_fields(db_session: Session) -> None:
    seed_match_graph(db_session)
    report = DatasetAuditService().audit(db_session)
    text = DatasetAuditService().format_report(report)
    assert "resolved_by_history:" in text
    assert "resolved_by_search:" in text
    assert "unresolved_identity_slots_pct:" in text
    assert "t1_complete_map_pct:" in text
    assert "t2_complete_map_pct:" in text
    assert report.unresolved_identity_slots_pct >= 0.0
