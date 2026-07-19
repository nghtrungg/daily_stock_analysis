# Settlement-Aware Trading Implementation Roadmap

## Purpose

This package turns the settlement-aware trading proposal into dependency-ordered,
self-contained implementation briefs for Daily Stock Analysis Vietnam.

The repository Web application is not part of this roadmap. Backend work must expose
stable additive API contracts for an external Web application. The external frontend
work is described separately in
[`external-web-implementation.md`](external-web-implementation.md).

## Recommended Codex task model

Use one Codex task for each backend PR. Do not paste the entire roadmap into one task.

Reasons:

- Each PR has a separate correctness boundary and validation gate.
- Later PRs depend on contracts established by earlier PRs.
- A smaller task makes review, rollback, and regression diagnosis more reliable.
- The task can be resumed if necessary, but it should remain scoped to one PR brief.

Start the next task only after the previous PR is merged or its final changes are
available in the new task's worktree. Do not implement dependent PRs in parallel.

The external Web work belongs in a separate task in the external Web repository. Its
first phase can begin after PR 3; later UI phases should wait for their corresponding
backend contracts.

## Common architecture rules

Every backend PR must preserve these rules:

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

## Execution order

```text
PR 1  Migration foundation and Vietnam calendar
  ↓
PR 2  Settlement-aware portfolio ledger
  ↓
PR 3  Portfolio API contract
  ↓
PR 4  Settlement-aware analysis and recommendation guardrail
  ↓
PR 5  Deterministic settlement-risk MVP
  ↓
PR 6  DecisionSignal linkage and settlement alerts
  ↓
PR 7  Settlement-aware outcome measurement
```

Implementation briefs:

1. [`pr-01-migration-and-calendar.md`](pr-01-migration-and-calendar.md)
2. [`pr-02-settlement-aware-ledger.md`](pr-02-settlement-aware-ledger.md)
3. [`pr-03-portfolio-api-contract.md`](pr-03-portfolio-api-contract.md)
4. [`pr-04-analysis-guardrail.md`](pr-04-analysis-guardrail.md)
5. [`pr-05-settlement-risk-mvp.md`](pr-05-settlement-risk-mvp.md)
6. [`pr-06-signal-linkage-and-alerts.md`](pr-06-signal-linkage-and-alerts.md)
7. [`pr-07-settlement-outcomes.md`](pr-07-settlement-outcomes.md)

Implemented contract references:

- [`portfolio-api-contract.md`](portfolio-api-contract.md) — PR 3 portfolio API.
- [`settlement-aware-analysis.md`](settlement-aware-analysis.md) — PR 4 analysis,
  report guardrail, and DecisionSignal metadata.
- [`../settlement-risk.md`](../settlement-risk.md) — PR 5 deterministic
  settlement-window risk methodology, score policy, report/API fields, and rollback.
- [`../settlement-signal-alerts.md`](../settlement-signal-alerts.md) — PR 6
  DecisionSignal-to-trade linkage, persistent settlement transitions, notification
  privacy, compatibility, and rollback.
- [`../settlement-outcomes.md`](../settlement-outcomes.md) — PR 7 versioned
  hypothetical and linked-execution outcomes, daily-bar ambiguity, API aggregates,
  scheduler behavior, compatibility, and rollback.

## Build now

PRs 1 through 4 form the first production milestone:

- Versioned and failure-aware Vietnam settlement calculations.
- Settlement-aware acquisition lots.
- Transactional rejection of sales above the sellable quantity.
- Additive API exposure for an external client.
- Deterministic report guardrails that prevent impossible sell instructions.

The milestone is not complete if enforcement exists only in the UI. Backend trade
recording and report generation must independently enforce the same contract.

## High priority after the first milestone

PRs 5 through 7 add:

- Deterministic settlement-window risk estimates.
- Traceability between a recommendation and a recorded trade.
- Settlement lifecycle alerts through the existing alert system.
- Settlement-aware historical outcome measurement.

## Low priority follow-up

These are useful only after PR 7 is stable:

- Calendar diagnostics and maintenance tooling.
- Manual settlement overrides for documented broker or VSDC delays.
- Restartable historical backfill tooling.
- Richer lot timelines and settlement-performance breakdowns.
- Direct links between external-Web position, alert, signal, and report views.

## Features blocked by prerequisites

| Capability | Required prerequisite |
| --- | --- |
| Position-sizing guidance | Deterministic invalidation prices, reliable available cash, concentration policy, and Vietnam trading-lot policy |
| Exact pre-settlement MAE or invalidation ordering | Reliable timestamped intraday OHLC data |
| Broad-market regime score | Dedicated Vietnam index and market-context implementation |
| Upcoming-event risk | Structured Vietnam corporate-event calendar |
| News uncertainty score | Deterministic and calibrated news classification |
| Bootstrap probability estimates | Sufficient clean historical observations and methodology validation |
| Full user-managed `TradePlan` entity | Proven lifecycle needs beyond `DecisionSignal`-to-trade linkage |

## Validation and handoff

Each PR task must:

- Inspect the current worktree and preserve unrelated user changes.
- Implement only the selected PR.
- Run the closest focused tests before broader validation.
- Follow the validation matrix in `AGENTS.md`.
- Update relevant durable docs and the flat `[Unreleased]` changelog for behavior,
  API, report, scheduler, notification, or configuration changes.
- Report changed files, validation, unverified paths, risks, and rollback.
- Avoid `git commit`, `git tag`, or `git push` without explicit confirmation.
