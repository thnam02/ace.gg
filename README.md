# VALORANT Scout

Player stats and comparison console: FastAPI backend plus a dense Next.js dashboard.

## Stack

- Backend: FastAPI, Python, PostgreSQL
- Frontend: Next.js, Tailwind CSS
- Local orchestration: Docker Compose

## Project layout

```text
apps/
  api/                 FastAPI service
    app/
      api/             HTTP routes
      models/          SQLAlchemy models
      schemas/         Pydantic schemas
      services/        Player stats, comparison, and match ingestion
      providers/       Data sources
      parsers/         VLR match HTML parsing
      metrics/         Custom metric engine placeholder
  web/                 Next.js dashboard
```

## Quick start

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

### Frontend

With the API running:

```bash
cd apps/web
npm install
npm run dev
```

Dashboard: [http://localhost:3000](http://localhost:3000)

### Database migrations

From `apps/api`, with `DATABASE_URL` pointing at PostgreSQL:

```bash
alembic upgrade head
alembic downgrade -1
alembic current
```

## Docker Compose

```bash
docker compose up --build
```

- Web: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)
- Postgres: `localhost:5432`
