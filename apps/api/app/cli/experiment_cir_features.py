from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.db import SessionLocal
from app.metrics.cir_feature_pruning_config import DEFAULT_PRUNING_SHRINKAGE_K
from app.services.cir_feature_pruning_service import CirFeaturePruningService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose and prune CIR candidate features without mutating CIR v0.1"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full experiment report as JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write the full report JSON to this path (separate from Context v2 outputs)",
    )
    parser.add_argument(
        "--shrinkage-k",
        type=float,
        default=DEFAULT_PRUNING_SHRINKAGE_K,
        help="Player shrinkage k for the main experimental comparison (default 50)",
    )
    parser.add_argument(
        "--allow-incomplete-maps",
        action="store_true",
        help="Include incomplete maps (tests / fixtures only)",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        service = CirFeaturePruningService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            shrinkage_k=args.shrinkage_k,
        )
        report = service.run()
        rec = report.recommendation
        print("cir_feature_pruning_experiment:")
        print(f"  preserved_metric_version: {CIR_REAL_EXPERIMENT_VERSION}")
        print(f"  selected_subset: {report.selected_subset}")
        print(f"  shrinkage_k: {report.shrinkage_k}")
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
        print("  residual_adr:")
        print(f"    interpretation: {report.residual_adr_diagnosis.interpretation}")
        print("  kast:")
        print(f"    conclusion: {report.kast_diagnosis.conclusion}")
        print("  apr:")
        print(f"    conclusion: {report.apr_diagnosis.conclusion}")
        print("  opening:")
        print(f"    conclusion: {report.opening_diagnosis.conclusion}")
        print("  dispositions:")
        for disposition in report.dispositions:
            print(f"    {disposition.feature}: {disposition.disposition} ({disposition.reason})")
        print("  cir_v0.2_candidate:")
        print(f"    combat: {rec.combat}")
        print(f"    damage: {rec.damage}")
        print(f"    team: {rec.team}")
        print(f"    opening: {rec.opening}")
        print(f"    clutch: {rec.clutch}")
        print(f"    context: {rec.context}")
        print(f"    shrinkage_k: {rec.shrinkage_k}")
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
