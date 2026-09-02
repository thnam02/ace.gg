from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.schemas.vct_circuit import EventStatus
from app.services.vct_sync_service import VctDailySyncService, format_vct_sync_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Discover official VCT events from /vct and incrementally ingest "
            "completed/ongoing matches. Refreshes frozen CIR snapshots; does not retrain."
        )
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-ingest completed events")
    parser.add_argument("--event-id", type=int, default=None)
    parser.add_argument(
        "--status",
        choices=[item.value for item in EventStatus],
        default=None,
    )
    parser.add_argument("--skip-snapshot-refresh", action="store_true")
    parser.add_argument("--season-year", type=int, default=None)
    parser.add_argument("--raw-cache-dir", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    cache_dir = Path(args.raw_cache_dir) if args.raw_cache_dir else None
    status = EventStatus(args.status) if args.status else None
    with SessionLocal() as session:
        service = VctDailySyncService(
            session,
            season_year=args.season_year or settings.vct_sync_season_year,
            raw_cache_dir=cache_dir,
        )
        report = service.sync(
            dry_run=args.dry_run,
            force=args.force,
            event_id=args.event_id,
            status=status,
            skip_snapshot_refresh=args.skip_snapshot_refresh,
            continue_on_error=True,
        )
        if not args.dry_run:
            session.commit()
        print(format_vct_sync_report(report))
        if args.json:
            print("")
            print(json.dumps(report.model_dump(mode="json"), default=str, indent=2))
        if report.job_status.value == "FAILED":
            return 1
        if report.job_status.value == "PARTIAL_SUCCESS":
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
