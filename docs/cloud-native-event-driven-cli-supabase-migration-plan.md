# Cloud-Native Event-Driven CLI and Supabase Migration Plan

## Status

Ready for staged implementation beginning with PR 0. This document is an
implementation plan, not an applied migration. No later PR should begin until
the preceding PR's exit criteria and the review gates below are satisfied.

Implementation update (2026-07-21): PR 0 through PR 2 are complete on the
current migration baseline. PR 3 repository batching is in progress; its local
deterministic checks pass, while the disposable PostgreSQL statement-count and
concurrency gate remains required before PR 3 is ready to merge.

## Feasibility decision

The migration is feasible, and the computational core can remain behaviorally
intact. It is not a four-file connector swap, however. The current database,
Web/API, Desktop, scheduler, tests, workflows, configuration, and documentation
are coupled across the repository.

The safe interpretation of "keep the core intact" is:

- preserve the algorithms, stage ordering, provider fallback, deterministic
  guardrails, report contracts, Vietnam-only behavior, and domain-service
  semantics;
- allow dependency-injection and serialization-boundary changes needed to give
  those algorithms a PostgreSQL repository implementation;
- do not opportunistically rewrite `src/core/pipeline.py`,
  `data_provider/`, the technical-analysis engine, prompts, or report logic.

The target should be delivered as several independently reversible pull
requests. Deleting the presentation layers before the PostgreSQL worker has
passed a production-like canary would remove the current recovery path too
early.

## Repository findings that affect the proposal

1. The requested `src/repositories/database.py` does not currently exist.
   Engine creation, 32 ORM models, SQLite migrations, and many persistence
   operations are combined in the roughly 3,500-line `src/storage.py`.
2. `src/storage.py` imports SQLite-specific `insert`, enables WAL and busy
   timeout behavior, runs `Base.metadata.create_all()` at application startup,
   and contains a SQLite-oriented ordered migration runner.
3. The PostgreSQL branch of `save_daily_data()` currently performs row-by-row
   ORM updates. `save_news_intel()` and
   `IntelligenceRepository.upsert_items()` also perform select/update/insert
   loops that would produce avoidable internet round trips.
4. `AnalysisContextPack` is an in-memory Pydantic contract. The full pack is
   intentionally not persisted. Only its sanitized, low-sensitivity overview
   is stored inside `analysis_history.context_snapshot`. This security and
   data-minimization boundary must remain.
5. `NewsIntel` is already normalized into relational columns. The structured
   news/evidence values that are actually text-serialized JSON include
   `intelligence_items.raw_payload` and
   `decision_signals.evidence_json`.
6. Many other columns are text-serialized JSON. Converting only two columns
   would leave inconsistent Python contracts and repeated JSON parsing
   throughout services.
7. The existing `--dry-run` means "fetch data and skip AI analysis." The
   requested meaning, "perform analysis but do not commit or notify," is a
   different execution contract.
8. The existing `--schedule` starts a long-running local scheduler loop. A
   GitHub-hosted runner is ephemeral, so GitHub Actions cron must own the
   09:20/15:10 ICT schedule.
9. `.github/workflows/00-daily-analysis.yml` already has appropriate UTC cron
   expressions, but they are commented out. The workflow still uses
   `DATABASE_PATH` and extracts callback data from the runner's SQLite file.
10. The presentation cleanup is wider than three directories. At the time of
    this plan, 34 Python test files import FastAPI/API code and at least 43
    repository files refer to the Web or Desktop applications.
11. `docs/personal-portfolio-product-plan.md` currently says this repository
    will not be migrated wholesale to Supabase and describes one-symbol jobs
    with scheduled refresh deferred. The new architecture supersedes those
    sections and will require an explicit documentation decision.
12. The current worktree contains active, uncommitted settlement-aware,
    portfolio, API, configuration, pipeline, and storage changes. The first
    implementation branch must begin only after those changes have a stable
    baseline; no migration work should overwrite or silently omit them.

## Required architecture corrections

### Connection string

The proposed port `6543` is Supavisor transaction mode and is appropriate for
short-lived GitHub Actions application traffic. A shared-pooler username must
include the project reference:

```dotenv
SUPABASE_DB_URL=postgresql+psycopg2://dsa_worker.[PROJECT-REF]:[URL-ENCODED-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
```

