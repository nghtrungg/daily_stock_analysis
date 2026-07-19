# PR 6 — DecisionSignal Linkage and Settlement Alerts

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Start from
a baseline containing PRs 1 through 5.

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
PR 1 → PR 2 → PR 3 → PR 4 → PR 5 → PR 6 (this PR) → PR 7
```

## Purpose

Keep recommendations and actual executions separate but traceable, then notify users
about important settlement transitions through the existing alert infrastructure.

## Prerequisites

- Settlement-aware trades and quantities.
- Guarded DecisionSignals.
- Deterministic settlement-risk output.

## Scope

### 1. Signal-to-trade sidecar

Add:

```text
DecisionSignalTradeLink
- signal_id
- trade_id
- link_type
- created_at
```

Requirements:

- A purchase remains a `PortfolioTrade`.
- A DecisionSignal remains a recommendation asset.
- Validate matching normalized `.VN` symbols.
- Reject missing, incompatible, or non-entry source signals clearly.
- Prevent duplicate links.
- Do not introduce `EXECUTED` as a replacement DecisionSignal action.

Extend the existing trade API with an optional source DecisionSignal ID. Keep old
requests valid.

### 2. Settlement lifecycle events

Generate system events such as:

```text
position_became_partially_sellable
position_became_sellable
thesis_invalidated_while_unsettled
settlement_risk_increased
```

Use the existing alert repository, trigger history, cooldowns, notification routing,
and sanitization. Do not create another alert engine or notification gateway.

### 3. Transition detection

- Compare current deterministic state with the latest recorded relevant state.
- Make evaluation idempotent across repeated worker runs.
- Deduplicate unchanged alerts across process restarts.
- Keep each account/symbol target identity stable.
- Include only low-sensitivity public fields in notifications.
- One notification-channel failure must not break settlement or portfolio processing.

### 4. Runtime integration

Use the existing alert worker/background-task conventions. The worker observes and
notifies; it does not mark lots sellable or correct portfolio state.

## Likely files

- `src/storage.py`
- A focused repository/service for signal-trade links
- `src/services/portfolio_service.py`
- `api/v1/schemas/portfolio.py`
- `api/v1/endpoints/portfolio.py`
- Existing alert repository, service, worker, contracts, and notification paths
- Signal-link and alert tests
- Alert, API, settlement, and notification documentation
- `docs/CHANGELOG.md`

## Required tests

- Valid and invalid signal-to-trade links.
- Symbol mismatch.
- Duplicate link.
- Legacy trade request without signal ID.
- Partial and full sellability transitions.
- Repeated worker execution.
- Process-restart deduplication through persistent state.
- Risk increase and thesis-invalidated cases.
- Notification failure isolation.
- Sanitization of alert payloads.
- Existing alert rules and cooldown behavior.

## Validation

- Run focused portfolio, DecisionSignal, alert-worker, and notification tests.
- Run API schema tests.
- Run backend validation.
- Confirm no `apps/dsa-web/` changes.

## Exit criteria

- Users can trace a recorded purchase to its source recommendation.
- Recommendation and execution remain separate records.
- Settlement lifecycle notifications are persistent, deduplicated, and non-blocking.

## Rollback

Reverting may leave link rows and settlement alert history in additive tables. Older
code must ignore them safely. Disable new alert evaluation before rollback if older code
would misinterpret new alert types.

## Out of scope

- Full mutable `TradePlan` entity.
- Broker execution.
- Outcome measurement, position sizing, and Web implementation.
