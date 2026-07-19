# Settlement-Aware Analysis Contract

This document records the additive backend report contract introduced by
settlement-aware trading PR 4. It applies only to Vietnam symbols with an explicit
`.VN` suffix.

## Context policy

The backend resolves settlement state on demand before either the legacy or Agent
analysis path runs.

- Position analysis submitted through
  `POST /api/v1/portfolio/positions/{symbol}/analysis` uses the selected account.
- General, CLI, and scheduled symbol analysis aggregates the same symbol across all
  active accounts. The LLM receives aggregate quantities and an account count, but
  not account IDs, names, cost basis, P&L, cash, or transaction details.
- If settlement context cannot be resolved, the snapshot is explicitly `unknown`.
  The backend does not infer an executable quantity from incomplete calendar data.

The frozen low-sensitivity snapshot version is `vn-settlement-v1`:

```json
{
  "snapshot_version": "vn-settlement-v1",
  "scope": "selected_account",
  "position_lifecycle": "open",
  "settlement_state": "partially_sellable",
  "total_quantity": 100,
  "sellable_quantity": 40,
  "unsettled_quantity": 60,
  "next_sellable_at": "2026-07-20T13:00:00+07:00",
  "maximum_sell_quantity": 40,
  "calendar_status": "confirmed",
  "warnings": []
}
```

The AnalysisContextPack includes this data in an authoritative `settlement` block.
The LLM may explain the values but must not calculate or replace quantities, dates,
or the maximum executable sale.

## Deterministic recommendation guardrail

The backend applies the guardrail after model generation and after existing phase,
market-context, trend, trade-plan, and canonical-action processing:

| Settlement state | Final behavior |
| --- | --- |
| No position | `sell` or `reduce` becomes `alert`; maximum is `0`. |
| `unsettled` | `sell` or `reduce` becomes `hold`; maximum is `0`. |
| `partially_sellable` | `sell` becomes `reduce`; any sale wording is capped at `sellable_quantity`. |
| `sellable` | Existing action semantics remain; sale wording is attached to the authoritative maximum. |
| `unknown` | `sell` or `reduce` becomes `alert`; no executable maximum is claimed. |

Canonical action wire values remain
`buy/add/hold/reduce/sell/watch/avoid/alert`. The final report adds optional fields:

- `settlement_constraint`
- `maximum_sell_quantity`
- `reason_codes`
- `settlement_snapshot`
- `dashboard.settlement_constraint`

Stable reason codes are:

- `settlement_no_position_to_sell`
- `settlement_unsettled_sale_blocked`
- `settlement_sale_quantity_capped`
- `settlement_calendar_unknown`

Authoritative fields are attached after model generation, replacing any model-supplied
settlement block. The final report schema is validated after the guardrail runs.
Historical reports without these fields remain readable.

## DecisionSignal persistence

DecisionSignal extraction preserves the final guarded action even when the sentiment
score would otherwise realign it. Metadata stores only the sanitized settlement
snapshot and reason codes. It does not store account identity, cost basis, P&L, cash,
or raw private portfolio context. A DecisionSignal remains a recommendation and is
never marked as an executed trade.

## API and external client compatibility

The report fields are additive and may be absent on historical records. External
clients should treat `maximum_sell_quantity=null` as unknown, not unlimited. A zero
value means that the backend has determined that no sale is currently executable.

The repository Web application under `apps/dsa-web/` is outside this roadmap and is
unchanged. External Web implementation should consume the additive report contract
without attempting to recalculate settlement.

## Rollback

Reverting PR 4 removes the context and recommendation guardrail while leaving PR 2
portfolio trade enforcement and PR 3 settlement APIs intact. Existing optional report
and DecisionSignal metadata remains readable and can be ignored by older code. This
rollback reopens the report-safety gap: reports may again suggest a sale that the
portfolio ledger correctly rejects.