Do not give the routine analysis workflow the `postgres` administrator
password. Create a dedicated `dsa_worker` login with only the required schema,
table, and sequence privileges.

Migrations, `pg_dump`, and administrative verification should not use the
transaction-pooler URL. Add a separate protected migration connection using the
direct connection where IPv6 is available, or Supavisor session mode on port
5432 from an IPv4-only runner:

```dotenv
SUPABASE_DB_MIGRATION_URL=postgresql+psycopg2://postgres.[PROJECT-REF]:[URL-ENCODED-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres?sslmode=require
```

Both values belong in GitHub Actions **Secrets**, not repository Variables,
source files, logs, artifacts, or the dashboard client.

### Scheduling

The target meaning of `--schedule` should be:

> Execute one scheduled batch now, mark its trigger as `schedule`, apply the
> trading-day guard, and exit.

It must not sleep or run an in-process scheduler. GitHub owns the two weekday
triggers:

```yaml
schedule:
  - cron: "20 2 * * 1-5" # 09:20 Asia/Ho_Chi_Minh
  - cron: "10 8 * * 1-5" # 15:10 Asia/Ho_Chi_Minh
```

GitHub scheduled workflows can be delayed and run only from the default branch.
The application must treat 09:20/15:10 as requested trigger times, not exact
execution guarantees.

### Dry-run

The target meaning of `--dry-run` should be:

- fetch current data;
- execute technical analysis, context-pack construction, LLM analysis, report
  validation, and deterministic guardrails;
- return/log the same in-memory result contract as a committed run;
- send no notifications;
- write no Supabase rows, update no run state, and mutate no remote queue state.

This cannot be implemented by merely suppressing the final history insert:
the current pipeline writes market data, fundamentals, news, diagnostics, and
history at several stages, and later stages read some of that data back.
Implement an explicit run/persistence policy and a tested dry-run storage
overlay or equivalent unit-of-work boundary. Do not hold a PostgreSQL
transaction open across provider and LLM network calls merely to roll it back.

### Dashboard access

"Dashboard interacts directly with the database" should mean the Supabase Data
API with a publishable key, authenticated user session, explicit grants, and
RLS. It must not mean putting a PostgreSQL password or service-role key in the
browser.

Keep internal computation evidence in a private schema. Expose only sanitized
user-facing tables, security-invoker views, or RPC contracts to the dashboard.

## Target architecture

```mermaid
flowchart LR
    U["Authenticated dashboard user"] --> E["Supabase Edge Function"]
    E -->|"create run + workflow_dispatch(run_id)"| G["GitHub Actions"]
    C["GitHub schedule<br/>02:20 / 08:10 UTC"] --> G
    M["Operator workflow_dispatch"] --> G
    G --> CLI["Python CLI entry point"]
    CLI --> P["Existing StockAnalysisPipeline"]
    P --> R["Repository compatibility facade"]
    R --> DB["Supabase Postgres<br/>private compute schema"]
    DB --> V["RLS-protected public results/views"]
    V --> U
```

Recommended ownership boundary:

- private compute schema, for example `dsa`: price history, raw analysis
  snapshots, evidence, diagnostics, LLM usage, backtest data, and internal
  portfolio/settlement sidecars;
- exposed `public` schema: authenticated run lifecycle, sanitized quote/result
  projections, and existing dashboard-owned portfolio/watchlist tables;
- `dsa_worker`: direct database login used only by GitHub Actions;
- `authenticated`: dashboard access through RLS;
- migration administrator: used only by a protected manual migration workflow.

The exact public/private split must be agreed with the separate dashboard
repository before either repository claims migration ownership for shared
tables such as `analysis_runs`.

Maintain a reviewed schema-ownership register for every shared table, view,
function, trigger, RLS policy, and enum. Each object must have exactly one
migration-owning repository. The other repository may consume the contract and
run compatibility tests, but must not ship competing DDL. Only one protected
deployment path may apply production migrations at a time.

## Target code boundaries

Introduce these boundaries without changing pipeline algorithms:

```text
src/
├─ repositories/
│  ├─ database.py          # Engine, session factory, health check, disposal
│  ├─ models.py            # SQLAlchemy declarative models and shared DB types
│  ├─ stock_repo.py        # Price-bar reads and PostgreSQL bulk upsert
│  ├─ analysis_repo.py     # Analysis history and context snapshots
│  ├─ intelligence_repo.py # News/evidence bulk upsert and retention
│  └─ ...                  # Existing domain repositories
├─ storage.py              # Temporary compatibility facade, then thin exports
└─ schema_migrations.py    # Legacy SQLite importer only; no runtime DDL

supabase/
├─ config.toml
├─ migrations/             # Supabase CLI-created, reviewed SQL migrations
└─ tests/                  # RLS, grants, constraints, and migration SQL tests
```

