# PR3 PostgreSQL Bulk Repository Writes

PR3 removes statement-per-row behavior from the cloud database path while
retaining the existing SQLite compatibility behavior and repository return
contracts. It does not change pipeline stages, provider priority, report
generation, Vietnam-only validation, or notification behavior.

## Write contracts

- `save_daily_data()` normalizes and deduplicates dates before one batched
  existence read and bounded PostgreSQL upserts on `(code, date)`. Its return
  value remains the number of inserted rows, excluding conflict updates.
- Daily conflict updates explicitly cover mutable OHLCV, indicator, source,
  and `updated_at` fields. They never replace `id` or `created_at`.
- `save_news_intel()` normalizes one response before bounded upserts on the
  existing unique URL contract. Existing title, code, URL, and row identity
  remain immutable; non-empty mutable evidence/query fields retain the former
  update semantics.
- `IntelligenceRepository.upsert_items()` preserves source/scope/url
  deduplication. Rows with a real `source_id` use the existing composite
  constraint. Rows without one use a partial expression index that also
  includes `source_name` and `source_type`, closing PostgreSQL's nullable-unique
  concurrency gap.
- Backtest results use SQLAlchemy 2.x mapping inserts in bounded chunks.
  Recomputed overall and per-symbol summaries are collected and upserted as
  one natural batch.
- Decision-signal outcomes load existing horizons in one query and persist the
  evaluated group with one bounded upsert transaction while retaining input
  order and inserted-versus-updated counts.

Batch construction is bounded by both bind-parameter count and UTF-8 payload
bytes. A single oversized row is still emitted alone so the caller can receive
the database's explicit size/validation error rather than loop indefinitely.
Successful bulk operations log only operation name, row count, chunk count,
and duration. Raw evidence and payloads are never logged.

## Retry policy

PostgreSQL write transactions retry only SQLSTATE connection-class failures,
serialization failures (`40001`), deadlocks (`40P01`), or explicitly invalidated
connections. Unique/check/foreign-key and other validation failures are not
retried. Defaults are bounded and exponentially backed off:

```dotenv
POSTGRES_WRITE_RETRY_MAX=2
POSTGRES_WRITE_RETRY_BASE_DELAY=0.2
```

Each retry creates a fresh session and transaction. No transaction spans
provider or LLM network calls.

## Validation and rollback

Deterministic tests cover bind/payload chunking, native JSON mappings,
transient-error classification, SQLite compatibility, news/intelligence
deduplication, and backtest batches. The disposable Supabase integration gate
also checks a 250-bar write's statement count, repeat-update idempotency,
immutable `created_at`, a representative news batch, and two concurrent
nullable-`source_id` intelligence writers. Backtest metrics and decision
outcomes have the same bounded-statement and repeat-upsert assertions.

Rollback is additive. Revert the repository changes and the nullable-source
index migration; leaving that unique index in place is also safe because it
enforces the pre-existing logical deduplication contract. Setting
`DATABASE_BACKEND=sqlite` continues to use the legacy local compatibility path.
