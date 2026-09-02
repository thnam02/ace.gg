#!/bin/sh
set -eu
CRON="${VCT_SYNC_CRON:-0 3 * * *}"
CMD="python -m app.cli.sync_vct_2026"
if [ -n "${VCT_SYNC_RAW_CACHE_DIR:-}" ]; then
  CMD="$CMD --raw-cache-dir $VCT_SYNC_RAW_CACHE_DIR"
fi
echo "$CRON $CMD" > /tmp/vct-sync.cron
exec /usr/local/bin/supercronic /tmp/vct-sync.cron
