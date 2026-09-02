#!/usr/bin/env bash
# Check this laptop is ready to copy a CIR dump and deploy scripts to a server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
FAIL=0

ok() { echo "OK   $1"; }
warn() { echo "WARN $1"; }
bad() { echo "FAIL $1"; FAIL=1; }

if [[ -z "${DATABASE_URL:-}" && -f "$ENV_FILE" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
  export DATABASE_URL
fi

echo "== Deploy preflight =="

[[ -x deploy/dump-postgres.sh ]] || bad "dump-postgres.sh is not executable"
[[ -x deploy/restore-postgres.sh ]] || bad "restore-postgres.sh is not executable"
[[ -x deploy/smoke-check.sh ]] || bad "smoke-check.sh is not executable"
[[ -f deploy/env.production.example ]] || bad "missing deploy/env.production.example"
[[ -f deploy/README.md ]] || bad "missing deploy/README.md"
[[ -f docker-compose.yml ]] || bad "missing docker-compose.yml"

if command -v pg_dump >/dev/null 2>&1; then
  ok "pg_dump is installed"
else
  bad "pg_dump is missing (install PostgreSQL client tools)"
fi

if command -v psql >/dev/null 2>&1; then
  ok "psql is installed"
else
  bad "psql is missing"
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  ok "DATABASE_URL is set"
else
  bad "DATABASE_URL is not set (need repo .env)"
fi

if [[ -n "${DATABASE_URL:-}" ]] && command -v psql >/dev/null 2>&1; then
  STATUS="$(psql "$DATABASE_URL" -Atc \
    "SELECT status FROM metric_versions WHERE name = 'CIR' AND version = 'v0.2-real-2026';" \
    2>/dev/null || true)"
  COUNT="$(psql "$DATABASE_URL" -Atc \
    "SELECT COUNT(*) FROM player_metric_snapshots;" 2>/dev/null || true)"
  if [[ "$STATUS" == "PRODUCTION" ]]; then
    ok "CIR v0.2-real-2026 is PRODUCTION"
  else
    bad "CIR v0.2-real-2026 is not PRODUCTION (got '${STATUS:-missing}')"
  fi
  if [[ "${COUNT:-0}" -gt 0 ]]; then
    ok "player_metric_snapshots count=${COUNT}"
  else
    bad "player_metric_snapshots is empty"
  fi
fi

DUMP="$(ls -1t deploy/backups/*.dump 2>/dev/null | head -1 || true)"
if [[ -n "$DUMP" ]]; then
  ok "dump exists: $DUMP ($(du -h "$DUMP" | awk '{print $1}'))"
else
  warn "no dump yet — run ./deploy/dump-postgres.sh"
fi

if git check-ignore -q deploy/backups/dummy.dump 2>/dev/null \
  || git check-ignore -q "$DUMP" 2>/dev/null; then
  ok "database dumps are gitignored"
else
  warn "confirm deploy/backups/ is gitignored so dumps are not committed"
fi

if git status --porcelain -- deploy docker-compose.yml apps/api/app/main.py apps/api/app/config.py .gitignore README.md \
  | grep -q .; then
  warn "deploy-related files are not committed — git pull on the server will miss them"
  git status --porcelain -- deploy docker-compose.yml apps/api/app/main.py apps/api/app/config.py .gitignore README.md
else
  ok "deploy files are committed"
fi

echo
echo "== Next steps =="
if [[ -n "$DUMP" ]]; then
  echo "1. scp $DUMP user@YOUR_SERVER:~/"
else
  echo "1. ./deploy/dump-postgres.sh"
  echo "   scp deploy/backups/*.dump user@YOUR_SERVER:~/"
fi
echo "2. git push  (then git pull on the server)"
echo "3. On the server:"
echo "     cp deploy/env.production.example .env   # edit CHANGE_ME"
echo "     docker compose up -d db"
echo "     ./deploy/restore-postgres.sh ~/$(basename "${DUMP:-valorant_scout.dump}")"
echo "     docker compose up -d --build api web"
echo "     ./deploy/smoke-check.sh"
echo "4. Do not start vct-sync. Do not retrain CIR."

if [[ "$FAIL" -ne 0 ]]; then
  echo
  echo "PREFLIGHT_BLOCKED"
  exit 1
fi
echo
echo "PREFLIGHT_OK"
