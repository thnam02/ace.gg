from __future__ import annotations

import argparse
import sys

from app.db import SessionLocal
from app.services.cir_readiness_service import CirReadinessService
from app.services.dataset_audit_service import DatasetAuditService
from app.services.dataset_integrity_service import DatasetIntegrityService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit canonical PostgreSQL dataset")
    parser.parse_args(argv)

    with SessionLocal() as session:
        audit = DatasetAuditService().audit(session)
        integrity = DatasetIntegrityService().check(session)
        readiness = CirReadinessService().assess(audit)
        print(DatasetAuditService().format_report(audit))
        print("")
        print(DatasetIntegrityService().format_report(integrity))
        print("")
        print(CirReadinessService().format_report(readiness))
    return 0


if __name__ == "__main__":
    sys.exit(main())
