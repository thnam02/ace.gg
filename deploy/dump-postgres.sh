#!/usr/bin/env bash
# Dump the local CIR database. Does not retrain or modify MetricVersion rows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
OUT=""

usage() {
  cat <<'EOF'
Dump the current Postgres database (CIR snapshots included).

Usage:
  ./deploy/dump-postgres.sh
  ./deploy/dump-postgres.sh --out deploy/backups/valorant_scout.dump
  DATABASE_URL=postgresql://user:pass@host:5432/valorant_scout ./deploy/dump-postgres.sh

Reads DATABASE_URL from the repo .env when the variable is not already set.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --out)
      OUT="${2:?--out requires a path}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${DATABASE_URL:-}" && -f "$ENV_FILE" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
  export DATABASE_URL
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set and $ENV_FILE has no DATABASE_URL." >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump is required (install PostgreSQL client tools)." >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ROOT/deploy/backups"
OUT="${OUT:-$ROOT/deploy/backups/valorant_scout-${STAMP}.dump}"
mkdir -p "$(dirname "$OUT")"

echo "Dumping database to $OUT"
pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --compress=9 \
  --dbname="$DATABASE_URL" \
  --file="$OUT"

echo "Listing dump table of contents (expect CIR v0.2-real-2026 among metric_versions):"
pg_restore -l "$OUT" | grep -E 'TABLE DATA.*(metric_versions|player_metric_snapshots)' || true
ls -lh "$OUT"
echo "Done. Copy this file to the server. Do not commit it."
