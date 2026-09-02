from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.db import SessionLocal
from app.schemas.ingestion import BulkIngestionSummary, EventIngestionSummary
from app.services.dataset_audit_service import DatasetAuditService
from app.services.dataset_scale_readiness import DatasetScaleReadinessService
from app.services.dataset_training_readiness import DatasetTrainingReadinessService
from app.services.json_event_ingestion import ingest_json_events


def _format_event_summary(summary: EventIngestionSummary) -> str:
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
            f"resolved_by_event_roster: {summary.resolved_by_event_roster}",
            f"resolved_by_team_roster: {summary.resolved_by_team_roster}",
            f"resolved_by_history: {summary.resolved_by_history}",
            f"resolved_by_db_identity: {summary.resolved_by_db_identity}",
            f"resolved_by_search: {summary.resolved_by_search}",
            f"invalid_agent_values: {summary.invalid_agent_values}",
            f"unknown_agent_rows: {summary.unknown_agent_rows}",
            f"maps_complete: {summary.maps_complete}",
            f"maps_incomplete: {summary.maps_incomplete}",
            f"maps_empty: {summary.maps_empty}",
            f"http_429_count: {summary.http_429_count}",
            f"cache_hits: {summary.cache_hits}",
            f"cache_misses: {summary.cache_misses}",
            f"dry_run: {summary.dry_run}",
        ]
    )


def _format_bulk_summary(summary: BulkIngestionSummary) -> str:
    return "\n".join(
        [
            "bulk_ingestion:",
            f"  events_requested: {summary.events_requested}",
            f"  events_completed: {summary.events_completed}",
            f"  events_failed: {summary.events_failed}",
            f"  matches_discovered: {summary.matches_discovered}",
            f"  matches_ingested: {summary.matches_ingested}",
            f"  maps: {summary.maps}",
            f"  player_map_stats: {summary.player_map_stats}",
            f"  resolved_by_event_roster: {summary.resolved_by_event_roster}",
            f"  resolved_by_team_roster: {summary.resolved_by_team_roster}",
            f"  resolved_by_history: {summary.resolved_by_history}",
            f"  resolved_by_search: {summary.resolved_by_search}",
            f"  ambiguous: {summary.ambiguous}",
            f"  unresolved: {summary.unresolved}",
            f"  complete_maps: {summary.complete_maps}",
            f"  incomplete_maps: {summary.incomplete_maps}",
            f"  empty_maps: {summary.empty_maps}",
            f"  http_429_count: {summary.http_429_count}",
            f"  cache_hits: {summary.cache_hits}",
            f"  cache_misses: {summary.cache_misses}",
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
    parser.add_argument(
        "--audit-after",
        action="store_true",
        help="Run the dataset audit after ingestion completes",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cache_dir = Path(args.raw_cache_dir) if args.raw_cache_dir else None
    with SessionLocal() as session:
        bulk = ingest_json_events(
            session,
            args.event_ids,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            raw_cache_dir=cache_dir,
        )
        if not args.dry_run:
            session.commit()
        for summary in bulk.event_summaries:
            print(_format_event_summary(summary))
            print("")
        print(_format_bulk_summary(bulk))
        if args.audit_after and not args.dry_run:
            audit = DatasetAuditService().audit(session, ingest_summaries=bulk.event_summaries)
            print("")
            print(DatasetAuditService().format_report(audit))
            print("")
            print(
                DatasetScaleReadinessService().format_report(
                    DatasetScaleReadinessService().assess(audit)
                )
            )
            print("")
            print(
                DatasetTrainingReadinessService().format_report(
                    DatasetTrainingReadinessService().assess(audit)
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
