from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal
from app.metrics.cir.config import CIR_V02_VERSION
from app.schemas.cir_v02 import CirSnapshotRefreshResult, CirTrainingGateResult
from app.services.cir_snapshot_service import CirSnapshotService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh PlayerMetricSnapshots using frozen CIR v0.2 parameters. "
            "Does not refit expectations, standardization, or the reference distribution."
        )
    )
    parser.add_argument("--version", default=CIR_V02_VERSION)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-incomplete-maps", action="store_true")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        service = CirSnapshotService(
            session, require_complete_maps=not args.allow_incomplete_maps
        )
        try:
            frozen, players, failures = service.refresh(version=args.version)
            session.commit()
        except ValueError as exc:
            print(str(exc))
            return 1

        counts: dict[str, int] = {}
        for player in players:
            counts[player.sample_status] = counts.get(player.sample_status, 0) + 1
        result = CirSnapshotRefreshResult(
            metric_version_id=str(frozen.metric_version.id),
            version=frozen.metric_version.version,
            player_snapshots=len(players),
            sample_counts=counts,
            gates=CirTrainingGateResult(passed=not failures, failures=failures),
        )
        print("cir_snapshot_refresh:")
        print(f"  version: {result.version}")
        print(f"  metric_version_id: {result.metric_version_id}")
        print(f"  player_snapshots: {result.player_snapshots}")
        print(f"  sample_counts: {result.sample_counts}")
        print("  note: MetricVersion parameters were not refit")
        if args.json:
            print("")
            print(json.dumps(result.model_dump(), default=str))
        if failures:
            for failure in failures:
                print(f"  gate_failure: {failure}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
