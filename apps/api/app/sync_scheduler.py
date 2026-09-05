from __future__ import annotations

import logging
import threading
from time import sleep

from app.config import settings
from app.services.vct_sync_runner import run_vct_sync_once, seconds_until_next_run

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    logger.info("VCT daily sync scheduler started (cron=%s)", settings.vct_sync_cron)
    while not _stop.is_set():
        wait = max(1.0, seconds_until_next_run())
        if _stop.wait(wait):
            return
        logger.info("Starting scheduled VCT sync (frozen CIR refresh, no retrain)")
        result = run_vct_sync_once()
        logger.info("Scheduled VCT sync finished: %s", result.get("status"))


def start_vct_sync_scheduler() -> None:
    global _thread
    if not settings.vct_sync_enabled:
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="vct-sync-scheduler", daemon=True)
    _thread.start()


def stop_vct_sync_scheduler() -> None:
    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)
