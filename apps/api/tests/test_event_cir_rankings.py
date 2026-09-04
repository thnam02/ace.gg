from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics.cir.config import (
    CIR_NAME,
    CIR_V02_VERSION,
    SHRINKAGE_K,
    MetricVersionStatus,
    SampleStatus,
)
from app.metrics.cir.scope import ScopeType
from app.models import (
    Event,
    MetricVersion,
    Player,
    PlayerMapStats,
    PlayerMetricScopedSnapshot,
    PlayerMetricSnapshot,
)
from app.services.event_cir_snapshot_service import EventCirSnapshotService
from tests.factories import seed_match_graph
from tests.test_cir_v02_api import _seed_production_snapshots


def _scope_type(payload: dict) -> str:
    scope = payload.get("scope")
    if isinstance(scope, dict):
        return str(scope.get("type") or "")
    return str(scope or "")


def _frozen_context_registry() -> dict[str, object]:
    return {
        "role_tier": [
            {
                "role": "Duelist",
                "tier": "S",
                "rounds": 500,
                "kills": 400,
                "deaths": 350,
                "observation_count": 20,
            }
        ],
        "tier": [
            {
                "tier": "S",
                "rounds": 500,
                "kills": 380,
                "deaths": 360,
                "observation_count": 20,
            }
        ],
        "global": {
            "rounds": 1000,
            "kills": 750,
            "deaths": 720,
            "observation_count": 40,
        },
    }


def _seed_event_scoring_graph(db_session: Session) -> dict[str, object]:
    graph = seed_match_graph(db_session)
    event: Event = graph["event"]
    event.region = "Pacific"
    event.tier = "T1"
    event.name = "VCT 2026 Pacific Stage 2"
    event.season_year = 2026
    event.status = "ONGOING"
    match_map = graph["match_map"]
    team = graph["team_a"]
    agent = graph["agent"]
    for index in range(9):
        filler = Player(vlr_player_id=9000 + index, handle=f"filler{index}")
        db_session.add(filler)
        db_session.flush()
        db_session.add(
            PlayerMapStats(
                match_map_id=match_map.id,
                player_id=filler.id,
                team_id=team.id,
                agent_id=agent.id,
                rounds=21,
                kills=12,
                deaths=12,
                assists=3,
                first_kills=1,
                first_deaths=1,
                adr=140.0,
                acs=220.0,
                kast_pct=70.0,
                headshot_pct=25.0,
            )
        )
    primary_stats: PlayerMapStats = graph["stats"]
    primary_stats.rounds = 143
    primary_stats.kills = 110
    primary_stats.deaths = 89
    primary_stats.assists = 40
    primary_stats.first_kills = 20
    primary_stats.first_deaths = 15
    primary_stats.adr = 155.0
    primary_stats.acs = 240.0
    primary_stats.kast_pct = 72.0
    primary_stats.headshot_pct = 28.0

    version = MetricVersion(
        name=CIR_NAME,
        version=CIR_V02_VERSION,
        status=MetricVersionStatus.PRODUCTION.value,
        feature_names=["kpr_residual", "negative_dpr_residual"],
        standardization_parameters={
            "means": {"kpr_residual": 0.0, "negative_dpr_residual": 0.0},
            "stds": {"kpr_residual": 1.0, "negative_dpr_residual": 1.0},
            "mu_kpr": 0.0,
            "sigma_kpr": 1.0,
            "mu_negative_dpr": 0.0,
            "sigma_negative_dpr": 1.0,
        },
        model_coefficients={
            "combat_factor_type": "equal_weight_standardized",
            "pca_equivalent": True,
        },
        regularization_parameters={
            "lambda": 1.0,
            "tau": 500.0,
            "context_type": "context_v2",
            "context_registry": _frozen_context_registry(),
            "context_expectations": [],
        },
        shrinkage_parameters={"k": 50, "reference_mean": 0.0},
        reference_population={"shrunk_raw_cir_values": [-1.0, 0.0, 0.5, 1.0]},
    )
    db_session.add(version)
    db_session.flush()
    graph["metric_version"] = version
    return graph


