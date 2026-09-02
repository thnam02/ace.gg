from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal
from app.metrics.cir_v01 import CIR_V01_VERSION
from app.schemas.team_rating import TeamRatingRebuildSummary
from app.services.cir_training_service import CIRTrainingService
from app.services.cir_validation_service import CIRValidationService
from app.services.dataset_audit_service import DatasetAuditService
from app.services.dataset_training_readiness import DatasetTrainingReadinessService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION, SCALE_EVENT_IDS
from app.services.team_rating_service import TeamRatingService


def _format_elo(summary: TeamRatingRebuildSummary) -> str:
    highest = summary.highest_rated_teams
    lines = [
        f"matches_processed: {summary.matches_processed}",
        f"matches_skipped: {summary.matches_skipped}",
        f"teams_rated: {summary.teams_rated}",
        f"rating_min: {summary.rating_min}",
        f"rating_p25: {summary.rating_p25}",
        f"rating_median: {summary.rating_median}",
        f"rating_p75: {summary.rating_p75}",
        f"rating_max: {summary.rating_max}",
        "highest_rated_teams:",
    ]
    for item in highest[:10]:
        lines.append(f"  {item.team_name}: {item.rating}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Historical CIR v0.1 trainer. Production CIR is v0.2 via app.cli.train_cir_v02."
    )
    parser.add_argument(
        "--persist-version",
        default=CIR_REAL_EXPERIMENT_VERSION,
        help=f"MetricVersion.version to write (default {CIR_REAL_EXPERIMENT_VERSION})",
    )
    parser.add_argument(
        "--skip-gates",
        action="store_true",
        help="Train even if dataset training gates fail (not recommended)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run CIR validation after training",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the training/validation payloads as JSON",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        audit = DatasetAuditService().audit(session)
        readiness = DatasetTrainingReadinessService().assess(audit)
        print(DatasetTrainingReadinessService().format_report(readiness))
        print("")
        if not readiness.can_train and not args.skip_gates:
            print("Stopped before CIR training because dataset gates failed.")
            return 1

        elo = TeamRatingService(session).rebuild_team_ratings()
        print("elo_rebuild:")
        print(_format_elo(elo))
        print("")

        trainer = CIRTrainingService(
            session,
            persist_version=args.persist_version,
            events_used=list(SCALE_EVENT_IDS),
        )
        result = trainer.train_cir_v01()
        session.commit()
        print("cir_training:")
        print(f"  version: {result.version}")
        print(f"  ridge_alpha: {result.ridge_alpha}")
        print(f"  shrinkage_k: {result.shrinkage_k}")
        print(f"  clutch_feature_enabled: {result.clutch_feature_enabled}")
        print(f"  maps_used_for_cir: {result.maps_used_for_cir}")
        print(f"  maps_excluded_unknown_agent: {result.maps_excluded_unknown_agent}")
        print("  coefficients:")
        for name, value in result.coefficients.items():
            print(f"    {name}: {value}")
        print(
            "  evaluation: "
            f"val_rmse={result.evaluation.validation_rmse} "
            f"test_rmse={result.evaluation.test_rmse} "
            f"val_r2={result.evaluation.validation_r2} "
            f"test_r2={result.evaluation.test_r2}"
        )
        if args.persist_version != CIR_V01_VERSION:
            print(f"  preserved_existing_version: {CIR_V01_VERSION}")

        validation_payload = None
        if args.validate:
            validation = CIRValidationService(session, training_service=trainer).validate_cir_v01()
            validation_payload = validation.model_dump()
            print("")
            print("cir_validation:")
            print(f"  decision: {validation.v02_recommendation.decision}")
            for metric in validation.baseline_comparison.metrics:
                print(
                    f"  {metric.name} {metric.split}: rmse={metric.rmse} "
                    f"mae={metric.mae} r2={metric.r2} spearman={metric.spearman}"
                )
            print("  ablation:")
            for row in validation.ablation_results.results:
                print(
                    f"    {row.variant}: val_rmse={row.validation_rmse} "
                    f"test_rmse={row.test_rmse} impact={row.impact}"
                )
            print(f"  recommended_k: {validation.shrinkage_analysis.recommended_k}")
            print("  v0.2 reasons:")
            for reason in validation.v02_recommendation.reasons:
                print(f"    - {reason}")

        if args.json:
            payload = {
                "training": result.model_dump(),
                "elo": elo.model_dump(),
                "readiness": {
                    "status": readiness.status,
                    "can_train": readiness.can_train,
                    "blockers": readiness.blockers,
                    "warnings": readiness.warnings,
                },
                "validation": validation_payload,
            }
            print("")
            print(json.dumps(payload, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
