# ACE.gg production

Restore CIR **v0.2-real-2026 PRODUCTION**. Do **not** retrain CIR. Do **not** `alembic upgrade head` on an empty volume.

Current live shape:

```text
browser  →  Vercel web
              ├─ SSR (rankings, player pages) → Railway API
              └─ /scout-api/* (search, compare) → Railway API
Railway API  →  Railway Postgres (restored dump)
```

Production hosts today:

- Web: `https://ace-gg-web-gray.vercel.app` (Vercel builds `main`)
- API: `https://acegg-production.up.railway.app`

Vercel production tracks **`main`**. Merge `nam/dev` before a production web deploy.

## Rate limits

In-memory sliding window, 60 seconds. `/health` and `/ops/vct-sync` are exempt.

| Path | Cap (per minute) |
|---|---|
| Railway API, per connecting IP | 600 general, 60 `/players/compare*` |
| Vercel `/scout-api`, per visitor IP | 90 general, 20 compare |

Over the cap returns **429** and `Retry-After`. This is per process, not Redis. It stops bursts and dumb scrapers; it is not a global WAF.

Set on **Railway API**:

```text
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=600
RATE_LIMIT_COMPARE_PER_MINUTE=60
```

Set on **Vercel** (runtime, `/scout-api` only). Optional; defaults are 90 / 20:

```text
RATE_LIMIT_PER_MINUTE=90
RATE_LIMIT_COMPARE_PER_MINUTE=20
```

## Railway API env

| Variable | Value |
|---|---|
| `DATABASE_URL` | Railway Postgres plugin (`postgres.railway.internal`). Do not use laptop `localhost`. |
| `CORS_ORIGINS` | Exact Vercel origin, e.g. `https://ace-gg-web-gray.vercel.app` |
| `DOCS_ENABLED` | `false` |
| `API_HOST` | `0.0.0.0` |
| `API_PORT` | `8000` (container port; not part of the hostname) |
| `RATE_LIMIT_ENABLED` | `true` |
| `VLRGGAPI_BASE_URL` | Reachable [vlrggapi](https://github.com/axsddlr/vlrggapi) origin (Railway private URL is fine). Required for daily ingest. |
| `VCT_SYNC_TOKEN` | Long random token for `GET`/`POST /ops/vct-sync`. Empty = endpoint 404. |
| `VCT_SYNC_ENABLED` | `true` to run ingest inside the API process at `VCT_SYNC_CRON` (default 03:00 UTC). `false` if you only use the GitHub Action. |
| `VCT_SYNC_SEASON_YEAR` | `2026` |
| `VLR_CIRCUIT_URL` | `https://www.vlr.gg/vct` (VCT circuit only, not Challengers) |

Do not put `NEXT_PUBLIC_*` or local `POSTGRES_*` on the API service.

Daily ingest **refreshes** frozen CIR v0.2 snapshots (season + event). It does **not** retrain. `/ops/vct-sync` is exempt from the IP rate limit so GitHub Actions can trigger it; keep the token secret.

GitHub repo secrets for `.github/workflows/daily-vct-sync.yml`:

```text
ACEGG_API_URL=https://acegg-production.up.railway.app
VCT_SYNC_TOKEN=<same value as Railway>
```

CORS also allows `https://*.vercel.app` so preview deployments can call the API. Compare in production still goes through `/scout-api` (same-origin), so CORS is backup for direct API calls.

## Vercel web env

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://acegg-production.up.railway.app` |
| `API_URL` | Same URL. Do **not** leave this empty — empty string wins over the public URL. |

`NEXT_PUBLIC_*` is baked at **build**. After changing it, Redeploy.

Root directory: `apps/web`. Do not set `output: "standalone"` on Vercel (`next.config.ts` skips it when `VERCEL` is set).

## Database dump / restore

Laptop check:

```bash
./deploy/preflight.sh
```

Dump the source DB that already has CIR:

```bash
./deploy/dump-postgres.sh
```

Writes `deploy/backups/` (gitignored). Confirm before dumping:

```sql
SELECT name, version, status
FROM metric_versions
WHERE name = 'CIR'
ORDER BY version;
```

Expected: `CIR | v0.2-real-2026 | PRODUCTION`.

Restore into Railway using the **public TCP proxy** host (not `postgres.railway.internal` — that only works inside Railway):

```bash
./deploy/restore-postgres.sh /path/to/valorant_scout.dump
```

`DATABASE_URL` for that command must be the proxy URL (`*.proxy.rlwy.net`). After restore, disable the TCP proxy if you do not need laptop access. Rotate the Postgres password if it was ever pasted into chat.

## Smoke check

Against production:

```bash
API_URL=https://acegg-production.up.railway.app \
WEB_URL=https://ace-gg-web-gray.vercel.app \
  ./deploy/smoke-check.sh
```

Expect:

- `/health` — database connected
- `/metrics/cir` — `v0.2-real-2026` `PRODUCTION`
- `/rankings/cir?limit=1` — players (Neon 99.8 as of the restored dump)
- `/` — ACE.gg homepage, not the full rankings table
- `/rankings` — ranking table
- `/docs` — not 200
- Compare in the browser — Network shows `/scout-api/players/compare` **200**

## Docker Compose (VPS alternative)

Same dump, different host. Copy `deploy/env.production.example` to `.env` next to `docker-compose.yml`.

| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_API_URL` | Public API URL baked into the web **image** |
| `CORS_ORIGINS` | Public website origin |
| `POSTGRES_PASSWORD` | Must match the password inside `DATABASE_URL` |
| `DOCS_ENABLED` | `false` |
| `RATE_LIMIT_PER_MINUTE` | API cap per IP (compare uses `RATE_LIMIT_COMPARE_PER_MINUTE`) |
| `VLRGGAPI_BASE_URL` | Self-hosted vlrggapi origin |
| `VCT_SYNC_TOKEN` | Protects `/ops/vct-sync` |
| `VCT_SYNC_ENABLED` | In-process daily cron; optional if using GitHub Action |

`docker-compose.yml` sets `API_URL=http://api:8000` for server-side fetches. Do not point that at localhost. Postgres publishes `127.0.0.1:5432` only.

```bash
docker compose up -d db
./deploy/restore-postgres.sh /path/to/valorant_scout.dump
docker compose up -d --build api web
API_URL=http://127.0.0.1:8000 WEB_URL=http://127.0.0.1:3000 ./deploy/smoke-check.sh
```

Do not start ingest until vlrggapi is reachable. Either:

```bash
docker compose --profile sync up -d vct-sync
```

or set `VCT_SYNC_ENABLED=true` on `api` (and `VLRGGAPI_BASE_URL` / `VCT_SYNC_TOKEN`).

## Do not

- Run `python -m app.cli.train_cir_v02` in production
- Alembic-upgrade an empty database instead of restoring the dump
- Commit `deploy/backups/`, `*.dump`, or a filled `.env`
- Use `.env.example` defaults (`valorant:valorant`) on a public host
