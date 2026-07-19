# PR0 Baseline and Contract Freeze

## Baseline

- Recorded Git commit: `2966d4a53608aa0bc1f7bc714b68ac13939192b0`
- Runtime SQLite schema version:
  `2026-07-18-settlement-z-outcomes`
- Configuration schema version: `2026-07-18-settlement-risk`
- ORM table count: 32
- Local profile: Vietnam only (`.VN`, VND, `Asia/Ho_Chi_Minh`)

The capture basis is the recorded commit plus the intentionally preserved
settlement, portfolio, API, pipeline, configuration, storage, and documentation
work already present in the working tree on 2026-07-19. PR0 does not reset,
stash, rewrite, or silently omit that work.

The machine-generated schema contract is
[`pr0-schema-inventory.json`](pr0-schema-inventory.json). It inventories every
ORM column, foreign key, unique constraint, index, structured-JSON field, and
date/timestamp field. Regenerate or verify it with:

```bat
cmd.exe /d /c ".venv\Scripts\python.exe scripts\generate_pr0_schema_inventory.py"
cmd.exe /d /c ".venv\Scripts\python.exe scripts\generate_pr0_schema_inventory.py --check"
```

## Frozen computation contracts

The PR0 characterization suite freezes these behaviors without changing their
implementations:

- `StockAnalysisPipeline.process_single_stock()` performs fetch/persist,
  analysis, then optional single-stock notification in that order.
- Fetch failure remains fail-open when reusable history is available.
- Vietnam symbols, stock-index loading, provider fallback, technical
  indicators, realtime overlays, context-pack overview, report schema/language,
  deterministic guardrails, and notification failure behavior remain covered
  by the existing focused non-network tests.
- Repository metadata and return contracts remain covered by storage and
  repository tests, with the generated inventory preventing silent DDL drift.
- Six sanitized run scenarios live in
  `tests/fixtures/pr0/representative_runs.json`.

The existing `--dry-run` behavior remains unchanged in PR0. Its new
write-nothing/full-analysis contract belongs to PR4.

## Ownership gate

[`schema-ownership-register.json`](schema-ownership-register.json) records one
migration owner for all current SQLite/private-compute tables and the
dashboard-owned Supabase objects found at the recorded baseline. The dashboard
repository owns public portfolio/run DDL; this repository must not recreate
those objects in PR1.

Before PR1 starts, the dashboard repository maintainer must confirm the
recorded ownership boundary in its own repository or shared review. PR0 can
freeze the observed contract locally, but it cannot manufacture external
approval.

## PR0 validation set

The deterministic PR0 gate is:

```bat
cmd.exe /d /c ".venv\Scripts\python.exe -m pytest -m \"not network\""
cmd.exe /d /c ".venv\Scripts\python.exe scripts\generate_pr0_schema_inventory.py --check"
cmd.exe /d /c ".venv\Scripts\python.exe scripts\check_ai_assets.py"
```

No Supabase engine, migration, runtime, CLI, scheduler, or presentation-layer
refactor is authorized by this baseline PR.
