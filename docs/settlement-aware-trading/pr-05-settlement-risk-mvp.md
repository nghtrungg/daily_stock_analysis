# PR 5 — Deterministic Settlement-Risk MVP

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Start from
a baseline containing PRs 1 through 4.

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
PR 1 → PR 2 → PR 3 → PR 4 → PR 5 (this PR) → PR 6 → PR 7
```

## Purpose

Estimate whether an entry can tolerate the settlement window without presenting a
precise future-price prediction or an uncalibrated probability as fact.

## Prerequisites

- Calendar and settlement-window definition from PR 1.
- Report settlement context and deterministic guardrail from PR 4.
- A deterministic policy for support and invalidation levels. Do not use an
  LLM-invented stop price as the authoritative risk boundary.

## Scope

### 1. Service and schema

Create focused modules such as:

```text
src/services/settlement_risk_service.py
src/schemas/settlement_risk.py
```

Initial output:

```text
lookback_sessions
settlement_sessions
two_session_return_quantiles
three_session_return_quantiles
atr_pct
expected_adverse_move_pct
expected_favorable_move_pct
maximum_adverse_excursion_pct
gap_down_frequency
support_buffer_pct
invalidation_buffer_pct
historical_invalidation_touch_frequency
liquidity_quality
survivability_score
risk_level
survivability_status
sample_count
data_quality
warnings
policy_version
```

### 2. Deterministic calculations

- Normalize OHLCV input and reject NaN/infinite/invalid values.
- Use rolling session windows without look-ahead.
- Treat quantiles and touch frequency as historical estimates.
- Handle insufficient history, missing volume, suspension, and zero volume explicitly.
- Reuse deterministic technical support information where valid.
- Do not add bootstrap sampling in this PR.

### 3. Score policy

- Use one versioned policy object rather than scattered constants.
- Externalize only settings that users need to configure.
- Update `Config`, config registry, `.env.example`, and docs for new public settings.
- Renormalize available component weights when optional inputs are unavailable.
- Never replace missing components with fake neutral values.
- Label the score as a heuristic, not a guaranteed probability.

Do not include broad-market regime, upcoming-event risk, or news uncertainty until
their deterministic Vietnam-specific sources exist.

### 4. Analysis and API integration

- Attach the deterministic risk block to analysis results.
- Allow the LLM to explain but not alter it.
- Add optional report/API fields.
- Add guardrail reason codes when an otherwise positive setup has unsafe settlement
  risk.
- Preserve existing canonical actions.

## Likely files

- New risk service and schema
- Deterministic technical-level policy module if not already sufficient
- `src/config.py`
- `src/core/config_registry.py`
- `.env.example`
- Analysis context, pipeline, report, and API schemas
- Focused risk, report, config, and compatibility tests
- Risk methodology documentation
- `docs/CHANGELOG.md`

## Required tests

- Complete and insufficient history.
- Missing/zero volume.
- Large gaps, high volatility, and low volatility.
- Missing support or invalidation.
- NaN, infinity, non-positive prices, and abnormal bars.
- Deterministic repeated output.
- Weight renormalization.
- Low sample confidence.
- Guardrail interaction.
- Old reports without risk fields.

## Validation

- Run focused risk and report tests.
- Run config and API schema tests.
- Run backend validation.
- Confirm new settings and methodology are documented.

## Exit criteria

- Settlement risk is fully backend-calculated and reproducible.
- Missing evidence produces degraded output, not fabricated confidence.
- Entry-related reports expose a versioned heuristic and its limitations.

## Rollback

Risk fields remain optional. Reverting the feature must leave calendar, ledger
enforcement, and settlement guardrails operational.

## Out of scope

- Position sizing.
- Bootstrap estimates.
- Machine learning.
- Vietnam market-regime, corporate-event, or news-uncertainty scoring.
- Alerts, outcomes, and Web implementation.
