from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics.cir.config import CIR_NAME, CIR_V02_VERSION, MetricVersionStatus, SampleStatus
from app.models import Event, MetricVersion, Player, PlayerMapStats, PlayerMetricSnapshot
from tests.factories import seed_match_graph
from tests.test_cir_v02_api import _seed_production_snapshots


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
    event.region = "INTL"
    event.name = "Champions 2024"
    match_map = graph["match_map"]
    team = graph["team_a"]
    agent = graph["agent"]
    # Complete maps need 10 player rows.
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
            )
        )
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
            status="completed",
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
    assert payload["scope"] == "event"
    assert payload["vlr_event_id"] == event.vlr_event_id
    assert payload["event_name"] == event.name
    assert payload["total"] >= 1
    assert payload["players"][0]["cir"] is not None
    assert "season reference" in (payload["note"] or "").lower()

    after = db_session.scalar(
        select(func.count()).select_from(PlayerMetricSnapshot).where(
            PlayerMetricSnapshot.metric_version_id == version.id
        )
    )
    assert after == before == 0


def test_event_cir_unknown_event_returns_404(client: TestClient, db_session: Session) -> None:
    _seed_production_snapshots(db_session)
    response = client.get("/rankings/cir/by-event/999999")
    assert response.status_code == 404


def test_season_rankings_keep_season_scope(client: TestClient, db_session: Session) -> None:
    _seed_production_snapshots(db_session)
    payload = client.get("/rankings/cir").json()
    assert payload["scope"] == "season"
    assert payload["vlr_event_id"] is None
