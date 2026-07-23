# Shared Supabase report integration

`daily_stock_analysis` remains a CLI-only analysis worker and keeps its local
SQLite history for compatibility and rollback. A tracked run requested by
`personal-stock-tracking` projects exactly one newly created `.VN` history
record into the dashboard-owned `public.analysis_runs` row through the signed
`analysis-callback` Edge Function.

The callback stores the run status, source analysis date, VND quote
provenance, summary, and a bounded report projection containing the stock
identity, report type, score, advice, trend, and four-part decision dashboard.
It never sends the raw LLM response, prompts, context snapshot, credentials,
or provider payloads.

SQLite is not deleted or rewritten during this transition. Before any future
direct Supabase migration, back up `data/stock_analysis_vn.db`, reconcile row
counts and representative reports, run compatibility tests, and retain a
documented rollback path.

See `docs/migration/schema-ownership-contract.md` for the cross-repository DDL
and DML boundary.
