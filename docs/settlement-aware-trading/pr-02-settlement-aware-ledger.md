# PR 2 — Settlement-Aware Portfolio Ledger

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Start from
a baseline containing PR 1. Do not add public Web behavior in this task.

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
PR 1 → PR 2 (this PR) → PR 3 → PR 4 → PR 5 → PR 6 → PR 7
```

## Purpose

Make the existing portfolio ledger settlement-aware so a recorded sale cannot consume
shares that have not become sellable.

## Prerequisite

PR 1 migration runner and Vietnam settlement calendar are available and tested.

## Scope

### 1. Trade execution timestamp

Add an optional execution timestamp to the existing `PortfolioTrade` model and service
contract.

- Normalize new values to `Asia/Ho_Chi_Minh`.
- Preserve `trade_date` for compatibility and reporting.
- Keep old records valid when their execution time is missing.
- Mark inferred legacy timing explicitly instead of fabricating precision.

### 2. Settlement sidecar

Add a one-to-one settlement annotation for buy trades:

```text
PortfolioTradeSettlement
- trade_id
- settlement_date
- estimated_sellable_at
- actual_sellable_at
- calendar_version
- policy_version
- calculation_status
- warnings_json
- created_at
- updated_at
```

The sidecar freezes the calculation provenance without making derived position lots the
source of truth.

### 3. Settlement-aware acquisition replay

Extend portfolio replay so acquisition lots carry:

```text
remaining_quantity
estimated_sellable_at
actual_sellable_at
settlement_state
calendar_status
source_trade_id
```

Settlement availability is independent of the selected cost-basis method. Average-cost
accounting must still retain acquisition timing for sellability enforcement.

### 4. Transactional sale enforcement

Inside the same portfolio write transaction:

- Calculate held, sellable, and unsettled quantities as of the sale timestamp.
- Allocate a sale only against sellable acquisitions.
- Reject a request above the sellable quantity even when total held quantity is larger.
- Preserve existing oversell validation.
- Preserve trade UID and deduplication behavior.
- Prevent two concurrent requests from both consuming the same sellable quantity.

Add a domain exception containing:

```text
requested_quantity
held_quantity
sellable_quantity
unsettled_quantity
next_sellable_at
```

### 5. Derived state

Expose separate derived values internally:

```text
position_lifecycle: open | closed
settlement_state: unsettled | partially_sellable | sellable | unknown
total_quantity
sellable_quantity
unsettled_quantity
next_sellable_at
settlement_calculation_status
```

Do not introduce a combined mutable position-status enum.

## Likely files

- `src/storage.py`
- `src/repositories/portfolio_repo.py`
- `src/services/portfolio_service.py`
- Portfolio service and persistence tests
- Settlement architecture documentation
- `docs/CHANGELOG.md`

## Required tests

- One buy lot.
- Multiple lots with different sellable timestamps.
- Partially and fully sellable positions.
- Sale consuming only eligible lots.
- Sale above sellable but below total quantity.
- Multiple partial sales.
- Existing full oversell behavior.
- FIFO and average-cost modes.
- Corporate-action interaction.
- Duplicate trade request.
- Concurrent sale attempts.
- Calendar degraded and unknown states.
- Replay, cache replacement, and refresh idempotency.
- Legacy trades without execution timestamps.

## Validation

- Run focused portfolio repository and service tests.
- Run changed-file compilation.
- Run the backend gate after focused tests pass.
- Inspect an upgraded copy or fixture database; never mutate the user's production
  database as validation.

## Exit criteria

- Backend trade recording cannot consume unsettled shares.
- Settlement enforcement is independent of UI behavior.
- Position replay remains deterministic and backward compatible.
- No scheduler run is required to make quantities correct.

## Rollback

Reverting service behavior may leave additive settlement tables and nullable fields in
the database. They must remain harmless to the older code. Document any manual cleanup
separately; do not automate destructive rollback.

## Out of scope

- Public API response changes beyond internal compatibility needs.
- Analysis/report guardrails.
- Risk scoring, alerts, outcomes, and Web implementation.
