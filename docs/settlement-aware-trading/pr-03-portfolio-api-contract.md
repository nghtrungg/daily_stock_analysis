# PR 3 — Portfolio API Contract

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Start from
a baseline containing PRs 1 and 2. Do not modify `apps/dsa-web/`.

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
PR 1 → PR 2 → PR 3 (this PR) → PR 4 → PR 5 → PR 6 → PR 7
```

## Purpose

Expose the settlement-aware ledger through stable additive FastAPI contracts for CLI,
API clients, Desktop compatibility, and the user's external Web application.

## Prerequisites

- PR 1 calendar and migration contracts.
- PR 2 settlement-aware portfolio enforcement.

## Scope

### 1. Trade request compatibility

Extend the existing route:

```text
POST /api/v1/portfolio/trades
```

Add an optional `executed_at` field while retaining `trade_date`.

Boundary behavior:

- Validate timezone-aware ISO input or normalize documented naive input to
  `Asia/Ho_Chi_Minh`.
- Require `.VN` under the active Vietnam profile.
- Preserve existing clients that only send `trade_date`.
- Return stable validation and conflict errors.

### 2. Snapshot fields

Add optional fields to each position:

```text
position_lifecycle
settlement_state
sellable_quantity
unsettled_quantity
next_sellable_at
settlement_calculation_status
settlement_warnings
```

Old records and clients must continue working when these fields are absent or `null`.

### 3. Settlement detail endpoint

Add:

```text
GET /api/v1/portfolio/positions/{symbol}/settlement
```

Support the current account-selection convention. Return:

```text
account_id
symbol
as_of
total_quantity
sellable_quantity
unsettled_quantity
settlement_state
next_sellable_at
calculation_status
warnings
lots[]
```

Lot data must not expose secrets or unrelated account data.

### 4. Structured sale rejection

Return HTTP 409:

```json
{
  "error": "insufficient_sellable_quantity",
  "message": "The requested quantity exceeds the currently sellable quantity.",
  "requested_quantity": 200,
  "held_quantity": 200,
  "sellable_quantity": 100,
  "unsettled_quantity": 100,
  "next_sellable_at": "2026-07-21T13:00:00+07:00"
}
```

Keep existing generic oversell behavior for requests above total held quantity.

### 5. External client contract

Update [`external-web-implementation.md`](external-web-implementation.md) if the final
wire contract differs from this brief. Do not implement the external frontend here.

## Likely files

- `api/v1/schemas/portfolio.py`
- `api/v1/endpoints/portfolio.py`
- `api/v1/errors.py` if structured error support requires it
- `docs/architecture/api_spec.json`
- Portfolio API tests
- API and settlement documentation
- `docs/CHANGELOG.md`

## Required tests

- Old request with only `trade_date`.
- New request with `executed_at`.
- Naive, aware, invalid, and wrong-timezone inputs.
- Snapshot serialization for unsettled, partial, sellable, and unknown states.
- Settlement endpoint account scoping and missing position.
- Structured insufficient-sellable response.
- Existing oversell, duplicate, busy, and generic validation contracts.
- OpenAPI or architecture-spec consistency.

## Validation

- Run focused portfolio API and schema tests.
- Run backend validation.
- Confirm no in-repository Web files changed.
- Confirm the external-Web contract examples match actual serialized responses.

## Exit criteria

- External clients can record execution time and inspect settlement state.
- All enforcement remains server-side.
- Existing API clients remain compatible.

## Rollback

The fields and endpoint are additive. Reverting the API may leave settlement data in
the database, which must remain usable by the service layer and harmless to old clients.

## Out of scope

- React, Web components, CSS, screenshots, or `apps/dsa-web/` changes.
- Analysis/report guardrails.
- Risk scoring, alerts, and outcomes.
