from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.db import SessionLocal
from app.metrics.cir_combat_factor_config import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    FROZEN_SHRINKAGE_K,
)
from app.services.cir_combat_factor_experiment_service import CirCombatFactorExperimentService
from app.services.scale_event_set import CIR_REAL_EXPERIMENT_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare CIR combat parameterizations without persisting CIR v0.2"
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
        report = CirCombatFactorExperimentService(
            session,
            require_complete_maps=not args.allow_incomplete_maps,
            shrinkage_k=args.shrinkage_k,
            bootstrap_iterations=args.bootstrap_iterations,
        ).run()
        rec = report.recommendation
        print("cir_combat_factor_experiment:")
        print(f"  preserved_metric_version: {CIR_REAL_EXPERIMENT_VERSION}")
        print(f"  selection: {rec.selection}")
        print(f"  readiness: {rec.readiness}")
        print(f"  winning_kind: {rec.winning_kind}")
        print(f"  kpr_ndpr_corr: {report.kpr_ndpr_train_correlation}")
        print(
            "  pca: "
            f"pc1={report.pca.explained_pc1} pc2={report.pca.explained_pc2} "
            f"kpr_loading={report.pca.kpr_loading_pc1} "
            f"ndpr_loading={report.pca.ndpr_loading_pc1}"
        )
        print(f"  pc2_discard: {report.pc2_diagnostic.discard_pc2}")
        print("  candidates:")
        for item in report.candidates:
            print(
                f"    {item.kind}: val_rmse={item.validation_metrics.rmse} "
                f"test_rmse={item.test_metrics.rmse} "
                f"gap={item.role_median_gap} "
                f"coef={item.combat_coefficient} dim={item.n_combat_dimensions}"
            )
        print(
            "  event_wins: "
            f"single={report.events_won_by_single_factor} "
            f"two={report.events_won_by_two_feature} "
            f"VLR={report.events_won_by_vlr} "
            f"KD={report.events_won_by_kd} ACS={report.events_won_by_acs}"
        )
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
