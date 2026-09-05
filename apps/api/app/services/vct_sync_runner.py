from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from app.config import settings
from app.db import SessionLocal
from app.services.vct_sync_service import VctDailySyncService, latest_sync_run

_RUN_LOCK = Lock()
_STATE_LOCK = Lock()
_running = False
_last_error: str | None = None


def parse_daily_cron(expr: str) -> tuple[int, int]:
    """Return (minute, hour) for a daily `M H * * *` cron. Fallback 03:00 UTC."""
    parts = expr.split()
    if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
        minute = int(parts[0])
        hour = int(parts[1])
        if 0 <= minute <= 59 and 0 <= hour <= 23:
            return minute, hour
    return 0, 3


def seconds_until_next_run(*, now: datetime | None = None) -> float:
    current = now or datetime.now(tz=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    minute, hour = parse_daily_cron(settings.vct_sync_cron)
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return (target - current).total_seconds()


def sync_is_running() -> bool:
    with _STATE_LOCK:
        return _running


def latest_sync_status() -> dict[str, Any]:
    with SessionLocal() as session:
        run = latest_sync_run(session)
        if run is None:
            return {
                "running": sync_is_running(),
                "last_status": None,
                "last_started_at": None,
                "last_finished_at": None,
                "last_error": _last_error,
            }
        report = run.report if isinstance(run.report, dict) else {}
        return {
            "running": sync_is_running(),
            "last_status": run.status,
            "last_started_at": run.started_at.isoformat() if run.started_at else None,
            "last_finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "matches_added": report.get("matches_added"),
            "cir_snapshots_refreshed": report.get("cir_snapshots_refreshed"),
            "retrained_cir": report.get("retrained_cir"),
            "last_error": _last_error,
        }


def run_vct_sync_once(*, force: bool = False) -> dict[str, Any]:
    """Ingest new VCT maps and refresh frozen CIR snapshots. Does not retrain."""
    global _running, _last_error
    if not _RUN_LOCK.acquire(blocking=False):
        return {"status": "already_running"}
    with _STATE_LOCK:
        _running = True
    try:
        with SessionLocal() as session:
            service = VctDailySyncService(session)
            report = service.sync(force=force, continue_on_error=True)
            session.commit()
            _last_error = None if not report.errors else "; ".join(report.errors[:5])
            return {
                "status": report.job_status.value,
                "matches_added": report.matches_added,
                "cir_snapshots_refreshed": report.cir_snapshots_refreshed,
                "retrained_cir": report.retrained_cir,
                "v02_parameters_frozen": report.v02_parameters_frozen,
                "errors": report.errors[:8],
            }
    except Exception as exc:  # noqa: BLE001 — persist failure for /ops status
        _last_error = str(exc)
        return {"status": "FAILED", "errors": [str(exc)]}
    finally:
        with _STATE_LOCK:
            _running = False
        _RUN_LOCK.release()
