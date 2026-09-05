# ACE.gg

VALORANT player analytics: CIR rankings, player dossiers, and side-by-side compare.

Public site is **ACE.gg**. CIR **v0.2-real-2026** is frozen **PRODUCTION**. Do not retrain CIR. Do not replace a live database with an empty Alembic schema.

## Stack

- API: FastAPI, PostgreSQL (CIR snapshots and map stats)
- Web: Next.js on Vercel
- Local / VPS: Docker Compose

## Layout

```text
apps/
  api/     FastAPI — rankings, players, compare
  web/     Next.js — homepage, /rankings, /compare, /players/[id]
deploy/    Dump/restore scripts and production env example
```

## Local

```bash
cp .env.example .env
```

Postgres must already contain the CIR dump. Rankings will be empty if you only run `alembic upgrade head`.

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/web
cp .env.example .env.local   # API_URL and NEXT_PUBLIC_API_URL → http://localhost:8000
npm install
npm run dev
```

- Web: http://localhost:3000
- API: http://localhost:8000
- Docs: http://localhost:8000/docs (keep `DOCS_ENABLED=false` in production)

```bash
cd apps/web && npm test && npm run typecheck
cd apps/api && python3 -m pytest
```

## Docker Compose

```bash
docker compose up --build
```

Postgres is bound to `127.0.0.1` only.

Daily VCT ingest scrapes new maps, then **refreshes frozen CIR snapshots** (season + event). It does **not** retrain CIR. It needs a reachable [vlrggapi](https://github.com/axsddlr/vlrggapi) (`/v2/match/details`, `/v2/event/{id}`).

- Local compose worker: `docker compose --profile sync up -d vct-sync` after `VLRGGAPI_BASE_URL` is set
- API in-process cron: `VCT_SYNC_ENABLED=true` (default `VCT_SYNC_CRON=0 3 * * *` UTC)
- GitHub Action: `POST /ops/vct-sync` with `X-Sync-Token` (repo secrets `ACEGG_API_URL`, `VCT_SYNC_TOKEN`)

Leave `VCT_SYNC_ENABLED=false` and `VCT_SYNC_TOKEN` empty until vlrggapi exists. An empty token hides `/ops/vct-sync` (404).

## Production

Live shape is **Vercel (web) + Railway (API + Postgres)**. How to dump, restore, set env, and smoke-check: [deploy/README.md](deploy/README.md).