def test_list_events_filters_by_canonical_region(
    client: TestClient, db_session: Session
) -> None:
    seed_match_graph(db_session)
    db_session.add(
        Event(
            vlr_event_id=2097,
            name="VCT 2026: Americas Kickoff",
            region="NA",
            tier="T1",
            season_year=2026,
            status="COMPLETED",
        )
    )
    db_session.flush()

    americas = client.get("/events", params={"region": "Americas"}).json()
    assert americas["total"] >= 1
    assert all(row["canonical_region"] == "Americas" for row in americas["events"])
    assert any(row["vlr_event_id"] == 2097 for row in americas["events"])

    intl = client.get("/events", params={"region": "INTL"}).json()
    assert any(row["vlr_event_id"] == 1188 for row in intl["events"])

    bad = client.get("/events", params={"region": "not-a-region"})
    assert bad.status_code == 400


def test_list_events_filters_by_tier_and_year(client: TestClient, db_session: Session) -> None:
    seed_match_graph(db_session)
    db_session.add(
        Event(
            vlr_event_id=3001,
            name="T2 Pacific Cup",
            region="Pacific",
            tier="T2",
            season_year=2026,
            status="COMPLETED",
        )
    )
    db_session.flush()
    t1 = client.get("/events", params={"year": 2026, "tier": "T1", "region": "Pacific"}).json()
    assert all((row["tier"] or "").upper() == "T1" for row in t1["events"])
    t2 = client.get("/events", params={"year": 2026, "tier": "T2"}).json()
    assert any(row["vlr_event_id"] == 3001 for row in t2["events"])


def test_event_cir_rankings_score_without_writing_season_snapshots(
    client: TestClient, db_session: Session
) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    version: MetricVersion = graph["metric_version"]
    before = db_session.scalar(
        select(func.count()).select_from(PlayerMetricSnapshot).where(
            PlayerMetricSnapshot.metric_version_id == version.id
        )
    )

    response = client.get(f"/rankings/cir/by-event/{event.vlr_event_id}")
    assert response.status_code == 200
    payload = response.json()
    assert _scope_type(payload) == "EVENT"
    assert payload["vlr_event_id"] == event.vlr_event_id
    assert payload["event_name"] == event.name
    assert payload["total"] >= 1
    assert payload["players"][0]["cir"] is not None
    assert "frozen v0.2" in (payload["note"] or "").lower()

    after = db_session.scalar(
        select(func.count()).select_from(PlayerMetricSnapshot).where(
            PlayerMetricSnapshot.metric_version_id == version.id
        )
    )
    assert after == before == 0


