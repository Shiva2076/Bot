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

## Revisions

| Revision | Contents |
|---|---|
| `20261030_0001` | Initial schema (all tables before Phase 1 order safety). |
| `20261112_0002` | Phase 1: `trades` order audit columns (`order_source` NOT NULL with CHECK, `override_reason`, `premarket_action_at_entry`, `prediction_gate_at_entry`), `trades.paper_signal_id` (+ partial unique index), `prediction_logs` gate/premarket/freshness columns, new tables `paper_signals` and `prediction_research_outcomes`. Existing trades are tagged `LEGACY`. |

### Databases already patched by the Bot1 `create_tables()` bootstrap

The Bot1 branch added the `20261112_0002` columns and tables at startup through `migrate_trade_order_audit`, `migrate_prediction_gate_logging` and `migrate_paper_engine`. Running `alembic upgrade head` on such a database fails with "column already exists". For those databases only:

```bash
cd backend
alembic stamp 20261112_0002   # after confirming the columns/tables above exist
alembic check                 # must report no new upgrade operations
```

Back up the database and run the upgrade on a copy first (`pg_dump` → restore into a scratch database → `alembic upgrade head` → `alembic check`).

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
