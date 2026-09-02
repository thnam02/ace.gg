from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, MatchMap, Player, PlayerMapStats
from app.normalizers.player_identity_resolver import PlayerIdentityResolver
from app.normalizers.vlr_api_match_normalizer import VlrApiMatchNormalizer
from app.parsers.agents import canonical_agent_name, is_known_agent, normalize_agent_name
from app.providers.vlr_api_ingestion_provider import StaticVlrApiIngestionProvider
from app.schemas.ingestion_diagnostics import IngestionDiagnostics
from app.services.cir_training_service import CIRTrainingService
from app.services.clutch_coverage import measure_clutch_coverage
from app.services.dataset_audit_service import DatasetAuditService
from app.services.dataset_scale_readiness import DatasetScaleReadinessService
from app.services.event_ingestion import EventIngestionService
from app.services.ingestion_sources import VlrApiEventIngestionSource
from app.services.map_completeness import (
    MapCompleteness,
    classify_player_stat_count,
    summarize_map_completeness,
)
from tests.factories import seed_match_graph
from tests.vlrggapi_fixtures import event_91000, match_900001_bo3, match_900003_sparse

SEN_ROSTER = [
    (92001, "TenZ"),
    (92002, "zekken"),
    (92003, "sacy"),
    (92004, "pancada"),
    (92005, "johnqt"),
]
LOUD_ROSTER = [
    (92006, "aspas"),
    (92007, "cauanzin"),
    (92008, "tuyz"),
    (92009, "saadhak"),
    (92010, "less"),
]


def _event_without_players() -> dict[str, Any]:
    event = copy.deepcopy(event_91000())
    for team in event["segments"]["teams"]:
        team["players"] = []
    return event


def _event_with_tenz_only() -> dict[str, Any]:
    event = copy.deepcopy(event_91000())
    event["segments"]["teams"][0]["players"] = [{"id": "92001", "name": "TenZ"}]
    event["segments"]["teams"][1]["players"] = []
    return event


def _strip_player_ids(match: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(match)
    for map_row in data["maps"]:
        for side in ("team1", "team2"):
            for player in map_row["players"][side]:
                player.pop("id", None)
    return data


def _team_profile(team_id: int, players: list[tuple[int, str]]) -> dict[str, Any]:
    return {
        "status": 200,
        "segments": [
            {
                "id": str(team_id),
                "roster": [
                    {"id": str(player_id), "alias": handle, "is_staff": False}
                    for player_id, handle in players
                ]
                + [{"id": "999", "alias": "Coach", "is_staff": True}],
            }
        ],
    }


def _nameless_match() -> dict[str, Any]:
    match = _strip_player_ids(match_900001_bo3())
    match["maps"] = [match["maps"][0]]
    return match


def _counting_team_provider(
    matches: dict[int, dict[str, Any]],
    *,
    events: dict[int, dict[str, Any]],
    teams: dict[int, dict[str, Any]],
) -> tuple[StaticVlrApiIngestionProvider, dict[str, int]]:
    counts = {"get_team": 0}

    class CountingProvider(StaticVlrApiIngestionProvider):
        def get_team(self, team_id: int) -> dict[str, Any]:
            counts["get_team"] += 1
            return super().get_team(team_id)

    provider = CountingProvider(
        matches,
        events=events,
        event_matches={91000: {"matches": [{"match_id": str(match_id)} for match_id in matches]}},
        teams=teams,
    )
    return provider, counts


def test_explicit_player_id_resolution() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(event_91000(), diagnostics=diagnostics)
    assert resolver.resolve("TenZ", 99999) == 99999
    assert diagnostics.player_identity.resolved_by_id == 1


def test_event_roster_resolution() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(event_91000(), diagnostics=diagnostics)
    assert resolver.resolve("zekken") == 92002
    assert diagnostics.player_identity.resolved_by_event_roster == 1


def test_team_roster_fallback() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(
        _event_without_players(),
        diagnostics=diagnostics,
    )
    resolver.add_team_roster(
        91001,
        _team_profile(91001, [(92001, "TenZ"), (92002, "zekken")]),
    )
    assert resolver.resolve("TenZ", team_vlr_id=91001) == 92001
    assert diagnostics.player_identity.resolved_by_team_roster == 1


def test_db_handle_fallback() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver(
        {},
        known_handles={"legacy": 4242},
        diagnostics=diagnostics,
    )
    assert resolver.resolve("Legacy") == 4242
    assert diagnostics.player_identity.resolved_by_db_handle == 1


def test_ambiguous_names_are_not_merged() -> None:
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
    assert resolver.resolve("Ace") is None
    assert diagnostics.ambiguous_player_count() == 1


def test_ambiguous_event_name_can_resolve_via_team_roster() -> None:
    event_data = {
        "segments": {
            "teams": [
                {
                    "id": "1",
                    "name": "Team A",
                    "players": [{"id": "100", "name": "Ace"}],
                },
                {
                    "id": "2",
                    "name": "Team B",
                    "players": [{"id": "101", "name": "Ace"}],
                },
            ]
        }
    }
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(event_data, diagnostics=diagnostics)
    resolver.add_team_roster(1, _team_profile(1, [(100, "Ace")]))
    assert resolver.resolve("Ace") is None
    assert resolver.resolve("Ace", team_vlr_id=1) == 100
    assert diagnostics.player_identity.resolved_by_team_roster == 1


def test_unresolved_names() -> None:
    diagnostics = IngestionDiagnostics()
    resolver = PlayerIdentityResolver.from_event_teams(
        _event_without_players(),
        diagnostics=diagnostics,
    )
    assert resolver.resolve("Nobody") is None
    assert diagnostics.unresolved_player_count() == 1


def test_team_profile_cache_fetches_each_team_once(db_session: Session) -> None:
    match_a = _nameless_match()
    match_b = copy.deepcopy(match_a)
    match_b["match_id"] = "900011"
    teams = {
        91001: _team_profile(91001, SEN_ROSTER),
        91002: _team_profile(91002, LOUD_ROSTER),
    }
    provider, counts = _counting_team_provider(
        {900001: match_a, 900011: match_b},
        events={91000: _event_without_players()},
        teams=teams,
    )
    EventIngestionService(db_session, VlrApiEventIngestionSource(provider)).ingest_event(91000)
    assert counts["get_team"] == 2


def test_identity_enrichment_on_reingestion(db_session: Session) -> None:
    match = _nameless_match()
    event = _event_with_tenz_only()
    first_provider = StaticVlrApiIngestionProvider(
        {900001: match},
        events={91000: event},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(first_provider),
    ).ingest_event(91000)
    stats_before = int(db_session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0)
    players_before = int(db_session.scalar(select(func.count()).select_from(Player)) or 0)
    assert stats_before == 1

    second_provider = StaticVlrApiIngestionProvider(
        {900001: match},
        events={91000: event},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, SEN_ROSTER),
            91002: _team_profile(91002, LOUD_ROSTER),
        },
    )
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(second_provider),
    ).ingest_event(91000)
    stats_after = int(db_session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0)
    players_after = int(db_session.scalar(select(func.count()).select_from(Player)) or 0)
    maps = int(db_session.scalar(select(func.count()).select_from(MatchMap)) or 0)
    assert stats_after == 10
    assert stats_after > stats_before
    assert players_after > players_before
    assert maps == 1
    assert summary.resolved_by_event_roster == 1
    assert summary.resolved_by_team_roster == 9


