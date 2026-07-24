# Shared Supabase Schema Ownership Contract

## Purpose and status

This is the PR0 ownership contract between `daily_stock_analysis` and
`personal-stock-tracking`. Its machine-readable register is
[`schema-ownership-register.json`](schema-ownership-register.json), and the
same register and contract are recorded in both repositories.

The baseline commit identifiers identify what was inventoried; they are not
claims that these contract files already exist in either baseline commit.

## Ownership boundary

`daily_stock_analysis` owns:

- the 32-table legacy SQLite inventory frozen by PR0;
- the future `dsa` private compute namespace;
- future migrations for raw market data, analysis evidence, diagnostics, LLM
  usage, backtests, and sanitized result projections in that namespace; and
- the future protected deployment path for those migrations.

`personal-stock-tracking` owns:

- the `private` schema definition, without blanket ownership of every object
  another approved owner may later place there;
- the five current `public` portfolio, watchlist, wallet, and analysis-run
  tables;
- their RLS policies, cooldown trigger, public financial RPCs, and named
  `private` helper functions;
- owner-facing grants and Data API exposure decisions for those objects; and
- the future protected deployment path for those migrations.

Ownership is per object, not per database connection. The shared `public` and
`private` schema names do not grant either repository blanket ownership of
Supabase/platform objects or unnamed future objects. The `dsa` namespace is
reserved for compute objects so new worker DDL cannot collide with dashboard
helpers already under `private`.

## Write and access contract

- Only the owner authors DDL, migrations, grants, RLS policies, triggers, or
  functions for an object.
- DML access never transfers DDL ownership. In particular,
  `daily_stock_analysis` may update an approved `public.analysis_runs` worker
  contract but may not recreate or alter that table.
- Browser/Data API access uses authenticated sessions, explicit grants, and
  RLS. API exposure is a separate decision from object ownership.
- The worker uses a dedicated least-privilege role. It does not receive the
  dashboard's service-role key or migration-administrator credential.
- A future dashboard result projection or RPC must be named in the register,
  sanitized, explicitly granted, and reviewed before it becomes a consumer
  contract.
- The approved `public.analysis_runs` DML contract includes nullable
  `analysis_date` and `report` fields. New successful worker callbacks write
  both together; legacy rows may keep both null. `report` is a bounded
  owner-facing projection and must exclude raw prompts, model responses,
  context snapshots, credentials, and provider payloads.

## Change protocol

1. The current owner proposes the migration and classifies it as additive,
   compatible deprecation, or breaking.
2. If another repository consumes the object, that consumer reviews the
   proposed interface and rollout. Additive nullable fields are preferred.
3. The change bumps `contract_version` and updates both copies of the JSON
   register and this document in the same coordinated change.
4. Each repository runs its local contract check. When the sibling checkout is
   present, the check also requires parsed JSON equality.
5. Only the owner's protected migration workflow deploys the DDL. Remote
   Dashboard/SQL-editor changes are forbidden once migration history exists.
6. The owner verifies migration history, grants, RLS, and affected consumer
   behavior in a disposable or staging database before production.

Object moves and renames are ownership changes even when their columns do not
change. A proposed object whose name collides with the other repository's
registered object or reserved namespace is blocked until the contract is
updated and jointly reviewed.

## Compatibility and rollback

Breaking changes require an explicit transition window or coordinated cutover.
The provider keeps the old contract operational until every registered
consumer has moved. During incidents, prefer forward fixes; do not drop shared
columns, functions, policies, or JSONB data. Destructive recovery requires a
verified backup and separately approved recovery plan.

## Verification

From `daily_stock_analysis`:

```bat
cmd.exe /d /c ".venv\Scripts\python.exe scripts\check_schema_ownership_contract.py"
```

From `personal-stock-tracking`:

```bat
cmd.exe /d /c "npm run check:schema-contract"
```

<<<<<<< HEAD
The local check validates the registered owners, required object categories,
duplicate ownership, and the SQLite inventory declared in `src/storage.py`.
Set `PERSONAL_STOCK_TRACKING_ROOT` to a sibling checkout to additionally
require parsed JSON equality with the peer copy. Dashboard migration replay is
owned and verified by the dashboard repository's deployment workflow.
=======
The checks validate the registered owners, required object categories,
duplicate/unowned gates, the final object state discovered by replaying the
full dashboard migration chain, and the peer copy when the sibling repository
is available.
>>>>>>> origin/remote_user
