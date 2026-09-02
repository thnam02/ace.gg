#!/usr/bin/env bash
# Smoke-check a deployed ACE.gg API + web.
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3000}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

echo "Checking $API_URL/health"
HEALTH="$(curl -fsS "$API_URL/health")"
python3 - "$HEALTH" <<'PY' || fail "API health check failed"
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("database") != "connected" or payload.get("status") != "ok":
    raise SystemExit(1)
print("health ok")
PY

echo "Checking $API_URL/metrics/cir"
CIR="$(curl -fsS "$API_URL/metrics/cir")"
python3 - "$CIR" <<'PY' || fail "CIR metadata is not production v0.2"
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("version") != "v0.2-real-2026" or payload.get("status") != "PRODUCTION":
    raise SystemExit(f"got version={payload.get('version')} status={payload.get('status')}")
print(f"CIR {payload['version']} {payload['status']}")
PY

echo "Checking $API_URL/rankings/cir?limit=1"
RANK="$(curl -fsS "$API_URL/rankings/cir?limit=1")"
python3 - "$RANK" <<'PY' || fail "rankings payload is empty — dump was not restored"
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("total", 0) < 1 or not payload.get("players"):
    raise SystemExit("empty rankings")
top = payload["players"][0]
print(f"top player: {top['handle']} CIR={top['cir']}")
PY

echo "Checking $WEB_URL/"
HOME_HTML="$(curl -fsS "$WEB_URL/")"
echo "$HOME_HTML" | grep -q "ACE.gg" || fail "homepage missing ACE.gg"
echo "$HOME_HTML" | grep -q "beyond the scoreboard" || fail "homepage missing hero copy"
if echo "$HOME_HTML" | grep -q "Include provisional"; then
  fail "homepage still renders the full rankings table"
fi

echo "Checking $WEB_URL/rankings"
RANK_HTML="$(curl -fsS "$WEB_URL/rankings")"
echo "$RANK_HTML" | grep -q "CIR rankings" || fail "rankings page missing heading"

DOCS_CODE="$(curl -sS -o /dev/null -w "%{http_code}" "$API_URL/docs" || true)"
if [[ "$DOCS_CODE" == "200" ]]; then
  echo "WARN: /docs is reachable. Set DOCS_ENABLED=false in production."
fi

echo "DEPLOY_SMOKE_OK"
