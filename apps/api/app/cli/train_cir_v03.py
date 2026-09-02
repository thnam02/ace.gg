from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.metrics.cir.config import CIR_NAME, CIR_V02_VERSION, CIR_V03_VERSION, MetricVersionStatus
from app.models import Event, Match, MetricVersion
from app.schemas.team_rating import TeamRatingRebuildSummary
from app.schemas.vct_circuit import CircuitName, EventStatus
from app.services.cir_v02_training_service import CirV02TrainingService, CirVersionExistsError
from app.services.team_rating_service import TeamRatingService


def _format_elo(summary: TeamRatingRebuildSummary) -> str:
    return "\n".join(
        [
            f"matches_processed: {summary.matches_processed}",
            f"teams_rated: {summary.teams_rated}",
        ]
    )


def _missing_completed_event_ids(session: Session) -> list[int]:
    missing: list[int] = []
    events = session.scalars(
        select(Event).where(
            Event.circuit == CircuitName.VCT.value,
            Event.season_year == 2026,
        )
    ).all()
    for event in events:
        if (event.status or "").upper() != EventStatus.COMPLETED.value:
            continue
        matches = (
            session.scalar(select(func.count(Match.id)).where(Match.event_id == event.id)) or 0
        )
        if matches == 0:
            missing.append(event.vlr_event_id)
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Train CIR v0.3-vct-2026 on the full official VCT corpus. "
            "Does not overwrite CIR v0.2-real-2026 or promote v0.3 to PRODUCTION."
        )
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-new-version", action="store_true")
    parser.add_argument("--bootstrap-iterations", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-incomplete-maps", action="store_true")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        missing = _missing_completed_event_ids(session)
        if missing and not args.dry_run:
            print(
                "Completed VCT events still missing matches: "
                + ", ".join(str(item) for item in missing)
            )
            print("Refusing to train CIR v0.3 until completed events are backfilled.")
            return 1

        kept_v02 = session.scalar(
            select(MetricVersion).where(
                MetricVersion.name == CIR_NAME,
                MetricVersion.version == CIR_V02_VERSION,
            )
        )
        v02_id = kept_v02.id if kept_v02 is not None else None
        vct_event_ids = [
            event.vlr_event_id
            for event in session.scalars(
                select(Event).where(
                    Event.circuit == CircuitName.VCT.value,
                    Event.season_year == 2026,
                )
            ).all()
        ]

        if not args.dry_run:
            elo = TeamRatingService(session).rebuild_team_ratings()
            print("elo_rebuild:")
            print(_format_elo(elo))
            print("")

        trainer = CirV02TrainingService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            bootstrap_iterations=args.bootstrap_iterations,
            persist_version=CIR_V03_VERSION,
            allow_production=False,
            events_used=vct_event_ids,
        )
        try:
            result = trainer.train(
                dry_run=args.dry_run,
                force_new_version=args.force_new_version,
            )
            if not args.dry_run:
                session.commit()
        except CirVersionExistsError as exc:
            print(str(exc))
            return 1

        still_v02 = session.scalar(
            select(MetricVersion).where(
                MetricVersion.name == CIR_NAME,
                MetricVersion.version == CIR_V02_VERSION,
            )
        )
        if v02_id is not None and (still_v02 is None or still_v02.id != v02_id):
            print("CIR v0.2 was modified; aborting.")
            return 1
        if not args.dry_run and result.status == MetricVersionStatus.PRODUCTION.value:
            print("CIR v0.3 was persisted as PRODUCTION; expected VALIDATED.")
            return 1

        print("cir_v03_training:")
        print(f"  version: {result.version}")
        print(f"  status: {result.status}")
        print(f"  metric_version_id: {result.metric_version_id}")
        print("  note: CIR v0.2-real-2026 was not overwritten")
        if args.json:
            print("")
            print(json.dumps(result.model_dump(), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