`StockAnalysisPipeline` should continue to receive an object exposing its
current database method signatures. Initially, `src/storage.py` should delegate
those calls to the new repositories so pipeline call sites do not need a broad
rewrite.

## Data contract and model migration

### PostgreSQL-native types

- Use `JSONB` for structured JSON and return native Python dictionaries/lists
  from the ORM.
- Use `TIMESTAMP WITH TIME ZONE` for new persisted instants and store UTC.
  Convert to `Asia/Ho_Chi_Minh` only at user-visible boundaries.
- Keep `Date` for Vietnam trading dates.
- Preserve current price/indicator numeric semantics in the first migration.
  A later reviewed migration may replace `Float` with explicit `Numeric`
  precision; combining that change with the storage cutover would increase
  reconciliation risk.
- Preserve all existing unique constraints, foreign keys, indexes, and return
  value semantics unless a PostgreSQL concurrency test demonstrates a defect.

### JSONB inventory

At minimum, migrate the following text-serialized JSON fields:

| Model | Current field(s) | Target |
| --- | --- | --- |
| `AnalysisHistory` | `raw_result`, `context_snapshot` | `JSONB` |
| `IntelligenceItem` | `raw_payload` | `JSONB` |
| `FundamentalSnapshot` | `payload`, `source_chain`, `coverage` | `JSONB` |
| `BacktestSummary` | `advice_breakdown_json`, `diagnostics_json` | `JSONB` with names cleaned in a later compatibility release |
| `PortfolioTradeSettlement` | `warnings_json` | `JSONB` |
| `PortfolioDailySnapshot` | `payload` | `JSONB` |
| `AgentProviderTurn` | `messages_json` | `JSONB` |
| `LLMUsage` | `provider_usage_json`, `known_dynamic_marker_positions` | `JSONB` |
| `AlertRuleRecord` | `parameters`, `cooldown_policy`, `notification_policy` | `JSONB` |
| `AlertTriggerRecord` | `diagnostics` | `JSONB` |
| `AlertNotificationRecord` | `diagnostics` | `JSONB` |
| `DecisionSignalRecord` | `evidence_json`, `data_quality_summary_json`, `metadata_json` | `JSONB` |
| `SettlementOutcomeRecord` | `ambiguity_flags_json` | `JSONB` |

Do not convert ordinary prose fields such as news title, snippet, analysis
summary, invalidation text, or report Markdown to JSONB.

Do not introduce a persisted full Context Pack. Migrate
`analysis_history.context_snapshot` to JSONB while continuing to persist only
the currently approved sanitized `analysis_context_pack_overview`.

During transition, one shared compatibility helper must accept either a legacy
JSON string or an already-decoded dict/list. Its contract must be field-aware
and explicit:

- pass native dict/list values through without double encoding;
- decode valid legacy strings once, including UTF-8 Vietnamese content;
- distinguish SQL `NULL`, JSON `null`, empty objects, and empty arrays according
  to each column's existing business contract;
- quarantine invalid legacy JSON during import instead of silently replacing
  it with an empty value;
- return fresh values or replace the complete top-level value on updates.
  In-place dict/list mutation is allowed only when SQLAlchemy mutable tracking
  is configured and covered by a persistence test.

Keep the helper at the repository/import serialization boundary. Domain
services should receive native Python values and should not call
`json.loads()` or `json.dumps()` for JSONB-backed fields. Remove scattered
manual serialization only after the data migration and PostgreSQL repository
integration tests pass.

### Indexes

Retain relational indexes used by the current queries. Add JSONB GIN or
expression indexes only for measured dashboard/research queries, for example:

- context-pack data-quality level;
- context-pack block status;
- evidence source/type;
- selected run/result metadata.

Do not add a broad GIN index to every JSONB column; large raw snapshots would
increase write cost and storage without a proven query.

## Migration management

`Base.metadata.create_all(engine)` is useful for disposable tests, but it is not
the production migration mechanism. Runtime workers must have DML privileges,
not DDL privileges, and must not race to change schema at cold start.

