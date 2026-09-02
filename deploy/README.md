# ACE.gg first deploy

Restore the existing CIR v0.2 database. Do **not** retrain CIR. Do **not** start from an empty Postgres volume.

Laptop check before you copy anything:

```bash
./deploy/preflight.sh
```

## 1. Dump the laptop database

On this machine (where rankings currently work):

```bash
./deploy/dump-postgres.sh
```

This writes a custom `pg_dump` under `deploy/backups/`. That folder is gitignored. Copy the `.dump` file to the server with `scp`.

Confirm CIR v0.2 is in the live source DB before dumping:

```sql
SELECT name, version, status
FROM metric_versions
WHERE name = 'CIR'
ORDER BY version;
```

Expected production row: `CIR | v0.2-real-2026 | PRODUCTION`.

## 2. Production env on the server

```bash
cp deploy/env.production.example .env
```

Edit `.env`:

| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL the **browser** uses for search and compare typeahead |
| `CORS_ORIGINS` | Public website origin (the Next.js host) |
| `POSTGRES_PASSWORD` | Strong password, also used inside `DATABASE_URL` |
| `DOCS_ENABLED` | Keep `false` on a public API |

`NEXT_PUBLIC_API_URL` is baked into the web image at **build** time. If you change it, rebuild web:

```bash
docker compose build --build-arg NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" web
```

`docker-compose.yml` already sets the web container `API_URL=http://api:8000` for server-side fetches. Do not point that at localhost.

## 3. Restore, then start API + web

On the server, from the repo root, with `.env` filled in and the dump file present:

```bash
docker compose up -d db
./deploy/restore-postgres.sh /path/to/valorant_scout.dump
docker compose up -d --build api web
```

Do not start `vct-sync` yet. Daily ingest needs a reachable VLRGGAPI. Enable later with:

```bash
docker compose --profile sync up -d vct-sync
```

Postgres is bound to `127.0.0.1` only. Do not publish `5432` on the public interface.

## 4. Smoke check

```bash
API_URL=http://127.0.0.1:8000 WEB_URL=http://127.0.0.1:3000 ./deploy/smoke-check.sh
```

From a laptop against a public host, point those URLs at the public origins.

Expect:

- `/health` database connected
- `/metrics/cir` version `v0.2-real-2026`, status `PRODUCTION`
- `/rankings/cir?limit=1` returns players
- `/` is the ACE.gg homepage, not the rankings table
- `/rankings` still has the ranking table

## 5. Do not

- Run `python -m app.cli.train_cir_v02` on the server
- Run `alembic upgrade head` on an empty database instead of restoring the dump
- Use `.env.example` defaults (`valorant:valorant`, localhost CORS, localhost API URL)
- Commit `deploy/backups/` or a filled `.env`

## First-deploy shape

```text
browser  →  web :3000
browser  →  api :8000   (search / compare typeahead; CORS must allow the web origin)
web      →  api:8000    (server-side ranking and player pages)
api      →  db          (restored CIR snapshots)
```
