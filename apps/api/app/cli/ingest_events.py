from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db import SessionLocal
from app.schemas.ingestion import EventIngestionSummary
from app.services.json_event_ingestion import ingest_json_events


def _format_summary(summary: EventIngestionSummary) -> str:
    return "\n".join(
        [
            f"event_id: {summary.event_id}",
            f"matches_discovered: {summary.matches_discovered}",
            f"matches_ingested: {summary.matches_ingested}",
            f"matches_skipped: {summary.matches_skipped}",
            f"matches_failed: {summary.matches_failed}",
            f"maps_created: {summary.maps_created}",
            f"player_map_stats_created: {summary.player_map_stats_created}",
            f"missing_rounds: {summary.missing_rounds}",
            f"missing_kast: {summary.missing_kast}",
            f"missing_clutch: {summary.missing_clutch}",
            f"unresolved_players: {summary.unresolved_players}",
            f"ambiguous_players: {summary.ambiguous_players}",
            f"resolved_by_id: {summary.resolved_by_id}",
            f"resolved_by_roster: {summary.resolved_by_roster}",
            f"resolved_by_name: {summary.resolved_by_name}",
            f"dry_run: {summary.dry_run}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest multiple VLR events via vlrggapi JSON")
    parser.add_argument("event_ids", type=int, nargs="+", help="VLR event IDs")
    parser.add_argument("--dry-run", action="store_true", help="Normalize without DB writes")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue ingesting remaining events after a failure",
    )
    parser.add_argument(
        "--raw-cache-dir",
        type=str,
        default=None,
        help="Optional directory to persist raw vlrggapi JSON",
    )
    args = parser.parse_args(argv)

    cache_dir = Path(args.raw_cache_dir) if args.raw_cache_dir else None
    with SessionLocal() as session:
        summaries = ingest_json_events(
            session,
            args.event_ids,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            raw_cache_dir=cache_dir,
        )
        if not args.dry_run:
            session.commit()
        for summary in summaries:
            print(_format_summary(summary))
            print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
