from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.db import SessionLocal
from app.metrics.cir_final_validation_config import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    FROZEN_SHRINKAGE_K,
)
from app.services.cir_final_validation_service import CirFinalValidationService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Final robustness validation for the combat-only CIR candidate"
    )
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    parser.add_argument("--output", type=str, default=None, help="Write the full report JSON")
    parser.add_argument("--shrinkage-k", type=float, default=FROZEN_SHRINKAGE_K)
    parser.add_argument("--bootstrap-iterations", type=int, default=DEFAULT_BOOTSTRAP_ITERATIONS)
    parser.add_argument(
        "--allow-incomplete-maps",
        action="store_true",
        help="Include incomplete maps (tests / fixtures only)",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        report = CirFinalValidationService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            shrinkage_k=args.shrinkage_k,
            bootstrap_iterations=args.bootstrap_iterations,
        ).run()
        rec = report.recommendation
        print("cir_final_validation:")
        print(f"  preserved_metric_version: {CIR_REAL_EXPERIMENT_VERSION}")
        print(f"  readiness: {rec.readiness}")
        print(f"  selected_features: {report.frozen_features}")
        print(
            f"  primary: val_rmse={report.primary.validation_metrics.rmse} "
            f"test_rmse={report.primary.test_metrics.rmse} "
            f"gap={report.primary.role_median_gap}"
        )
        print(f"  tier_generalization: {report.tier_generalization}")
        print(
            f"  event_wins: CIR={report.events_won_by_cir} "
            f"KD={report.events_won_by_kd} ACS={report.events_won_by_acs} "
            f"VLR={report.events_won_by_vlr}"
        )
        print(f"  redundancy: {report.combat_redundancy.conclusion}")
        print(f"  ranking_floor: >={rec.ranking.minimum_rounds} rounds")
        print("  failures:")
        for item in report.failure_audit.failures:
            print(f"    - {item}")
        if not report.failure_audit.failures:
            print("    (none)")
        payload = json.dumps(report.model_dump(), default=str)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload + "\n")
            print(f"  wrote: {path}")
        if args.json:
            print("")
            print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