Production schema changes should be SQL migrations created with:

```text
supabase migration new <descriptive_name>
```

The protected migration workflow should:

1. validate migration ordering and SQL against a disposable Postgres/Supabase
   environment;
2. create or verify a hosted backup;
3. apply migrations with the migration URL;
4. run Supabase security and performance advisors;
5. verify grants, RLS, constraints, indexes, and schema version;
6. stop before data import if any validation fails.

Keep the current ordered SQLite runner only long enough to read/export the
legacy database. Do not reuse its `schema_migrations` table as Supabase's
migration history.

## Implementation sequence

### PR 0 — Freeze the baseline and contracts

Goal: establish evidence that later refactors preserve computation.

Tasks:

1. Resolve or intentionally baseline the current uncommitted settlement,
   portfolio, API, pipeline, configuration, and storage work.
2. Record the baseline commit and current schema version.
3. Inventory every ORM table, foreign key, unique constraint, index, JSON
   serialization point, and timestamp semantic.
4. Create the shared schema-ownership register with the dashboard repository.
   Record one owner for every shared table, view, function, trigger, RLS
   policy, enum, and production migration workflow.
5. Add characterization tests around:
   - `StockAnalysisPipeline` stage order;
   - `.VN` rejection and Vietnam-only index behavior;
   - provider priority/fallback;
   - technical indicators and realtime overlays;
   - AnalysisContextPack summary/overview;
   - report schema, language, and integrity checks;
   - phase, daily-market-context, settlement, and trade-plan guardrails;
   - notification fail-open behavior;
   - repository method return contracts.
6. Save representative sanitized fixtures for single-stock, batch, failed
   provider, stale quote, partial data, and no-news runs.

Exit criteria:

- the deterministic non-network suite passes;
- no target refactor has started;
- the JSON/timestamp inventory is reviewed;
- the schema-ownership register has no unowned or multiply owned object.

PR0 ownership continuation (2026-07-19): the versioned register and ownership
contract are now mirrored in `daily_stock_analysis` and
`personal-stock-tracking`. They reserve `dsa` for private compute objects,
leave dashboard portfolio/run DDL with `personal-stock-tracking`, and define
the coordinated change, compatibility, deployment, and rollback protocol.

### PR 1 — Add Supabase migrations and security boundaries

Goal: create an empty, secured PostgreSQL schema without changing runtime.

Tasks:

1. Initialize `supabase/config.toml` and generate migration files through the
   Supabase CLI.
2. Create the private compute schema and all model tables with PostgreSQL-native
   types.
3. Create the dashboard-facing run/result contract or views only after
   coordinating table ownership with the external dashboard repository.
   Dashboard-readable views must use `security_invoker = true`; otherwise keep
   them in an unexposed schema with `anon` and `authenticated` access revoked.
4. Create `dsa_worker` with login but without administrator or `BYPASSRLS`
   privileges. Grant only required schema usage, table DML, and sequence usage.
5. Enable RLS on every exposed table and define ownership policies using
   `TO authenticated` plus an ownership predicate. Add both `USING` and
   `WITH CHECK` for updates.
6. Revoke default `anon` access. Expose only the columns/contracts the
   dashboard needs.
7. Add table/check constraints for uppercase `.VN` symbols, VND currency,
   run-state transitions, nonnegative counts, and required timestamps.
8. Add SQL tests for two-user isolation, worker access, anonymous denial, and
   repeated migration application in a disposable environment.

Exit criteria:

- clean schema creation passes;
- migrations are idempotent at the migration-history level;
- RLS/grant tests and advisors pass;
- the schema matches the ownership register and no competing DDL exists in the
  dashboard repository;
- no production data has been copied.

### PR 2 — Extract the database engine and models

Goal: make PostgreSQL selectable while keeping pipeline imports stable.

Files:

- `requirements.txt`
- `.env.example`
- `src/config.py`
- `src/core/config_registry.py`
- new `src/repositories/database.py`
- new `src/repositories/models.py`
- `src/storage.py`
- database-focused tests and deployment docs

Tasks:

1. Add `psycopg2-binary` with a reviewed version range. Keep the synchronous
   SQLAlchemy API; moving the current synchronous pipeline to `asyncpg` would
   force an unrelated async rewrite.
2. Remove FastAPI dependencies only in the later presentation cleanup PR, not
   in this database PR.
