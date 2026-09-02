from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.db import SessionLocal
from app.metrics.mir.mir_config import DEFAULT_MIR_SHRINKAGE_K
from app.services.mir_experiment_service import MirExperimentService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run MIR residualization experiments without mutating CIR"
    )
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write the full report JSON to this path",
    )
    parser.add_argument(
        "--shrinkage-k",
        type=float,
        default=DEFAULT_MIR_SHRINKAGE_K,
        help="Player shrinkage k (default 50)",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist MIR/v0.1-experimental-2026 only if evidence gates pass strongly",
    )
    parser.add_argument(
        "--allow-incomplete-maps",
        action="store_true",
        help="Include incomplete maps (tests / fixtures only)",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        report = MirExperimentService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            shrinkage_k=args.shrinkage_k,
            persist=args.persist,
        ).run()
        rec = report.recommendation
        print("mir_experiment:")
        print(f"  preserved_metric_version: {CIR_REAL_EXPERIMENT_VERSION}")
        print(f"  selected_subset: {report.selected_subset}")
        print(f"  decision: {rec.decision}")
        print(f"  readiness: {rec.readiness}")
        print(f"  economy_enabled: {report.economy_enabled}")
        print("  subset_results:")
        for subset in report.subset_results:
            print(
                f"    {subset.name}: n={subset.number_of_features} "
                f"val_rmse={subset.validation_metrics.rmse} "
                f"test_rmse={subset.test_metrics.rmse} "
                f"val_r2={subset.validation_metrics.r2} "
                f"val_spearman={subset.validation_metrics.spearman} "
                f"gap={subset.role_bias_metrics.max_role_median_gap}"
            )
        print("  raw_vs_unique:")
        for comparison in report.raw_vs_unique:
            print(f"    {comparison.signal}: {comparison.conclusion}")
        print("  components:")
        for evidence in report.component_evidence:
            print(f"    {evidence.component}: {evidence.disposition} ({evidence.conclusion})")
        print("  mir_v0.1_candidate:")
        print(f"    combat: {rec.combat}")
        print(f"    support: {rec.support}")
        print(f"    opening: {rec.opening}")
        print(f"    economy: {rec.economy}")
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
