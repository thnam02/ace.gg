from __future__ import annotations

import argparse
import sys

from app.db import SessionLocal
from app.services.dataset_audit_service import DatasetAuditService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit canonical PostgreSQL dataset")
    parser.parse_args(argv)

    with SessionLocal() as session:
        report = DatasetAuditService().audit(session)
        print(DatasetAuditService().format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