3. Load `SUPABASE_DB_URL` from configuration and fail closed in cloud mode when
   it is missing. Never log the URL or password.
4. Configure a deliberately small SQLAlchemy pool for one GitHub runner, with
   `pool_pre_ping`, bounded `pool_size`/`max_overflow`, checkout timeout,
   recycle policy, and explicit engine disposal. Benchmark a small queue
   against `NullPool`; keep connection count below the configured worker
   concurrency.
5. Set connection timeout, application name, and bounded statement/idle
   transaction timeouts where the pooler supports them.
6. Remove SQLite PRAGMAs, lock retries, SQLite DDL repair paths, and
   `BEGIN IMMEDIATE` from the PostgreSQL runtime.
7. Keep a temporary test/import adapter only if needed to migrate the existing
   SQLite-heavy tests and legacy data.
8. Make `src/storage.py` a compatibility facade so `get_db()` and existing
   model imports keep working while repositories move.
9. Add the shared JSON compatibility helper at the repository/import boundary.
   Cover legacy strings, native dict/list values, SQL `NULL`, JSON `null`,
   empty values, invalid JSON, and update persistence. Domain services must not
   manually serialize JSONB values.

Exit criteria:

- engine health check passes against a disposable PostgreSQL service;
- a missing/invalid database secret fails safely without leaking it;
- current pipeline unit tests still import through `src.storage`.

### PR 3 — Refactor repositories and bulk writes

Goal: remove SQLite SQL and internet-latency amplification.

Tasks:

1. Replace daily-bar row loops with chunked PostgreSQL
   `insert(...).on_conflict_do_update()` on `(code, date)`.
2. Preserve `save_daily_data()`'s current return value: count newly inserted
   rows, not updated rows. Use one batched existence read plus the upsert in the
   same short transaction, or another tested PostgreSQL-safe strategy.
   Conflict updates must not overwrite immutable provenance such as
   `created_at`; explicitly list the mutable market-data columns.
3. Replace news select/insert loops with one normalized batch and
   `ON CONFLICT` using the existing URL uniqueness contract.
4. Replace intelligence-item loops with a PostgreSQL upsert that preserves the
   current source/scope deduplication semantics. Add concurrent-writer tests for
   nullable `source_id` cases.
5. Use SQLAlchemy 2.x `Session.execute(insert(Model), mappings)` or
   dialect-specific multi-row upserts. Do not adopt legacy
   `bulk_save_objects()` as the default; SQLAlchemy documents it as a legacy
   API.
6. Batch fundamental snapshots, backtest metrics, decision outcomes, and other
   naturally grouped inserts. Do not force unrelated single-record business
   transactions into bulk APIs.
7. Choose chunk size by total bind parameters and payload bytes, not only row
   count. Record rows, chunks, duration, and retry category without logging raw
   evidence.
8. Retry only transient connection, deadlock, or serialization failures with
   bounded backoff. Do not retry constraint or validation errors.
9. Add idempotency and concurrency tests for every upsert key.

Exit criteria:

- daily bars, news, indicators, and metric batches use bounded round trips;
- a representative 250-bar write performs one batched existence query plus the
  required chunked upsert statements, with no SQL statement per row;
- statement-count tests use the same invariant for representative news,
  indicator, and metric batches;
- conflict-update tests prove immutable creation/provenance fields and current
  repository return values are preserved;
- duplicate/retry behavior is deterministic;
- repository contract tests pass on PostgreSQL.

### PR 4 — Implement the new dry-run execution policy

Goal: satisfy "analyze fully, write nothing, notify nobody."

Tasks:

1. Introduce a small immutable run policy, for example:
   `analyze=True`, `persist=False`, `notify=False`.
2. Pass it through orchestration seams without changing technical-analysis,
   context-pack, LLM, report, or guardrail algorithms.
3. Provide an ephemeral persistence overlay for write-then-read data needed in
   the same run, or refactor that data handoff explicitly. Do not open one
   long-lived database transaction across network calls.
4. Capture would-be persistence events for diagnostics so tests can prove which
   writes were suppressed without storing sensitive payloads.
5. Make all notification routes impossible under the dry-run policy, including
   single-stock, aggregate, error, callback, and sidecar notifications.
6. Add a database audit test that snapshots table counts/updated timestamps
   before and after a full dry run and proves no changes.

Exit criteria:

