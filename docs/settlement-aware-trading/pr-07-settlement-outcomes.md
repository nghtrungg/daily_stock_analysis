# PR 7 — Settlement-Aware Outcome Measurement

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Start from
a baseline containing PRs 1 through 6.

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
PR 1 → PR 2 → PR 3 → PR 4 → PR 5 → PR 6 → PR 7 (this PR)
```

## Purpose

Measure historical recommendations using settlement-aware horizons without assuming
that every recommendation became an actual purchase.

## Prerequisites

- Versioned settlement calendar and policy.
- Guarded DecisionSignals with frozen settlement/risk context.
- Signal-to-trade linkage for distinguishing hypothetical and actual outcomes.

## Scope

### 1. Separate outcome types

Keep these concepts distinct:

```text
signal outcome:
  hypothetical performance under an explicit entry policy

execution outcome:
  performance derived from recorded PortfolioTrade events
```

Do not infer that a signal was executed unless a trade link exists.

### 2. Versioned settlement outcome sidecar

Add a sidecar keyed by signal and calculation version rather than overloading every
legacy outcome row.

Suggested fields:

```text
signal_id
engine_version
entry_policy_version
calendar_version
settlement_policy_version
anchor_date
estimated_settlement_date
estimated_first_sellable_at
return_t1_pct
return_t2_pct
return_first_sellable_pct
return_t5_pct
return_t10_pct
return_t20_pct
mae_before_sellable_pct
mfe_before_sellable_pct
invalidation_before_sellable
operationally_executable
estimated_fee_pct
estimated_slippage_pct
net_return_first_sellable_pct
data_quality
ambiguity_flags_json
created_at
updated_at
```

### 3. No-look-ahead evaluation

- Use only information available at the original signal timestamp.
- Define the hypothetical entry policy explicitly and version it.
- Use the calendar version appropriate to the evaluation contract.
- Order bars deterministically and exclude the anchor bar where the existing horizon
  contract requires forward-only data.
- Keep corporate-action handling aligned with existing provider behavior.

### 4. Daily-bar limitation

Daily OHLC cannot determine whether an event on the sellable session occurred before or
after an intraday settlement time. Until reliable intraday bars exist:

- Mark T+2 intraday ordering as ambiguous.
- Use a documented conservative daily-bar proxy.
- Do not claim exact pre-settlement MAE or exact invalidation ordering.

### 5. Aggregates

Add versioned metrics with explicit sample counts:

```text
settlement failure rate
median return at first sellable session
average adverse movement before sellable
invalidation breach rate before sellable
net win rate
profit factor when supported
expected return
expected return divided by settlement-risk score
performance by survivability bucket
performance by liquidity bucket
performance by guarded action
```

Return `null` and an unavailable reason rather than fake zero values.

### 6. Idempotent execution

Add explicit API execution and an idempotent after-market background job through the
existing runtime scheduler conventions. Repeated runs must update or reuse the same
versioned outcome rather than duplicate it.

## Likely files

- `src/storage.py`
- DecisionSignal outcome repository/service modules
- `src/core/backtest_engine.py`
- `src/services/backtest_service.py` where shared calculations apply
- Runtime scheduler integration
- API outcome schemas/endpoints
- Outcome, backtest, scheduler, API, and migration tests
- Backtesting methodology documentation
- `docs/CHANGELOG.md`

## Required tests

- No recommendation-to-execution assumption.
- No look-ahead bars.
- Holiday-aware first sellable session.
- Missing calendar or prices.
- T+2 ambiguity flag.
- Daily-bar MAE/MFE proxy.
- Fee and slippage application.
- Strategy and engine version separation.
- Repeated API and scheduler execution.
- Empty and insufficient samples.
- Aggregate sample counts and unavailable metrics.
- Actual execution outcomes use linked trades only.

## Validation

- Run focused outcome, backtest, repository, and scheduler tests.
- Run backend validation.
- Compare a small hand-calculated fixture set.
- Document all daily-bar limitations and calculation versions.

## Exit criteria

- Historical signal and execution outcomes remain distinct.
- First-sellable-session metrics are calendar-aware and reproducible.
- Repeated calculation is idempotent.
- Intraday uncertainty is visible rather than hidden.

## Rollback

Versioned sidecar rows may remain after code rollback. Older outcome and backtest APIs
must continue functioning. Disable the new scheduler job before reverting its consumer
code.

## Out of scope

- Intraday data acquisition.
- Exact pre-settlement intraday ordering.
- Machine learning, position sizing, and Web implementation.
