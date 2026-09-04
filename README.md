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

Postgres is bound to `127.0.0.1` only. Daily VCT ingest is opt-in (`--profile sync`) and needs a reachable VLRGGAPI — leave it off until that exists.

## Production

Live shape is **Vercel (web) + Railway (API + Postgres)**. How to dump, restore, set env, and smoke-check: [deploy/README.md](deploy/README.md).