def test_rankings_cir_event_id_query(client: TestClient, db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    response = client.get("/rankings/cir", params={"event_id": str(event.id)})
    assert response.status_code == 200
    payload = response.json()
    assert _scope_type(payload) == "EVENT"
    assert payload["event_id"] == str(event.id)
    assert payload["scope"]["label"] == event.name
    assert payload["scope"]["tier"] == "T1"
    player = payload["players"][0]
    assert player["rank_label"] == "Event rank"
    assert player["sample_status"] in {
        SampleStatus.LOW_SAMPLE.value,
        SampleStatus.PROVISIONAL.value,
        SampleStatus.ESTABLISHED.value,
    }


def test_event_cir_unknown_event_returns_404(client: TestClient, db_session: Session) -> None:
    _seed_production_snapshots(db_session)
    response = client.get("/rankings/cir/by-event/999999")
    assert response.status_code == 404
    missing_uuid = client.get(
        "/rankings/cir",
        params={"event_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert missing_uuid.status_code == 404


def test_season_rankings_keep_global_scope(client: TestClient, db_session: Session) -> None:
    _seed_production_snapshots(db_session)
    payload = client.get("/rankings/cir").json()
    assert _scope_type(payload) == "GLOBAL_2026"
    assert payload["vlr_event_id"] is None
    assert payload["scope"]["label"] == "2026 CIR"


def test_event_snapshot_backfill_idempotent(db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    service = EventCirSnapshotService(db_session, require_complete_maps=True)
    first = service.refresh_events([event])
    db_session.commit()
    count_after_first = db_session.scalar(
        select(func.count()).select_from(PlayerMetricScopedSnapshot)
    )
    assert first.snapshots_upserted >= 1
    assert count_after_first == first.snapshots_upserted

    second = service.refresh_events([event])
    db_session.commit()
    count_after_second = db_session.scalar(
        select(func.count()).select_from(PlayerMetricScopedSnapshot)
    )
    assert count_after_second == count_after_first
    assert second.snapshots_upserted == first.snapshots_upserted


def test_event_kpr_dpr_and_shrinkage_use_event_rounds(db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    primary: Player = graph["player"]
    service = EventCirSnapshotService(db_session, require_complete_maps=True)
    bundles, _, _ = service.refresh_event(event)
    db_session.commit()
    bundle = next(item for item in bundles if item.score.player_id == primary.id)
    assert bundle.score.rounds == 143
    assert bundle.score.kpr == pytest.approx(110 / 143)
    assert bundle.score.dpr == pytest.approx(89 / 143)
    assert bundle.score.sample_weight == pytest.approx(143 / (143 + SHRINKAGE_K))
    assert bundle.apr == pytest.approx(40 / 143)
    assert bundle.fk_per_round == pytest.approx(20 / 143)
    assert bundle.fd_per_round == pytest.approx(15 / 143)
    assert bundle.opening_frequency == pytest.approx(35 / 143)
    assert bundle.opening_efficiency == pytest.approx(20 / 35)
    assert bundle.kd == pytest.approx(110 / 89)
    assert bundle.score.sample_status == SampleStatus.PROVISIONAL.value

    snap = db_session.scalar(
        select(PlayerMetricScopedSnapshot).where(
            PlayerMetricScopedSnapshot.player_id == primary.id,
            PlayerMetricScopedSnapshot.scope_type == ScopeType.EVENT.value,
            PlayerMetricScopedSnapshot.scope_id == str(event.id),
        )
    )
    assert snap is not None
    assert snap.rounds == 143
    assert snap.kpr == pytest.approx(110 / 143)


def test_event_player_cir_endpoint(client: TestClient, db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    primary: Player = graph["player"]
    EventCirSnapshotService(db_session, require_complete_maps=True).refresh_event(event)
    db_session.commit()

    response = client.get(
        f"/players/{primary.id}/cir",
        params={"event_id": str(event.id)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rounds"] == 143
    assert payload["event_rank"] is not None
    assert payload["scope"]["type"] == "EVENT"
    assert "event only" in (payload["note"] or "").lower()


def test_upcoming_event_empty(client: TestClient, db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    event.status = "UPCOMING"
    db_session.flush()
    payload = client.get("/rankings/cir", params={"event_id": str(event.id)}).json()
    assert payload["total"] == 0
    assert "no completed maps" in (payload["note"] or "").lower()


def test_event_min_rounds_and_search(client: TestClient, db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    EventCirSnapshotService(db_session, require_complete_maps=True).refresh_event(event)
    db_session.commit()

    all_players = client.get("/rankings/cir", params={"event_id": str(event.id)}).json()
    filtered = client.get(
        "/rankings/cir",
        params={"event_id": str(event.id), "min_rounds": 100},
    ).json()
    assert filtered["total"] <= all_players["total"]
    assert all(row["rounds"] >= 100 for row in filtered["players"])

    search = client.get(
        "/rankings/cir",
        params={"event_id": str(event.id), "search": "tenz"},
    ).json()
    assert all("tenz" in row["handle"].lower() for row in search["players"])


def test_global_snapshots_unchanged_by_event_backfill(db_session: Session) -> None:
    graph = _seed_event_scoring_graph(db_session)
    event: Event = graph["event"]
    version: MetricVersion = graph["metric_version"]
    player: Player = graph["player"]
    db_session.add(
        PlayerMetricSnapshot(
            player_id=player.id,
            metric_version_id=version.id,
            cir=99.8,
            raw_cir=1.0,
            shrunk_raw_cir=0.9,
            combat_component=1.0,
            rounds=977,
            maps_played=40,
            events_played=5,
            sample_status=SampleStatus.ESTABLISHED.value,
            reliability="HIGH",
            details={"kpr": 0.82, "dpr": 0.58},
            calculated_at=datetime.now(tz=UTC),
        )
    )
    db_session.flush()
    before = db_session.scalar(
        select(PlayerMetricSnapshot).where(PlayerMetricSnapshot.player_id == player.id)
    )
    assert before is not None
    before_cir = before.cir
    before_rounds = before.rounds

    EventCirSnapshotService(db_session, require_complete_maps=True).refresh_event(event)
    db_session.commit()

    after = db_session.scalar(
        select(PlayerMetricSnapshot).where(PlayerMetricSnapshot.player_id == player.id)
    )
    assert after is not None
    assert after.cir == before_cir
    assert after.rounds == before_rounds