def test_idempotent_reingestion_does_not_duplicate(db_session: Session) -> None:
    provider = StaticVlrApiIngestionProvider(
        {900001: match_900001_bo3()},
        events={91000: event_91000()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    source = VlrApiEventIngestionSource(provider)
    service = EventIngestionService(db_session, source)
    first = service.ingest_event(91000)
    second = EventIngestionService(db_session, VlrApiEventIngestionSource(provider)).ingest_event(
        91000
    )
    assert first.player_map_stats_created == 20
    assert second.player_map_stats_created == 0
    assert int(db_session.scalar(select(func.count()).select_from(PlayerMapStats)) or 0) == 20


def test_map_completeness_classes() -> None:
    assert classify_player_stat_count(10) is MapCompleteness.COMPLETE
    assert classify_player_stat_count(9) is MapCompleteness.INCOMPLETE
    assert classify_player_stat_count(1) is MapCompleteness.INCOMPLETE
    assert classify_player_stat_count(0) is MapCompleteness.EMPTY


def test_map_completeness_summary(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    summary = summarize_map_completeness(db_session)
    assert summary.maps_played == 1
    assert summary.maps_incomplete == 1
    assert summary.maps_complete == 0
    assert graph["match_map"].id in summary.incomplete_map_ids


def test_cir_excludes_incomplete_maps(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    match_map = graph["match_map"]
    agent = graph["agent"]
    team_a = graph["team_a"]
    for index in range(9):
        player = Player(vlr_player_id=81000 + index, handle=f"filler{index}")
        db_session.add(player)
        db_session.flush()
        db_session.add(
            PlayerMapStats(
                match_map_id=match_map.id,
                player_id=player.id,
                team_id=team_a.id,
                agent_id=agent.id,
                rounds=21,
                kills=10 + index,
                deaths=8,
                assists=3,
                first_kills=1,
                first_deaths=1,
                adr=140.0,
                kast_pct=70.0,
                clutch_wins=1,
                clutch_attempts=2,
            )
        )
    incomplete = MatchMap(
        match_id=graph["match"].id,
        map_number=2,
        map_name="Haven",
        team_a_score=13,
        team_b_score=11,
        winner_team_id=team_a.id,
        rounds_played=24,
    )
    db_session.add(incomplete)
    db_session.flush()
    db_session.add(
        PlayerMapStats(
            match_map_id=incomplete.id,
            player_id=graph["player"].id,
            team_id=team_a.id,
            agent_id=agent.id,
            rounds=24,
            kills=12,
            deaths=10,
            assists=4,
            first_kills=2,
            first_deaths=1,
            adr=150.0,
            kast_pct=72.0,
            clutch_wins=0,
            clutch_attempts=1,
        )
    )
    db_session.flush()

    result = CIRTrainingService(db_session).train_cir_v01()
    assert result.maps_used_for_cir == 1
    assert result.maps_incomplete == 1
    assert result.maps_empty == 0
    assert result.maps_excluded_from_cir == 1


def test_canonical_agent_normalization() -> None:
    assert normalize_agent_name("Kayo") == "KAY/O"
    assert normalize_agent_name("kay/o") == "KAY/O"
    assert normalize_agent_name("Jett") == "Jett"
    assert is_known_agent("KAY/O")
    assert canonical_agent_name("Miks") == "Unknown"
    assert canonical_agent_name("Veto") == "Unknown"


def test_invalid_agent_rejection(db_session: Session) -> None:
    match = _nameless_match()
    match["maps"][0]["players"]["team1"][0]["agent"] = "Miks"
    match["maps"][0]["players"]["team1"][1]["agent"] = "Veto"
    teams = {
        91001: _team_profile(91001, SEN_ROSTER),
        91002: _team_profile(91002, LOUD_ROSTER),
    }
    provider = StaticVlrApiIngestionProvider(
        {900001: match},
        events={91000: _event_without_players()},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams=teams,
    )
    summary = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(provider),
    ).ingest_event(91000)
    assert "Miks" in summary.invalid_agent_values
    assert "Veto" in summary.invalid_agent_values
    assert summary.unknown_agent_rows >= 2
    assert db_session.scalar(select(Agent).where(Agent.name == "Miks")) is None
    assert db_session.scalar(select(Agent).where(Agent.name == "Veto")) is None
    unknown = db_session.scalar(select(Agent).where(Agent.name == "Unknown"))
    assert unknown is not None


def test_missing_clutch_stays_none() -> None:
    diagnostics = IngestionDiagnostics()
    data = VlrApiMatchNormalizer(diagnostics).normalize(match_900003_sparse(), event_id=93000)
    assert all(
        stat.clutch_wins is None and stat.clutch_attempts is None
        for stat in data.maps[0].player_stats
    )
    assert diagnostics.missing_clutch == 2


def test_clutch_feature_disable_threshold(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    stats = graph["stats"]
    assert isinstance(stats, PlayerMapStats)
    stats.clutch_wins = None
    stats.clutch_attempts = None
    db_session.flush()

    coverage = measure_clutch_coverage([stats], min_coverage=0.5)
    assert coverage.clutch_feature_enabled is False
    assert coverage.clutch_coverage_pct == 0.0

    result = CIRTrainingService(
        db_session,
        require_complete_maps=False,
        min_clutch_coverage=0.5,
    ).train_cir_v01()
    assert result.clutch_feature_enabled is False
    assert result.coefficients["clutch_rate_adjusted"] == 0.0


def test_dataset_audit_counts(db_session: Session) -> None:
    seed_match_graph(db_session)
    report = DatasetAuditService().audit(db_session)
    assert report.players == 2
    assert report.teams == 2
    assert report.events == 1
    assert report.matches == 1
    assert report.maps == 1
    assert report.player_map_stats == 1
    assert report.total_rounds == 21
    assert report.maps_incomplete == 1
    assert report.maps_complete == 0
    assert report.maps_empty == 0
    assert report.maps_eligible_for_cir == 0
    text = DatasetAuditService().format_report(report)
    assert "resolved_by_team_roster:" in text
    assert "maps_complete:" in text
    assert "players_with_100_rounds:" in text
    assert "agent_map_tier:" in text
    scale = DatasetScaleReadinessService().assess(report)
    assert scale.status == "NOT_READY"


def test_before_after_identity_quality(db_session: Session) -> None:
    match = _nameless_match()
    event = _event_without_players()
    before_provider = StaticVlrApiIngestionProvider(
        {900001: match},
        events={91000: event},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
    )
    before = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(before_provider),
    ).ingest_event(91000)
    assert before.unresolved_players == 10
    assert before.player_map_stats_created == 0
    assert before.maps_empty == 1

    after_provider = StaticVlrApiIngestionProvider(
        {900001: match},
        events={91000: event},
        event_matches={91000: {"matches": [{"match_id": "900001"}]}},
        teams={
            91001: _team_profile(91001, SEN_ROSTER),
            91002: _team_profile(91002, LOUD_ROSTER),
        },
    )
    after = EventIngestionService(
        db_session,
        VlrApiEventIngestionSource(after_provider),
    ).ingest_event(91000)
    assert after.unresolved_players == 0
    assert after.player_map_stats_created == 10
    assert after.maps_complete == 1
    assert after.resolved_by_team_roster == 10
