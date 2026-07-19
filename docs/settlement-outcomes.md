# Settlement-Aware Outcome Measurement

PR 7 adds a versioned outcome sidecar without replacing the legacy directional
DecisionSignal outcome or backtest tables.

## Outcome identities

- `signal` measures a hypothetical Vietnam entry. It never implies that the user
  traded. `vn-next-session-open-v1` enters at the next stored trading session's open.
- `execution` exists only for a `buy` `PortfolioTrade` connected through
  `DecisionSignalTradeLink`. `vn-linked-trade-price-v1` uses the recorded trade price
  and fee.

Rows are unique by signal, outcome type, signal/trade identity, outcome engine
version, and entry-policy version. The current engine is
`vn-settlement-outcome-v1`. Repeated API or scheduler runs reuse a completed row;
`force=true` updates the same versioned row.

## Forward-only and settlement contract

The entry session is the anchor and is excluded from all horizon returns. T+1, T+2,
T+5, T+10, and T+20 use deterministically date-ordered bars after that anchor.
The first-sellable return uses the daily close on the settlement date calculated by
the frozen Vietnam calendar and `vn-equity-t2-2022-08-29` policy. Execution outcomes
prefer the settlement provenance already frozen on the linked purchase.

The signal entry price comes from a future entry bar, not from an original intraday
signal's eventual closing price. This prevents the prior signal-level anchor-close
method from introducing look-ahead into the hypothetical execution policy.

Corporate-action treatment remains identical to the stored provider bars. PR 7 does
not add a second adjustment layer.

## Daily-bar limitations

Daily OHLC cannot show whether a low, high, or invalidation breach on the T+2 session
happened before or after 13:00 ICT. Therefore every daily-bar result includes:

- `daily_bar_mae_mfe_proxy`
- `t2_intraday_ordering_ambiguous`

MAE and MFE are conservative extrema through the sellable session. A stop breach on
an earlier session is `true`; a breach found only on the sellable session is `null`
with `invalidation_ordering_ambiguous`. The API never describes these proxies as
exact intraday ordering.

## Costs and data quality

Hypothetical signal outcomes subtract a documented 0.30% round-trip fee estimate and
0.20% round-trip slippage estimate. Linked executions use the recorded entry fee,
plus a 0.15% estimated exit fee and 0.10% exit slippage. These are measurement
assumptions, not broker invoices.

Calendar or price gaps remain visible through `data_quality`, `unavailable_reason`,
and ambiguity flags. Missing values stay `null`; aggregates include sample counts and
an `unavailable_reason` instead of substituting zero.

## API and scheduler

- `POST /api/v1/decision-signals/settlement-outcomes/run`
- `GET /api/v1/decision-signals/settlement-outcomes`
- `GET /api/v1/decision-signals/settlement-outcomes/stats`

The runtime scheduler registers `settlement_outcomes_after_market` every 30 minutes.
It evaluates only after the Vietnam regular session and is idempotent. Correct
portfolio settlement remains calculated on demand and does not depend on this job.

Aggregates expose settlement failure rate, first-sellable median return, adverse
movement, unambiguous invalidation rate, net win rate, profit factor when both gains
and losses exist, expected return, return per settlement-risk point, and breakdowns
by survivability, liquidity, and guarded action.

## Compatibility and rollback

Legacy `decision_signal_outcomes`, backtest APIs, reports, and historical records are
unchanged. Disable the scheduler consumer before reverting PR 7 code. The additive
`settlement_outcomes` table may remain; older versions ignore it.
