from __future__ import annotations

import argparse
import json
import sys
from uuid import UUID

from app.db import SessionLocal
from app.metrics.cir.config import CIR_V02_VERSION
from app.services.event_cir_snapshot_service import EventCirSnapshotService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill event-scoped CIR snapshots using frozen CIR v0.2 parameters. "
            "Does not refit expectations, standardization, shrinkage k, or the "
            "reference CDF. Observation window = eligible maps inside each event."
        )
    )
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--event-id", type=str, default=None)
    parser.add_argument("--tier", type=str, default=None)
    parser.add_argument("--region", type=str, default=None)
    parser.add_argument("--version", default=CIR_V02_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-incomplete-maps", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    event_uuid: UUID | None = None
    if args.event_id:
        try:
            event_uuid = UUID(args.event_id)
        except ValueError:
            print(f"Invalid --event-id: {args.event_id}")
            return 1

    with SessionLocal() as session:
        service = EventCirSnapshotService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
        )
        events = service.list_backfill_events(
            year=args.year,
            event_id=event_uuid,
            tier=args.tier,
            region=args.region,
        )
        if not events:
            print("event_cir_backfill:")
            print("  events_processed: 0")
            print("  note: no matching COMPLETED/ONGOING events")
            return 0

        result = service.refresh_events(
            events,
            version=args.version,
            dry_run=args.dry_run,
            force=args.force,
        )
        if not args.dry_run:
            session.commit()

        print("event_cir_backfill:")
        print(f"  version: {args.version}")
        print(f"  dry_run: {args.dry_run}")
        print(f"  events_processed: {result.events_processed}")
        print(f"  players_scored: {result.players_scored}")
        print(f"  snapshots_upserted: {result.snapshots_upserted}")
        print(f"  snapshots_deleted: {result.snapshots_deleted}")
        print(f"  errors: {len(result.errors or [])}")
        print("  note: MetricVersion parameters were not refit; k=50 uses event rounds")
        if result.errors:
            for error in result.errors:
                print(f"  error: {error}")
        if args.json:
            print("")
            print(
                json.dumps(
                    {
                        "version": args.version,
                        "dry_run": args.dry_run,
                        "events_processed": result.events_processed,
                        "players_scored": result.players_scored,
                        "snapshots_upserted": result.snapshots_upserted,
                        "snapshots_deleted": result.snapshots_deleted,
                        "event_ids": result.event_ids,
                        "errors": result.errors,
                    },
                    default=str,
                )
            )
        return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
