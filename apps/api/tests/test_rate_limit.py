from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import settings
from app.rate_limit import client_ip, reset_rate_limiter


def test_ops_vct_sync_is_exempt_from_rate_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "vct_sync_token", "")
    reset_rate_limiter()

    first = client.post("/ops/vct-sync")
    second = client.post("/ops/vct-sync")
    assert first.status_code == 404
    assert second.status_code == 404


def test_health_is_exempt_from_rate_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    reset_rate_limiter()

    first = client.get("/health")
    second = client.get("/health")
    assert first.status_code == 200
    assert second.status_code == 200


def test_rate_limit_returns_429_after_burst(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    monkeypatch.setattr(settings, "rate_limit_compare_per_minute", 2)
    reset_rate_limiter()

    assert client.get("/metrics/cir").status_code != 429
    assert client.get("/metrics/cir").status_code != 429
    blocked = client.get("/metrics/cir")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded"
    assert blocked.headers.get("retry-after")


def test_compare_bucket_is_stricter_than_general(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 100)
    monkeypatch.setattr(settings, "rate_limit_compare_per_minute", 1)
    reset_rate_limiter()

    first = client.get("/players/compare", params={"player_ids": ["missing-a", "missing-b"]})
    second = client.get("/players/compare", params={"player_ids": ["missing-a", "missing-b"]})
    assert first.status_code != 429
    assert second.status_code == 429


def test_client_ip_uses_last_forwarded_hop() -> None:
    request = Request(
        {
            "type": "http",
            "asgi": {"spec_version": "2.4", "version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"9.9.9.9, 10.0.0.1")],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
        }
    )
    assert client_ip(request) == "10.0.0.1"
