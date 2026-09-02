from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.models import Event
from app.providers.vlrggapi_raw_cache import VlrggApiRawCache
from app.services.sample_validation_service import SampleValidationService


def _pick_match_ids(session: Session, *, per_event: int) -> list[int]:
    events = session.scalars(select(Event).options(selectinload(Event.matches))).all()
    selected: list[int] = []
    for event in events:
        completed = [
            match
            for match in event.matches
            if match.status == "completed" or match.winner_team_id is not None
        ]
        completed.sort(key=lambda match: match.vlr_match_id)
        selected.extend(match.vlr_match_id for match in completed[:per_event])
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare DB rows to cached vlrggapi JSON")
    parser.add_argument(
        "--raw-cache-dir",
        type=str,
        required=True,
        help="Directory used during ingestion to persist raw vlrggapi JSON",
    )
    parser.add_argument(
        "--per-event",
        type=int,
        default=2,
        help="Number of matches to sample from each event",
    )
    parser.add_argument(
        "match_ids",
        type=int,
        nargs="*",
        help="Optional explicit VLR match IDs to compare",
    )
    args = parser.parse_args(argv)

    cache = VlrggApiRawCache(Path(args.raw_cache_dir))
    with SessionLocal() as session:
        match_ids = args.match_ids or _pick_match_ids(session, per_event=args.per_event)
        report = SampleValidationService().validate(session, cache, match_ids=match_ids)
        print(SampleValidationService().format_report(report))
        print("sampled_match_ids:")
        for match_id in match_ids:
            print(f"  {match_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
