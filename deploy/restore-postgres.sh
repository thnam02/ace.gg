#!/usr/bin/env bash
# Restore a CIR database dump into the compose Postgres service.
# Does not run CIR training.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DUMP=""
COMPOSE=1
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

usage() {
  cat <<'EOF'
Restore a pg_dump custom file into Docker Compose Postgres.

Usage:
  ./deploy/restore-postgres.sh deploy/backups/valorant_scout-YYYYMMDD.dump

The compose stack must be able to start `db`. This script:
  1. starts only Postgres
  2. waits until it is healthy
  3. restores the dump with --clean --if-exists
  4. checks that CIR v0.2-real-2026 is PRODUCTION

Do not run alembic against an empty database instead of this restore.
Do not retrain CIR after restore.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --no-compose)
      COMPOSE=0
      shift
      ;;
    *)
      if [[ -n "$DUMP" ]]; then
        echo "Unexpected extra argument: $1" >&2
        exit 1
      fi
      DUMP="$1"
      shift
      ;;
  esac
done

if [[ -z "$DUMP" ]]; then
  usage >&2
  exit 1
fi
if [[ ! -f "$DUMP" ]]; then
  echo "Dump file not found: $DUMP" >&2
  exit 1
fi

if [[ "$COMPOSE" -eq 0 ]]; then
  if [[ -z "${DATABASE_URL:-}" && -f "$ENV_FILE" ]]; then
    DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
    export DATABASE_URL
  fi
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required with --no-compose." >&2
    exit 1
  fi
  echo "Restoring $DUMP into DATABASE_URL host"
  pg_restore --clean --if-exists --no-owner --no-acl --dbname="$DATABASE_URL" "$DUMP"
  exit 0
fi

load_env() {
  local key="$1" default="${2:-}"
  local value=""
  if [[ -f "$ENV_FILE" ]]; then
    value="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
  fi
  printf '%s' "${value:-$default}"
}

POSTGRES_USER="$(load_env POSTGRES_USER valorant)"
POSTGRES_DB="$(load_env POSTGRES_DB valorant_scout)"

echo "Starting Postgres (db only; vct-sync stays off)"
docker compose up -d db

echo "Waiting for Postgres to become healthy"
for _ in $(seq 1 60); do
  if docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
  echo "Postgres did not become ready." >&2
  exit 1
fi

REMOTE="/tmp/valorant_scout.restore.dump"
echo "Copying dump into the db container"
docker compose cp "$DUMP" "db:${REMOTE}"

echo "Restoring (warnings about missing objects on an empty database are normal)"
set +e
docker compose exec -T db pg_restore \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  "$REMOTE"
RESTORE_STATUS=$?
set -e
if [[ "$RESTORE_STATUS" -gt 1 ]]; then
  echo "pg_restore failed with status $RESTORE_STATUS" >&2
  exit "$RESTORE_STATUS"
fi

echo "Verifying frozen CIR production row"
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT name, version, status FROM metric_versions WHERE name = 'CIR' ORDER BY version;"

STATUS="$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT status FROM metric_versions WHERE name = 'CIR' AND version = 'v0.2-real-2026';")"
if [[ "$STATUS" != "PRODUCTION" ]]; then
  echo "CIR v0.2-real-2026 is not PRODUCTION after restore (got: '${STATUS}')." >&2
  echo "Do not retrain. Check that you restored the laptop dump, not an empty volume." >&2
  exit 1
fi

echo "Restore OK. CIR v0.2-real-2026 is PRODUCTION."
echo "Next: docker compose up -d --build api web"
echo "Do not start vct-sync until VLRGGAPI is available."
