# PR 1 — Migration Foundation and Vietnam Calendar

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Do not
start PR 2 work in this task.

## Common architecture rules

1. `PortfolioTrade` remains the executed-transaction source of truth.
2. Portfolio positions and acquisition lots remain derived projections.
3. Position lifecycle, settlement state, and thesis state are independent fields.
4. Existing `DecisionAction` wire values remain unchanged.
5. Settlement dates, quantities, risk metrics, and action constraints are calculated
   by deterministic backend code.
6. The LLM may explain supplied settlement data but must not calculate or replace it.
7. Public API changes are additive and remain under `/api/v1/*`.
8. Existing reports and historical records remain readable when new fields are absent.
9. New behavior remains Vietnam-only: explicit `.VN` symbols, VND, Vietnamese reports,
   and `Asia/Ho_Chi_Minh`.
10. Settlement correctness is calculated on demand. Scheduler jobs may evaluate alerts
    and outcomes but must not be required to make a position correct.
11. The repository Web application under `apps/dsa-web/` is out of scope.
12. Do not create a second position, transaction, alert, or recommendation subsystem.

## Overall execution order

```text
PR 1 (this PR) → PR 2 → PR 3 → PR 4 → PR 5 → PR 6 → PR 7
```

## Purpose

Provide the migration and calendar foundations required by every later settlement
feature. Existing databases must upgrade safely, and Vietnam settlement calculations
must no longer silently treat every weekday as a confirmed trading or settlement day.

## Scope

### 1. Ordered database migrations

Extend the existing `schema_migrations` mechanism with an ordered, idempotent migration
runner.

Requirements:

- Run after the SQLAlchemy engine is ready and before services depend on new fields.
- Record each applied migration version and description.
- Apply each migration transactionally where SQLite permits.
- Detect already-applied changes safely.
- Fail startup with an actionable error when a required migration cannot complete.
- Do not rewrite, delete, or silently reset the existing Vietnam database.
- Add tests starting from a representative pre-migration database.

Keep the mechanism small and local to the current SQLAlchemy/SQLite architecture. Do
not introduce Alembic unless a concrete repository constraint makes the local runner
insufficient and the dependency is separately justified.

### 2. Versioned Vietnam market calendar

Extend `src/core/trading_calendar.py` or add a tightly scoped supporting module that its
existing Vietnam functions delegate to.

The calendar must distinguish:

```text
trading day
settlement day
non-trading closure
settlement-only closure
unknown calendar coverage
```

Bundled files belong in a committed location such as:

```text
config/market_calendars/vn/2026.json
```

Do not place bundled files under ignored runtime `data/`.

### 3. Settlement calculation result

Return a structured result rather than only a date:

```text
trade_date
settlement_date
estimated_sellable_at
calendar_version
policy_version
calculation_status: confirmed | degraded | unknown
warnings
```

Requirements:

- Normalize timestamps to `Asia/Ho_Chi_Minh`.
- Reject negative settlement-session counts.
- Count settlement sessions rather than calendar days.
- Preserve separate trading and settlement exclusions.
- Make unknown-year behavior explicit.
- Do not silently claim official accuracy from weekend-only fallback data.
- Preserve existing multi-market compatibility functions while changing only Vietnam
  behavior needed by this local profile.

## Likely files

- `src/storage.py`
- A small migration module under `src/` if needed
- `src/core/trading_calendar.py`
- `config/market_calendars/vn/*.json`
- `tests/test_storage.py`
- `tests/test_trading_calendar.py`
- Relevant settlement/calendar documentation
- `docs/CHANGELOG.md`

## Required tests

- Migration from an existing schema.
- Repeated initialization and concurrent initialization.
- Normal weekday and weekend.
- Friday purchase.
- Public holiday and consecutive holidays.
- Settlement-only closure.
- Year boundary.
- Missing and malformed calendar year.
- Negative settlement sessions.
- Naive and aware timestamps around midnight.
- Deterministic repeated calculation.

## Validation

- Run focused storage and trading-calendar tests.
- Run `python -m py_compile` for changed Python files.
- Run the backend gate if focused tests pass.
- Confirm the bundled calendar files are included in normal source and Docker build
  contexts.

## Exit criteria

- Existing databases upgrade without data loss.
- Repeated startup does not repeat or corrupt migrations.
- Calendar calculations expose coverage and degradation explicitly.
- Existing scheduling and market-phase tests remain compatible.

## Rollback

Reverting the code must not delete migration records or bundled calendar files from an
existing installation. Document whether newly created migration metadata can safely
remain after rollback.

## Out of scope

- Portfolio trade or lot settlement fields.
- FastAPI endpoints.
- Report or LLM changes.
- Alerts, outcomes, position sizing, and Web implementation.
