# Settlement-Aware Portfolio API

This document records the additive backend contract introduced by settlement-aware
portfolio API PR 3. All routes remain under `/api/v1/portfolio`.

## Record a trade

`POST /trades` retains the required `trade_date` field and accepts an optional
`executed_at` ISO timestamp. A timestamp without an offset is interpreted in
`Asia/Ho_Chi_Minh`. A timestamp with an offset is converted to that timezone and must
resolve to `trade_date`; otherwise the API returns `400 validation_error`.

Vietnam trades require an explicit `.VN` symbol and use VND. Omitting `executed_at`
preserves the old request contract and invokes the documented PR 2 execution-time
inference.

PR 6 adds optional `source_decision_signal_id`. It is valid only for a purchase and
must reference an active Vietnam `buy` or `add` DecisionSignal with the same normalized
symbol. Missing signals, symbol or market mismatches, non-entry actions, inactive
signals, and duplicate source links are rejected. Omitting the field preserves the
legacy request. Successful create and list responses add nullable
`source_decision_signal_id` and `link_type="source_recommendation"` fields.

## Snapshot settlement fields

Each item in `GET /snapshot` account `positions` may include:

- `position_lifecycle`
- `settlement_state`
- `sellable_quantity`
- `unsettled_quantity`
- `next_sellable_at`
- `settlement_calculation_status`
- `settlement_warnings`

Clients must treat these fields as additive. Missing or null fields on historical
payloads mean “not recorded,” not zero.

## Position settlement details

`GET /positions/{symbol}/settlement` accepts optional `account_id`, `as_of`, and
`cost_method` query parameters. If the symbol is held in multiple active accounts,
omitting `account_id` returns `400 ambiguous_position_account`. A missing or closed
position returns `404 not_found`.

The response contains the authoritative total, sellable, and unsettled quantities,
position settlement state, next sellable timestamp, calculation status, warnings, and
active acquisition lots. Each lot includes only its source trade ID, acquisition time,
remaining quantity, unit cost, settlement timestamps and state, calculation status,
and warnings.

## Position analysis handoff

`POST /positions/{symbol}/analysis` passes the selected account's settlement state,
sellable and unsettled quantities, next sellable timestamp, calculation status, and
warnings to the analysis pipeline. PR 4 freezes those fields into the versioned
low-sensitivity report snapshot described in
[`settlement-aware-analysis.md`](settlement-aware-analysis.md). The queued task and
public task events do not expose the private portfolio context.

## Sale conflicts

A sale above total held quantity retains the existing `409 portfolio_oversell`
contract. A sale within total holdings but above the currently sellable quantity
returns:

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

The values are calculated transactionally by the backend and should replace stale
client state.

## Rollback

All response fields and the detail endpoint are additive. Reverting this API layer
does not remove PR 2 settlement sidecars or derived cache fields; older clients remain
able to use `trade_date` and the pre-existing snapshot fields. PR 6 link rows may
remain after rollback and are ignored by older code.