- LLM analysis and every deterministic guardrail execute;
- the returned result matches committed-run shape;
- no database or notification side effect occurs.

### PR 5 — Replace `main.py` with a thin one-shot CLI

Goal: make the process an explicit worker entry point.

Target job contract:

```text
--symbol SYMBOL.VN   Run exactly one canonical Vietnam symbol.
--batch              Run STOCK_LIST sequentially.
--schedule           Run the scheduled universe once and exit.
--dry-run            Full analysis with no persistence or notifications.
```

Tasks:

1. Make `--symbol`, `--batch`, and `--schedule` mutually exclusive.
2. Validate uppercase canonical `.VN` symbols before constructing the
   pipeline.
3. Define `--batch` input as `STOCK_LIST`; the workflow may populate it from a
   trusted run record or a validated operator input.
4. Define `--schedule` input as the configured scheduled universe from
   Supabase or `STOCK_LIST`, and apply the existing trading-day guard.
5. Force sequential execution (`MAX_WORKERS=1`) for the initial cloud release
   to preserve provider stability and report determinism.
6. Remove Web/API imports, aliases, host/port resolution, server startup,
   runtime Web scheduler ownership, and keepalive loops.
7. Preserve exit-code distinctions for success, invalid input/configuration,
   skipped non-trading day, partial symbol failure, and fatal infrastructure
   failure.
8. Decide separately how to expose current backtest and notification-diagnostic
   jobs. Prefer dedicated module entry points rather than silently deleting
   pure-compute capabilities.

Exit criteria:

- each job mode runs once and exits;
- `--schedule` never sleeps;
- invalid/non-Vietnam input exits before provider or database work;
- CLI contract tests replace server-mode tests.

### PR 6 — Convert GitHub Actions into the event-driven worker

Goal: make GitHub Actions the only compute runtime and scheduler.

Tasks:

1. Enable the two UTC cron entries corresponding to 09:20 and 15:10 ICT.
2. Keep `workflow_dispatch`; separate a trusted dashboard `run_id` path from
   direct operator symbol/batch inputs.
3. Treat all dispatch inputs as untrusted. For dashboard requests, re-read the
   symbol, owner scope, and portfolio context from Supabase using `run_id`.
4. Pass `SUPABASE_DB_URL` only from GitHub Secrets.
5. Add least-privilege workflow permissions, environment protection for
   production, timeout, global concurrency, and explicit cancellation policy.
6. Record queued/running/succeeded/failed state, GitHub run ID/URL, timestamps,
   safe error code, symbol set, trigger source, and schema/app version.
7. Retain a database-backed queue/cooldown when the dashboard contract requires
   inspectable FIFO behavior. GitHub concurrency alone is not a durable queue.
8. Remove SQLite directory creation, `DATABASE_PATH`, and callback extraction
   from a local database. If the dashboard still needs a callback, make it a
   small signed status notification after the authoritative Supabase
   transaction, not the primary persistence mechanism.
9. Upload sanitized reports/logs as optional debugging artifacts; Supabase is
   the authoritative result store.
10. Add a failure-finalizer step that marks an owned active run failed without
    overwriting an already terminal run.

Exit criteria:

- manual single and batch jobs pass;
- both scheduled invocations select the correct mode and exit;
- duplicate and failed jobs leave inspectable, terminal state;
- secrets are absent from logs/artifacts.

### PR 7 — Migrate legacy SQLite data and cut over

Goal: move valid history without corrupting JSON, timestamps, or IDs.

Tasks:

1. Tag the reviewed pre-cutover baseline, stop SQLite writers, and take a
   read-only copy of `./data/stock_analysis_vn.db`. Record its cryptographic
   checksum, size, schema version, and row-count manifest.
2. Export table counts, min/max IDs, date ranges, null counts, unique-key
   duplicates, invalid JSON rows, and foreign-key orphans.
3. Build a one-off, restartable importer that:
   - reads SQLite in read-only mode;
   - copies tables in foreign-key order;
   - validates `.VN`, VND, and enum constraints;
   - converts valid JSON strings to objects/arrays;
   - quarantines invalid JSON with table, primary key, field, and safe error
     category;
   - applies an approved per-column rule for mixed local-naive and UTC-naive
     timestamps;
   - imports in bounded PostgreSQL batches;
   - preserves IDs where required and resets sequences afterward.
