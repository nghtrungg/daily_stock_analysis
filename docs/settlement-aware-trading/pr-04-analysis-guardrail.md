# PR 4 — Settlement-Aware Analysis and Recommendation Guardrail

## Session usage

Use this file as the complete scope for one Codex task and one reviewable PR. Start from
a baseline containing PRs 1 through 3.

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
PR 1 → PR 2 → PR 3 → PR 4 (this PR) → PR 5 → PR 6 → PR 7
```

## Purpose

Make reports and DecisionSignals compatible with the user's actual settlement state.
This PR completes the first production milestone.

## Prerequisites

- Settlement-aware portfolio calculations from PR 2.
- Stable API and serialization contracts from PR 3.

## Scope

### 1. Backend-owned settlement context

Build a low-sensitivity context:

```text
position_lifecycle
settlement_state
total_quantity
sellable_quantity
unsettled_quantity
next_sellable_at
maximum_sell_quantity
calendar_status
warnings
```

Account-specific portfolio analysis uses the selected account. Scheduled or general
symbol analysis must use an explicitly documented aggregation policy across active
accounts and must not expose per-account financial details unnecessarily.

### 2. Analysis context integration

- Add the settlement block to the existing analysis context pack.
- Provide it to both legacy and Agent analysis paths.
- Preserve current data-quality and sanitization behavior.
- Freeze a versioned public settlement snapshot needed for reproducibility.
- Do not persist raw private portfolio context merely for debugging.

### 3. Deterministic recommendation guardrail

Add a guardrail alongside existing phase and market-context guardrails.

Rules:

```text
unsettled:
  sell/reduce is not executable
  maximum_sell_quantity = 0
  final action becomes hold or alert with a reason code

partially sellable:
  reduce/sell may apply only to sellable quantity
  unsettled quantity receives a separate warning

sellable:
  existing action semantics apply

unknown:
  do not claim an executable sale quantity
  expose degraded/unknown status explicitly
```

Keep canonical `buy/add/hold/reduce/sell/watch/avoid/alert` wire values. Add fields such
as:

```text
settlement_constraint
maximum_sell_quantity
reason_codes
```

### 4. Report and LLM contract

- The LLM may explain the backend block.
- The LLM must not calculate or return authoritative settlement quantities or dates.
- Attach deterministic fields after model generation.
- Validate the final report after the guardrail runs.
- Keep new report fields optional for historical compatibility.
- Preserve Vietnamese-language validation.

### 5. DecisionSignal compatibility

Persist the final guarded action and a sanitized settlement snapshot or versioned reason
metadata. Do not add replacement action values or mark a recommendation as an executed
trade.

## Likely files

- `src/services/analysis_context_builder.py`
- `src/schemas/analysis_context_pack.py`
- A focused settlement decision guardrail module under `src/`
- `src/core/pipeline.py`
- `src/analyzer.py`
- `src/schemas/report_schema.py`
- `src/services/decision_signal_extractor.py`
- API analysis/history schemas if needed
- Report, context, guardrail, and signal tests
- Relevant report/settlement documentation
- `docs/CHANGELOG.md`

## Required tests

- No position.
- Fully unsettled position.
- Partially sellable position.
- Fully sellable position.
- Unknown calendar coverage.
- Impossible `sell` and `reduce` model outputs.
- Quantity mismatch in generated text or structured data.
- Legacy and Agent paths.
- Vietnamese language validation.
- Old reports without settlement fields.
- DecisionSignal extraction after guardrail.
- Sanitized persisted context.

## Validation

- Run focused context-pack, report-schema, pipeline, and DecisionSignal tests.
- Run backend validation.
- Confirm report API examples match the external-Web contract.
- No in-repository Web build is required because `apps/dsa-web/` must remain unchanged.

## Exit criteria

- No persisted report or DecisionSignal instructs selling more than the sellable
  quantity.
- Deterministic values cannot be overridden by model output.
- Historical reports remain readable.

## Rollback

New report fields are optional. Reverting the guardrail leaves existing settlement
snapshots as ignored additive data. Document that rollback reopens the report-safety
gap even though portfolio trade enforcement remains active.

## Out of scope

- Settlement-risk score.
- Position sizing.
- Signal-to-trade linkage.
- Alerts, outcomes, and Web implementation.
