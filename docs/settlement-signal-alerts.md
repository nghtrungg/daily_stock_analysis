# DecisionSignal Trade Links And Settlement Alerts

This document records settlement-aware trading PR 6 for the Vietnam local build.
Recommendation assets and executed trades remain separate; the new sidecar makes a
purchase traceable to the recommendation that sourced it.

## Trade linkage contract

`POST /api/v1/portfolio/trades` accepts nullable
`source_decision_signal_id`. When supplied, the backend validates and writes the trade
and link in one portfolio transaction.

- The trade must be a `buy`; sales cannot cite an entry recommendation.
- The signal must exist, be active, use market `vn`, and have action `buy` or `add`.
- Signal and trade symbols must resolve to the same explicit `.VN` identity.
- One trade can have only one `source_recommendation` link.
- A DecisionSignal action is never changed to `EXECUTED`.
- Requests that omit the field remain valid.

Trade create and list payloads expose nullable `source_decision_signal_id` and
`link_type`. Deleting a trade deletes its sidecar link but does not delete the source
DecisionSignal.

## Settlement lifecycle evaluation

The existing `AlertWorker` evaluates Vietnam positions when
`AGENT_EVENT_MONITOR_ENABLED=true`. It observes the on-demand deterministic portfolio
snapshot; it does not mark lots sellable or repair portfolio state.

The worker recognizes these transitions:

| Event | Transition |
| --- | --- |
| `position_became_partially_sellable` | Sellable quantity moves from zero to a positive value below total quantity |
| `position_became_sellable` | Sellable quantity reaches total open quantity |
| `thesis_invalidated_while_unsettled` | A linked source signal becomes invalidated while unsettled quantity remains |
| `settlement_risk_increased` | The latest stored deterministic settlement-risk level moves to a higher rank under the same policy version |

The first observation establishes a baseline and does not notify. The latest
account/symbol observation is stored in `settlement_alert_states`, so unchanged
worker runs and process restarts do not repeat an event. Closed positions reset the
baseline before a later reopening.

Settlement risk is read from the newest DecisionSignal-bound analysis history for the
symbol that contains the versioned PR 5 `settlement_risk` block. Newest is determined
by the immutable analysis-history creation time, not by mutable DecisionSignal status
updates. A policy-version change establishes a new baseline instead of comparing ranks
across incompatible policies. Missing risk data does not fabricate a level and does
not erase the last known baseline.

Scheduled observations resolve their snapshot date explicitly in
`Asia/Ho_Chi_Minh`, independent of the host operating-system timezone.

## Existing alert infrastructure

Each transition uses a system-owned `settlement_lifecycle` rule with stable target
`account:<id>:symbol:<symbol>`. Trigger history, 24-hour cooldown state, alert-route
notification dispatch, per-channel attempts, and diagnostic sanitization reuse the
existing alert repositories and worker methods.

Notifications contain only the event type, numeric account ID, `.VN` symbol, public
settlement quantities/state, linked signal ID, and versioned risk level/policy. They
exclude owner identity, account name, broker, cash, cost basis, P&L, notes, raw report
content, credentials, and notification endpoints.

A notification-channel exception is recorded as a sanitized failed attempt and does
not roll back the position baseline, trade, settlement projection, or other alert
processing.

## Runtime and compatibility

No new environment variable is introduced. The existing schedule and runtime
scheduler conventions register `AlertWorker`; settlement evaluation is therefore
controlled by the existing event-monitor enable flag and polling interval.

All API fields and tables are additive. Historical trades without links, historical
reports without settlement risk, and alert history without settlement diagnostics
remain readable.

The repository Web application under `apps/dsa-web/` is unchanged. External clients
may show the optional linkage but must not infer execution by mutating the
DecisionSignal action.

## Rollback

Disable alert evaluation before reverting if an older worker would not understand
system settlement rules. Reverting PR 6 may leave:

- `decision_signal_trade_links`
- `settlement_alert_states`
- system-owned `settlement_lifecycle` alert rules
- associated trigger, notification, and cooldown history

Older code ignores the additive link and state tables. Existing alert history remains
ordinary history. The tables should be removed only through an explicit,
operator-approved cleanup after confirming the data is no longer needed.
