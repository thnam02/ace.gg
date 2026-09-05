from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services.vct_sync_runner import parse_daily_cron, seconds_until_next_run


def test_parse_daily_cron_reads_hour_and_minute() -> None:
    assert parse_daily_cron("15 4 * * *") == (15, 4)
    assert parse_daily_cron("not-a-cron") == (0, 3)


def test_seconds_until_next_run_is_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vct_sync_cron", "0 3 * * *")
    now = datetime(2026, 9, 5, 2, 0, tzinfo=UTC)
    wait = seconds_until_next_run(now=now)
    assert wait == 3600.0


def test_ops_sync_hidden_without_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vct_sync_token", "")
    response = client.post("/ops/vct-sync")
    assert response.status_code == 404


def test_ops_sync_rejects_bad_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vct_sync_token", "secret-token")
    response = client.post("/ops/vct-sync", headers={"X-Sync-Token": "nope"})
    assert response.status_code == 401


def test_ops_sync_starts_with_valid_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vct_sync_token", "secret-token")
    started = threading.Event()

    def _fake_sync(*, force: bool = False) -> dict[str, object]:
        del force
        started.set()
        return {"status": "SUCCESS", "retrained_cir": False}

    monkeypatch.setattr("app.api.ops.run_vct_sync_once", _fake_sync)
    response = client.post("/ops/vct-sync", headers={"X-Sync-Token": "secret-token"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert "not retrained" in payload["message"].lower()
    assert started.wait(timeout=2.0)


def test_ops_sync_conflict_when_running(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vct_sync_token", "secret-token")
    monkeypatch.setattr("app.api.ops.sync_is_running", lambda: True)
    response = client.post("/ops/vct-sync", headers={"X-Sync-Token": "secret-token"})
    assert response.status_code == 409


def test_ops_sync_status_requires_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vct_sync_token", "secret-token")
    missing = client.get("/ops/vct-sync")
    assert missing.status_code == 401
    ok = client.get("/ops/vct-sync", headers={"X-Sync-Token": "secret-token"})
    assert ok.status_code == 200
    assert "running" in ok.json()
