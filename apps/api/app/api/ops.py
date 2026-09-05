from __future__ import annotations

import hmac
import threading

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.vct_sync_runner import (
    latest_sync_status,
    run_vct_sync_once,
    sync_is_running,
)

router = APIRouter(prefix="/ops", tags=["ops"])


class VctSyncTriggerResponse(BaseModel):
    status: str
    message: str


def _require_sync_token(x_sync_token: str | None) -> None:
    expected = settings.vct_sync_token.strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    provided = (x_sync_token or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid sync token")


@router.get("/vct-sync")
def get_vct_sync_status(
    x_sync_token: str | None = Header(default=None, alias="X-Sync-Token"),
) -> dict[str, object]:
    _require_sync_token(x_sync_token)
    return latest_sync_status()


@router.post("/vct-sync", response_model=VctSyncTriggerResponse)
def trigger_vct_sync(
    x_sync_token: str | None = Header(default=None, alias="X-Sync-Token"),
) -> VctSyncTriggerResponse:
    _require_sync_token(x_sync_token)
    if sync_is_running():
        raise HTTPException(status_code=409, detail="Sync already running")

    def _job() -> None:
        run_vct_sync_once()

    threading.Thread(target=_job, name="vct-sync-manual", daemon=True).start()
    return VctSyncTriggerResponse(
        status="started",
        message="Ingesting new maps and refreshing frozen CIR snapshots. CIR is not retrained.",
    )