4. Re-run the importer in verification mode to prove idempotency.
5. Compare row counts, business-key counts, representative context snapshots,
   latest prices, decision signals, settlement data, and backtest summaries.
6. Run a no-notify `VNM.VN` canary, then a small batch, then one scheduled-mode
   canary.
7. Restore the tagged SQLite workflow and snapshot in an isolated checkout and
   execute a read-only reconciliation/canary. This proves rollback before any
   presentation code is deleted.
8. Keep the SQLite snapshot read-only through at least one accepted production
   cycle and the agreed rollback-retention window.

Exit criteria:

- reconciliation is documented;
- no invalid JSON or ambiguous timestamp is silently coerced;
- the snapshot checksum and manifest match, and the isolated rollback drill
  succeeds;
- Supabase is the only active runtime store.

### PR 8 — Remove presentation, server, Desktop, and obsolete deployment code

Goal: delete unsupported product surfaces only after cutover succeeds.

Prefer a repository tag/branch for historical recovery, then use reviewed
`git rm` changes. Do not move obsolete applications into a permanent
`archive/` directory inside the active source tree.

Primary removal candidates:

```text
api/
apps/dsa-web/
apps/dsa-desktop/
server.py
webui.py
src/webui_frontend.py
static/                    # only generated Web assets; inspect non-Web files first
.github/workflows/desktop-release.yml
Web/Desktop packaging scripts
OpenAPI generation/spec artifacts
Web/Desktop Docker services and publishing workflows, if no CLI image is retained
API/Web/Desktop-only tests
```

Required follow-up:

1. Remove `fastapi`, `uvicorn[standard]`, and `python-multipart`.
   `websockets` is not a direct current requirement; verify transitive and bot
   usage before claiming it was removed.
2. Remove Web/Desktop config keys, API auth/session code, CORS settings,
   runtime scheduler ownership, static-asset checks, CI gates, release
   workflows, Docker entry points, and docs that no longer have consumers.
3. Preserve outbound notifications unless a separate product decision removes
   them. Inbound long-lived bot streams need a reachability decision; they are
   not automatically authorized for deletion by the Web/API/Desktop request.
4. Do not delete `src/services/` modules merely because an API endpoint was
   their former caller. Classify each as core computation, worker support,
   notification, dashboard-owned, or truly unreachable.
5. Update `README.md` only at this point because the project positioning and
   quick start have changed at homepage level.
6. Update detailed guides, bilingual pairs, `docs/INDEX*.md`, CI documentation,
   and `docs/CHANGELOG.md` using the flat `[Unreleased]` entry format.
7. Supply deletion evidence in the PR: CLI help, workflow canary, test results,
   and screenshots only if any surviving report/page rendering changed.

Exit criteria:

- no imports or references to removed surfaces remain;
- CI contains backend, PostgreSQL/migration, and workflow gates only;
- the pre-cutover tag resolves, the SQLite snapshot remains readable and
  checksum-verified, and the documented restore command was exercised in PR 7;
- a fresh clone can run the documented GitHub Actions/CLI path.

### PR 9 — Production hardening and launch

Goal: make the new path operable and reversible.

Tasks:

1. Add structured, secret-safe run logging and stable error codes.
2. Add database connection, query-duration, batch-size, queue-depth, provider
   fallback, data-quality, and run-duration metrics.
3. Configure budget/timeout alerts for GitHub Actions and Supabase connections.
4. Run Supabase security/performance advisors after final DDL.
5. Exercise backup restoration in a non-production project.
6. Document secret rotation for the worker role and dashboard dispatch token.
7. Document rollback triggers, owner, steps, and evidence.

Exit criteria:

- launch checklist is signed off;
- backup restore and credential rotation are tested;
- rollback does not require reconstructing deleted local UI code from memory.

## Verification matrix

### Database and repositories

- Apply every migration to an empty disposable PostgreSQL database.
- Apply the production migration chain to a copy of representative legacy data.
- Verify RLS with two authenticated users, `anon`, `dsa_worker`, and the
  migration administrator.
- Verify all foreign keys, unique constraints, sequences, and indexes.
- Round-trip Unicode Vietnamese text, JSONB dict/list/null values, dates, aware
  timestamps, and non-finite numeric normalization.
- Prove bulk upserts are idempotent and safe under two concurrent writers.
- Measure SQL statement count for representative 250-bar and news batches.
- Test connection timeout, stale connection recovery, statement timeout, and
  pool exhaustion.

