# External Web Implementation — Settlement-Aware Trading

## Audience and repository boundary

This document is for the user's separate primary Web application. It must be applied in
that Web application's repository, not in `apps/dsa-web/` in Daily Stock Analysis
Vietnam.

The frontend consumes authenticated `/api/v1/*` contracts. It must not calculate
authoritative settlement dates, sellable quantities, risk scores, or action
constraints in the browser.

## When to use this plan

The external Web work can be implemented incrementally:

```text
Backend PR 3 available → Web Phase A
Backend PR 4 available → Web Phase B
Backend PR 5 available → Web Phase C
Backend PR 6 available → Web Phase D
Backend PR 7 available → Web Phase E
```

Use a separate Codex task in the external Web repository. Follow that repository's own
framework, component, state-management, API-client, test, and design-system
conventions.

## Shared client rules

1. Treat backend settlement fields as authoritative.
2. Never enable a sale above `sellable_quantity`.
3. Client validation improves usability but does not replace backend enforcement.
4. Display unknown and degraded calendar states explicitly.
5. Preserve timestamps with offsets and display them in `Asia/Ho_Chi_Minh`.
6. Format money as actual VND.
7. Keep recommendations separate from recorded purchases.
8. Do not imply that recording a trade submits a broker order.
9. Do not infer missing historical fields.
10. Use stable API error codes rather than parsing English messages.

## Web Phase A — Trade recording and settlement state

### Prerequisite

Backend PR 3 is deployed or available to the Web development environment.

### Trade form

Extend the existing purchase/sale form with:

```text
account
symbol
execution date and time
side
quantity
price in VND
fee
tax
trade UID when supported
notes
```

Submit:

```json
{
  "account_id": 1,
  "symbol": "FPT.VN",
  "trade_date": "2026-07-18",
  "executed_at": "2026-07-18T10:15:00+07:00",
  "side": "buy",
  "quantity": 100,
  "price": 124500,
  "fee": 18675,
  "tax": 0
}
```

Use language such as “Record purchase” and “Record sale,” not “Execute order.”

### Position display

Display:

```text
total quantity
sellable quantity
unsettled quantity
settlement state
next estimated sellable time
calendar/calculation status
warnings
```

Suggested user states:

```text
Pending settlement
Partially sellable
Sellable
Settlement date unavailable
Calendar data degraded
```

### Sale behavior

- Set the quantity maximum to the backend `sellable_quantity`.
- Show unsettled quantity beside the sale form.
- Disable sale submission when sellable quantity is zero.
- Explain why the action is disabled.
- Refresh the position after successful trade recording.
- Handle stale snapshots by refreshing before final submission when practical.

Handle HTTP 409:

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

Update the form from the returned authoritative quantities rather than showing only a
generic failure toast.

### Lot details

Use:

```text
GET /api/v1/portfolio/positions/{symbol}/settlement?account_id=1&as_of=2026-07-18&cost_method=fifo
```

Show each acquisition lot with purchase time, remaining quantity, settlement state, and
estimated sellable time. Keep lot details collapsible if the main position view would
become crowded.

The response uses `calculation_status` at the position and lot levels, and each lot
contains `source_trade_id`, `acquired_at`, `remaining_quantity`, `unit_cost`,
`settlement_state`, `estimated_sellable_at`, `actual_sellable_at`, and `warnings`.
When the same symbol is held in multiple active accounts, the backend returns
`400 ambiguous_position_account` until the client supplies `account_id`.

## Web Phase B — Settlement-aware report

### Prerequisite

Backend PR 4 is deployed.

Display the backend-owned settlement context near the recommendation:

```text
current canonical action
settlement constraint
maximum sell quantity
sellable and unsettled quantities
next sellable time
reason codes translated into user-facing text
calendar warnings
```

Presentation requirements:

- Clearly distinguish recommendation from executable quantity.
- For partially sellable positions, separate guidance for sellable and unsettled shares.
- Do not reconstruct constraints from Vietnamese narrative text.
- Treat missing fields in old reports as “Not recorded,” not zero.
- Preserve the Vietnamese report narrative supplied by the backend.

## Web Phase C — Settlement-risk presentation

### Prerequisite

Backend PR 5 is deployed.

Display:

```text
survivability score
risk level
historical adverse/favorable movement range
ATR percentage
support and invalidation buffers
historical invalidation-touch frequency
sample count
data-quality state
warnings
policy version in technical details
```

The UI must describe these as historical estimates and a heuristic. Avoid probability
language when the backend field is not a calibrated probability.

Do not show a confident gauge for degraded or insufficient data. Prefer an explicit
limited-data state.

## Web Phase D — Recommendation linkage and alerts

### Prerequisite

Backend PR 6 is deployed.

### Record purchase from recommendation

Allow an eligible DecisionSignal detail view to open a prefilled record-purchase form.
Submit the source DecisionSignal ID with the trade. The user must still confirm price,
quantity, execution time, fees, and account.

Do not automatically create a trade by opening or accepting a recommendation.

### Settlement alerts

Display existing alert history for:

```text
position became partially sellable
position became sellable
thesis invalidated while unsettled
settlement risk increased
```

Use backend trigger IDs and timestamps for deduplication. Link to the affected position
or report when the API provides a stable identifier.

## Web Phase E — Settlement outcomes

### Prerequisite

Backend PR 7 is deployed.

Display signal outcomes separately from actual execution outcomes.

Useful fields:

```text
return at first sellable session
adverse movement before sellable
invalidation before sellable
fee/slippage-adjusted return
engine and policy versions
sample count
data quality
ambiguity flags
```

If daily-bar ambiguity is present, show that the application cannot determine whether
an event occurred before or after the intraday settlement time.

Never label a hypothetical signal outcome as the user's realized portfolio return.

## Client types

Keep types additive and nullable for compatibility. Suggested shapes:

```ts
type SettlementState =
  | 'unsettled'
  | 'partially_sellable'
  | 'sellable'
  | 'unknown';

interface PositionSettlementSummary {
  totalQuantity: number;
  sellableQuantity: number;
  unsettledQuantity: number;
  settlementState: SettlementState;
  nextSellableAt?: string | null;
  calculationStatus: 'confirmed' | 'degraded' | 'unknown';
  warnings: string[];
}
```

Use the external application's normal snake-case conversion layer rather than mixing API
wire names directly into components.

## Required frontend tests

- Record a purchase with an execution timestamp.
- Pending, partially sellable, sellable, degraded, and unknown states.
- Sale quantity above the locally displayed maximum.
- Backend 409 after the state changes between display and submission.
- Old API/report payload without settlement fields.
- Timezone display around midnight.
- VND formatting.
- Report constraint rendering independent of narrative text.
- Risk limited-data state.
- Recommendation-to-purchase confirmation.
- Signal versus execution outcome labels.

Add browser-level coverage for the purchase-to-pending-settlement flow and rejected
sale flow. Capture before/after screenshots according to the external repository's PR
requirements.

## External Web exit criteria

- The frontend never presents unsettled shares as sellable.
- Backend conflicts update the visible state clearly.
- Recommendation, recorded execution, and historical outcome remain distinct.
- Old records degrade gracefully.
- No authoritative financial calculation is duplicated in browser code.
