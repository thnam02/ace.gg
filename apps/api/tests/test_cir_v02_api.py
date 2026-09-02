from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.metrics.cir.config import CIR_NAME, CIR_V02_VERSION, MetricVersionStatus, SampleStatus
from app.models import MetricVersion, Player, PlayerMetricSnapshot
from tests.test_player_api import _seed_compare_graph


def _seed_production_snapshots(db_session: Session) -> dict[str, object]:
    graph = _seed_compare_graph(db_session)
    player: Player = graph["player"]
    teammate: Player = graph["teammate"]
    version = MetricVersion(
        name=CIR_NAME,
        version=CIR_V02_VERSION,
        status=MetricVersionStatus.PRODUCTION.value,
        training_start=None,
        training_end=None,
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
            "context_registry": {"role_tier": [], "tier": [], "global": {}},
            "context_expectations": [],
        },
        shrinkage_parameters={"k": 50, "reference_mean": 0.0},
        reference_population={"shrunk_raw_cir_values": [0.0, 0.5, 1.0]},
    )
    db_session.add(version)
    db_session.flush()
    high = PlayerMetricSnapshot(
        player_id=player.id,
        metric_version_id=version.id,
        raw_cir=0.8,
        shrunk_raw_cir=0.7,
        cir=92.0,
        combat_component=0.8,
        rounds=842,
        maps_played=40,
        events_played=3,
        sample_weight=842 / (842 + 50),
        sample_status=SampleStatus.ESTABLISHED.value,
        reliability="HIGH",
        details={
            "kpr": 0.84,
            "dpr": 0.60,
            "expected_kpr": 0.77,
            "expected_dpr": 0.65,
            "kpr_residual": 0.07,
            "negative_dpr_residual": 0.05,
            "role": "Duelist",
            "primary_agent": "Jett",
            "tier": "T1",
            "reliability_pct": 100.0,
        },
        calculated_at=datetime.now(tz=UTC),
    )
    low = PlayerMetricSnapshot(
        player_id=teammate.id,
        metric_version_id=version.id,
        raw_cir=0.1,
        shrunk_raw_cir=0.05,
        cir=40.0,
        combat_component=0.1,
        rounds=120,
        maps_played=8,
        events_played=1,
        sample_weight=120 / 170,
        sample_status=SampleStatus.PROVISIONAL.value,
        reliability="MEDIUM",
        details={
            "kpr": 0.61,
            "dpr": 0.78,
            "expected_kpr": 0.77,
            "expected_dpr": 0.65,
            "kpr_residual": -0.16,
            "negative_dpr_residual": -0.13,
            "role": "Duelist",
            "primary_agent": "Jett",
            "tier": "T1",
            "reliability_pct": 48.0,
        },
        calculated_at=datetime.now(tz=UTC),
    )
    db_session.add_all([high, low])
    db_session.flush()
    graph["metric_version"] = version
    return graph


def test_rankings_default_to_established(client: TestClient, db_session: Session) -> None:
    _seed_production_snapshots(db_session)
    response = client.get("/rankings/cir")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["players"][0]["handle"] == "TenZ"
    assert payload["players"][0]["rank"] == 1
    assert payload["players"][0]["cir"] == 92.0
    assert payload["players"][0]["sample_status"] == "ESTABLISHED"


def test_rankings_include_provisional_and_pagination(
    client: TestClient, db_session: Session
) -> None:
    _seed_production_snapshots(db_session)
    response = client.get("/rankings/cir", params={"include_provisional": True, "limit": 1})
    payload = response.json()
    assert payload["total"] == 2
    assert payload["limit"] == 1
    assert len(payload["players"]) == 1
    page_two = client.get(
        "/rankings/cir", params={"include_provisional": True, "limit": 1, "offset": 1}
    ).json()
    assert page_two["players"][0]["handle"] == "zekken"
    assert page_two["players"][0]["rank"] == 2


def test_rankings_are_deterministic(client: TestClient, db_session: Session) -> None:
    graph = _seed_production_snapshots(db_session)
    extra = Player(
        vlr_player_id=88,
        handle="aaa",
    )
    db_session.add(extra)
    db_session.flush()
    version = graph["metric_version"]
    db_session.add(
        PlayerMetricSnapshot(
            player_id=extra.id,
            metric_version_id=version.id,
            cir=92.0,
            raw_cir=0.8,
            shrunk_raw_cir=0.7,
            combat_component=0.8,
            rounds=900,
            maps_played=41,
            sample_status=SampleStatus.ESTABLISHED.value,
            reliability="HIGH",
            details={"role": "Sentinel"},
        )
    )
    db_session.flush()
    payload = client.get("/rankings/cir").json()
    handles = [row["handle"] for row in payload["players"]]
    assert handles == ["aaa", "TenZ"]


def test_player_cir_and_metadata_endpoints(client: TestClient, db_session: Session) -> None:
    graph = _seed_production_snapshots(db_session)
    player = graph["player"]
    detail = client.get(f"/players/{player.id}/cir")
    assert detail.status_code == 200
    body = detail.json()
    assert body["cir"] == 92.0
    assert body["kpr"] == 0.84
    assert body["expected_kpr"] == 0.77
    assert "z_kpr" not in body
    meta = client.get("/metrics/cir")
    assert meta.status_code == 200
    assert meta.json()["version"] == CIR_V02_VERSION
    assert "90th percentile" in meta.json()["tooltip"]
    assert "true player value" not in meta.json()["description"].lower()


def test_compare_includes_cir_inputs(client: TestClient, db_session: Session) -> None:
    graph = _seed_production_snapshots(db_session)
    response = client.get(
        "/players/compare",
        params={"player_ids": [str(graph["player"].id), str(graph["teammate"].id)]},
    )
    assert response.status_code == 200
    payload = response.json()
    tenz = next(item for item in payload["players"] if item["player"]["handle"] == "TenZ")
    assert tenz["cir"]["cir"] == 92.0
    assert tenz["cir"]["kpr_residual"] == 0.07
    dedicated = client.get(
        "/players/compare/cir",
        params={"player_ids": [str(graph["player"].id), str(graph["teammate"].id)]},
    )
    assert dedicated.status_code == 200
    assert len(dedicated.json()["players"]) == 2
