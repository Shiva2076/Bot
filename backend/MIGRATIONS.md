# Database migrations

Schema changes are applied with Alembic. FastAPI lifespan on Vercel does **not** run `create_all()` or `ALTER TABLE`.

## Prerequisites

- Working `DATABASE_URL` (URL-encode special characters in the password, e.g. `@` → `%40`).
- Dependencies installed from `requirements.txt` (includes `alembic` and `psycopg2-binary` for sync migrations).
- The application runtime continues to use `postgresql+asyncpg`. Alembic rewrites the URL to `postgresql+psycopg2` only for migrations.
- Run commands from the `backend/` directory.

## Apply migrations (safe path)

```bash
cd backend
alembic upgrade head
```

Use this against local Postgres, Docker Compose, or Supabase **before** relying on `/ready` or DB-backed API routes.

## Check current revision

```bash
cd backend
alembic current
alembic history
```

## Existing databases that already used `create_tables()`

If tables were created by the old startup bootstrap and match the models:

```bash
cd backend
alembic stamp head
```

Only stamp when the live schema already matches this revision. Prefer `alembic upgrade head` on empty or partially migrated databases.

## Legacy emergency bootstrap

`database.create_tables()` still exists for offline repair. Do **not** call it from the Vercel function lifespan. Prefer Alembic.

```bash
cd backend
python -c "import asyncio; from database import create_tables; asyncio.run(create_tables())"
```

## Vercel / production notes

1. Run `alembic upgrade head` from a trusted machine or CI job with network access to the database.
2. Deploy the API only after migrations succeed.
3. Use `GET /health` for process liveness and `GET /ready` for database readiness.