### Core computational guardrails

- Keep `AnalysisContextPack.PACK_VERSION == "1.0"` unless an intentional schema
  change is separately approved.
- Verify the fixed block/status scoring, limitations, and sanitized overview.
- Prove full pack values, prompts, credentials, portfolio internals, and raw
  provider payloads are not exposed in dashboard projections.
- Verify Vietnam history sanitization and foreign/Han legacy filtering.
- Verify `.VN` validation, VND values, and `Asia/Ho_Chi_Minh` presentation.
- Verify the Vietnam-only stock index and `ENABLED_MARKETS=vn`.
- Verify legacy market review, remote multi-market index refresh, and automatic
  Desktop updates remain disabled or are removed, never reactivated.
- Run technical-indicator, realtime-overlay, provider-fallback, stale/partial
  data, no-news, fundamental-fallback, and report-language tests.
- Run phase, daily-market-context, trade-plan, settlement-decision, and
  settlement-risk guardrail tests.
- Run report schema, renderer, integrity, decision-signal extraction,
  attribution, outcome, and backtest regression tests.

### CLI and workflow

- `--symbol VNM.VN` processes exactly one symbol.
- invalid or foreign symbols fail before database/provider access.
- `--batch` processes the configured list sequentially and reports partial
  failure correctly.
- `--schedule` executes once, respects the trading calendar, and exits.
- `--dry-run` executes analysis/guardrails with zero database mutations and
  zero notifications.
- workflow dispatch validates `run_id` ownership and ignores forged symbol/user
  context.
- cron-to-ICT mapping is asserted in tests.
- concurrency/cooldown prevents simultaneous provider jobs.
- every claimed run reaches an idempotent terminal state.

### Cleanup

- Fresh dependency installation succeeds without FastAPI/Uvicorn.
- `rg` finds no imports or operational references to `api`, WebUI, Electron,
  host/port server flags, or deleted workflows outside historical changelog
  entries where they are intentionally retained.
- Backend CI, PostgreSQL integration, migrations, and workflow contract tests
  pass from a fresh clone.

## Rollout

1. Complete PRs 0-6 without deleting the current product surfaces.
2. Apply migrations to a staging Supabase project.
3. Import a sanitized copy of SQLite data and reconcile it.
4. Run dry-run, single-symbol, small-batch, and scheduled-mode canaries.
5. Back up production Supabase, apply the reviewed schema, import production
   SQLite, and switch workflow secrets.
6. Observe at least one accepted 09:20 and 15:10 ICT cycle.
7. Only then merge the presentation/deployment cleanup.

## Rollback

- Application rollback: revert to the last tagged worker commit and restore the
  prior workflow file. Git history retains removed Web/Desktop/API code.
- Runtime rollback before cleanup: disable the Supabase workflow and re-enable
  the verified SQLite workflow from the tagged baseline.
- Database rollback: prefer forward fixes for additive schema problems. Do not
  drop JSONB columns/tables during an incident.
- Data-corruption rollback: stop writers, preserve evidence, restore the
  verified Supabase backup into a controlled project, reconcile, then cut over.
- Credential incident: disable the worker role, rotate its password and GitHub
  secret, inspect database and workflow audit logs, then re-enable.

## Definition of done

- GitHub Actions is the only compute and scheduling runtime.
- The CLI is one-shot and exposes the approved processing modes.
- Supabase PostgreSQL is the only active persistence store.
- The dashboard accesses only RLS-protected, sanitized contracts.
- Core pipeline behavior, technical analysis, providers, domain services,
  deterministic guardrails, Vietnamese reports, `.VN`, VND, and ICT behavior
  pass regression tests.
- Dry-run performs full analysis with no persistent or notification side
  effects.
- Price bars, evidence, and metric batches use measured bulk operations.
- Every shared Supabase object has one migration-owning repository and one
  protected production deployment path.
- React, Electron, FastAPI, server startup, and obsolete deployment surfaces
  are removed with no dangling references.
- Migration, canary, monitoring, backup, secret rotation, and rollback evidence
  is documented.

## Primary references

- [Supabase database connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase Postgres roles](https://supabase.com/docs/guides/database/postgres/roles)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [SQLAlchemy PostgreSQL dialect, JSONB, and ON CONFLICT](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [SQLAlchemy connection pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [SQLAlchemy 2.x bulk DML](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html)
- [GitHub Actions workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
