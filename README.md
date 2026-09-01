# VALORANT Scout

Player stats and comparison app. This scaffold uses mock player data only. Riot API integration and the custom rating metric are not implemented yet.

## Stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Python
- Database: PostgreSQL
- Local orchestration: Docker Compose

## Project layout

```text
apps/
  web/                 Next.js UI
  api/                 FastAPI service
    app/
      api/             HTTP routes
      models/          SQLAlchemy models
      schemas/         Pydantic schemas
      services/        Player stats and comparison
      providers/       Data sources (mock for now)
      metrics/         Custom metric engine placeholder
packages/
  shared/              Shared TypeScript API types
```

## Quick start (local, no Docker)

Copy environment defaults:

```bash
cp .env.example .env
```

### Backend

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Health check: [http://localhost:8000/health](http://localhost:8000/health)

Without PostgreSQL running, the API still serves mock players and `/health` reports `database: disconnected`.

### Database migrations

From `apps/api`, with `DATABASE_URL` pointing at PostgreSQL:

```bash
alembic upgrade head
alembic downgrade -1
alembic current
```

### Frontend

From the repo root:

```bash
npm install
npm run dev:web
```

## Current modules

| Module | Status |
| --- | --- |
| Player stats | Mock profiles via `/players` and `/players/{id}` |
| Player comparison | Placeholder via `/players/compare?ids=tenz&ids=aspas` |
| Data provider | `MockPlayerDataProvider` only |
| Custom metric engine | Placeholder; rating is not implemented |
| Riot API | Not integrated |
