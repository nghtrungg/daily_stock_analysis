# PR2 Supabase Database Runtime

PR2 makes Supabase PostgreSQL selectable without changing the default local
runtime or the stock-analysis pipeline import contract. SQLite remains the
default until the later worker cutover. Production PostgreSQL DDL remains owned
by the reviewed files under `supabase/migrations/`; application startup never
creates or repairs PostgreSQL tables.

## Runtime selection

Use the local compatibility database:

```dotenv
DATABASE_BACKEND=sqlite
DATABASE_PATH=./data/stock_analysis_vn.db
```

Select the Supabase worker database:

```dotenv
DATABASE_BACKEND=supabase
SUPABASE_DB_URL=postgresql+psycopg2://dsa_worker.PROJECT_REF:URL_ENCODED_PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
```

`SUPABASE_DB_URL` is a secret. Put it in GitHub Actions Secrets, not repository
variables, `.env.example`, source files, logs, artifacts, Web settings, or a
browser bundle. When `DATABASE_BACKEND=supabase`, a missing or non-PostgreSQL
URL fails before engine creation. Error messages identify only the backend and
never include the URL.

The routine worker URL must use the least-privilege `dsa_worker` role created by
PR1. Do not use the migration administrator URL for analysis runs. Migration,
backup, advisor, and restore commands continue to use the separately protected
migration connection.

## Connection policy

The default is:

```dotenv
DATABASE_POOL_STRATEGY=null
DATABASE_CONNECT_TIMEOUT_SECONDS=10
DATABASE_STATEMENT_TIMEOUT_MS=120000
DATABASE_IDLE_TRANSACTION_TIMEOUT_MS=30000
```

`null` uses SQLAlchemy `NullPool`, matching current Supabase guidance for
short-lived, auto-scaling clients using Supavisor transaction mode. A bounded
queue is available for an explicit benchmark:

```dotenv
DATABASE_POOL_STRATEGY=queue
DATABASE_POOL_SIZE=1
DATABASE_MAX_OVERFLOW=0
DATABASE_POOL_TIMEOUT_SECONDS=10
DATABASE_POOL_RECYCLE_SECONDS=300
```

The initial worker is sequential, so the queue defaults allow one application
connection and no overflow. Keep the combined application and Supavisor
connection count below the project limit. Both strategies enable
`pool_pre_ping`, set the application name, and apply bounded connection,
statement, and idle-transaction timeouts. Call `DatabaseManager.dispose()` at
the end of an explicit worker lifecycle; process exit also disposes the engine.

## Compatibility boundary

- `src.repositories.database` owns engine, session-factory, health-check, and
  disposal behavior.
- `src.repositories.models` owns the SQLAlchemy declarative models.
- `src.storage` temporarily re-exports the models and `get_db()` so pipeline,
  services, and tests keep their current imports.
- SQLite alone runs `Base.metadata.create_all()` and the ordered legacy repair
  runner. PostgreSQL workers have DML-only runtime behavior.
- Unqualified ORM tables are translated to the private `dsa` schema only for
  PostgreSQL. SQLite retains its historical table names.
- Persisted instants bind as UTC to PostgreSQL `timestamptz` columns and retain
  the current UTC-naive Python compatibility contract.

Structured fields use JSONB on PostgreSQL and text compatibility on SQLite.
The shared JSON boundary accepts a native dictionary/list or one valid legacy
JSON string, preserves Vietnamese Unicode, distinguishes SQL NULL from JSON
null through explicit field policy, returns fresh mutable values, and raises a
field-only error for invalid JSON. Invalid legacy payloads must be quarantined
by the importer; they are never replaced silently with `{}` or `[]`.

The full `AnalysisContextPack` is still not persisted. Only the approved,
sanitized overview inside `analysis_history.context_snapshot` may be stored.

## Validation and rollback

Deterministic validation covers configuration failure, secret-safe errors,
SQLite health/disposal, both pool strategies, schema translation, stable
`src.storage` exports, JSONB/timestamptz DDL, Unicode/native/legacy/null/empty
JSON behavior, invalid JSON quarantine, and the current SQLite storage suite.

The `database-gate` CI job starts disposable local Supabase, applies the clean
migration chain, exports its local `DB_URL` only inside the runner, and executes
`tests/test_supabase_runtime_integration.py`. That check exercises a real
psycopg2 connection, health query, private `dsa` schema translation, JSONB
round-trip, UTC timestamp normalization, transaction rollback, and disposal.
The test skips when no disposable `SUPABASE_DB_URL` is present; do not point it
at production.

Rollback is additive: set `DATABASE_BACKEND=sqlite` and restore the prior
`DATABASE_PATH`. No PR2 code deletes or mutates the isolated SQLite database,
and no PostgreSQL DDL is applied at runtime.
