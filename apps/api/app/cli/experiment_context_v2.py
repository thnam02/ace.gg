from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal
from app.metrics.context_v2_config import default_context_experiment_matrix
from app.services.context_v2_experiment_service import ContextV2ExperimentService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Context Adjustment v2 experiments without mutating CIR v0.1"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full experiment report as JSON",
    )
    parser.add_argument(
        "--allow-incomplete-maps",
        action="store_true",
        help="Include incomplete maps (tests / fixtures only)",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        service = ContextV2ExperimentService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            matrix=default_context_experiment_matrix(),
        )
        report = service.run()
        rec = report.recommendations
        print("context_v2_experiment:")
        print(f"  preserved_metric_version: {CIR_REAL_EXPERIMENT_VERSION}")
        print(f"  best_validation_configuration: {report.best_validation_configuration}")
        print(f"  decision: {rec.decision}")
        print(f"  selected_lambda: {rec.selected_lambda}")
        print(f"  selected_tau: {rec.selected_tau}")
        print(f"  selected_shrinkage_k: {rec.selected_shrinkage_k}")
        print("  experiments:")
        for item in report.experiments:
            print(
                f"    {item.name}: val_rmse={item.validation_metrics.rmse} "
                f"test_rmse={item.test_metrics.rmse} "
                f"val_r2={item.validation_metrics.r2} "
                f"gap={item.role_bias_metrics.max_role_median_gap}"
            )
        print("  controller_diagnosis:")
        for line in report.controller_diagnosis.evidence:
            print(f"    - {line}")
        print("  reasons:")
        for reason in rec.reasons:
            print(f"    - {reason}")
        if args.json:
            print("")
            print(json.dumps(report.model_dump(), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
