from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal
from app.metrics.cir.config import CIR_V02_VERSION
from app.schemas.team_rating import TeamRatingRebuildSummary
from app.services.cir_v02_training_service import CirV02TrainingService, CirVersionExistsError
from app.services.dataset_audit_service import DatasetAuditService
from app.services.dataset_training_readiness import DatasetTrainingReadinessService
from app.services.team_rating_service import TeamRatingService


def _format_elo(summary: TeamRatingRebuildSummary) -> str:
    lines = [
        f"matches_processed: {summary.matches_processed}",
        f"teams_rated: {summary.teams_rated}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Train and persist frozen CIR v0.2-real-2026. "
            "Does not overwrite CIR v0.1-real-2026. Scoring != retraining."
        )
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force-new-version",
        action="store_true",
        help="Replace only CIR v0.2-real-2026 if it already exists",
    )
    parser.add_argument("--bootstrap-iterations", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-incomplete-maps",
        action="store_true",
        help="Tests/fixtures only",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        audit = DatasetAuditService().audit(session)
        readiness = DatasetTrainingReadinessService().assess(audit)
        print(DatasetTrainingReadinessService().format_report(readiness))
        print("")
        if not readiness.can_train and not args.dry_run:
            print("Stopped before CIR v0.2 training because dataset gates failed.")
            return 1

        if not args.dry_run:
            elo = TeamRatingService(session).rebuild_team_ratings()
            print("elo_rebuild:")
            print(_format_elo(elo))
            print("")

        trainer = CirV02TrainingService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            bootstrap_iterations=args.bootstrap_iterations,
            persist_version=CIR_V02_VERSION,
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

        print("cir_v02_training:")
        print(f"  version: {result.version}")
        print(f"  status: {result.status}")
        print(f"  metric_version_id: {result.metric_version_id}")
        print(f"  dry_run: {result.dry_run}")
        print(f"  maps_used: {result.maps_used}")
        print(f"  player_snapshots: {result.player_snapshots}")
        print(f"  reference_size: {result.reference_size}")
        print(f"  reference_mean: {result.reference_mean}")
        print(f"  mu_kpr: {result.mu_kpr} sigma_kpr: {result.sigma_kpr}")
        print(
            "  mu_negative_dpr: "
            f"{result.mu_negative_dpr} sigma_negative_dpr: {result.sigma_negative_dpr}"
        )
        print(
            f"  val_rmse: {result.val_rmse} test_rmse: {result.test_rmse} "
            f"role_gap: {result.role_gap} bootstrap_sign_flips: {result.bootstrap_sign_flips}"
        )
        print(f"  sample_counts: {result.sample_counts}")
        print(f"  gates.passed: {result.gates.passed}")
        for failure in result.gates.failures + result.gates.regression_failures:
            print(f"  gate_failure: {failure}")
        print("  top_established:")
        for row in result.top_established:
            print(f"    {row.get('handle')}: CIR {row.get('cir')} ({row.get('rounds')} rounds)")

        if args.json:
            print("")
            print(json.dumps(result.model_dump(), default=str))

        if not result.gates.passed and not args.dry_run:
            print("CIR v0.2 was persisted as VALIDATED, not PRODUCTION.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
