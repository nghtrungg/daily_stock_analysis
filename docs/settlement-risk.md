# Vietnam Settlement-Window Risk Heuristic

## Purpose

The settlement-risk block estimates whether a new Vietnam equity entry historically
tolerated the period before acquired shares became sellable. It is deterministic,
versioned, and calculated by the backend. It is a heuristic based on historical daily
bars, not a prediction, probability of profit, or guarantee that a future price path
will resemble the sample.

The current policy version is `vn-settlement-risk-v1`. It applies only to explicit
`.VN` symbols and does not introduce market-regime, corporate-event, news, machine
learning, bootstrap, or position-sizing inputs.

## Inputs and validation

The service consumes daily OHLCV already loaded by the analysis pipeline. It does not
make a second provider request. Bars are sorted by session and limited to the latest
configured lookback.

A bar is rejected when:

- any OHLC price is missing, non-finite, or non-positive;
- `high` is below another OHLC value; or
- `low` is above another OHLC value.

Duplicate session rows are reduced to the first validated observation and reported
with `duplicate_session_rejected`.

Invalid volume is treated as missing because price-based estimates can still be
calculated. Missing, partial, and zero-volume history produce explicit warning codes.
A zero-volume flat bar is also flagged as a possible suspension session.

The existing deterministic trend analyzer supplies the nearest support level. When it
is absent or not below the latest close, support and invalidation components are
omitted. The service never uses an LLM-generated stop price as an authoritative
boundary.

## Historical estimates

All percentages use daily bars in chronological order and rolling windows with no
look-ahead beyond each historical entry window:

- `two_session_return_quantiles` and `three_session_return_quantiles` are empirical
  close-to-close return quantiles.
- `expected_adverse_move_pct` is the absolute fifth-percentile return over the
  configured settlement window, floored at zero.
- `expected_favorable_move_pct` is the 95th-percentile return over that window,
  floored at zero.
- `maximum_adverse_excursion_pct` is the largest observed decline from an entry close
  to the lowest low inside its settlement window.
- `gap_down_frequency` is the share of sessions whose open is below the previous
  close.
- `atr_pct` is the latest 14-session average true range divided by the latest close.
- `support_buffer_pct` is the distance from the latest close to deterministic support.
- `invalidation_buffer_pct` extends that distance by `0.5 × ATR%`, as defined by the
  versioned policy.
- `historical_invalidation_touch_frequency` is the share of historical settlement
  windows whose low touched the relative invalidation buffer.

These are historical estimates. Field names do not imply calibrated confidence
intervals or probabilities.

## Score policy

The score combines only available components:

| Component | Base weight |
| --- | ---: |
| Expected adverse move | 30% |
| Maximum adverse excursion | 20% |
| Historical invalidation survival | 25% |
| Support coverage | 15% |
| Liquidity quality | 10% |

If support, invalidation, or volume evidence is unavailable, its component is omitted
and the remaining weights are renormalized to sum to one. Missing evidence is never
replaced with a neutral score.

The score is labeled as a `survivability_score` heuristic:

- `70–100`: `survivable` / low risk;
- `40–69.99`: `caution` / medium risk;
- below `40`: `unsafe` / high risk.

At least 30 rolling settlement-window observations are required before the status can
be actionable. Smaller samples return `insufficient_history` and
`low_sample_confidence`, even if partial metrics can be calculated. At least 80
observations are required for `data_quality=good`.

An otherwise positive `buy` or `add` result is deterministically downgraded to
`watch` only when the estimate is actionable and `unsafe`. The report receives the
reason code `settlement_risk_unsafe_entry`. The LLM may explain the attached block but
cannot change its values or restore the blocked entry action.

## Report and API contract

Analysis records add an optional `settlement_risk` object at the report root and in
`dashboard.settlement_risk`. Public analysis and history responses also expose the
same optional block through `report.summary.settlement_risk`.

All fields remain optional for compatibility. Historical reports that predate PR5
remain readable and serialize `settlement_risk` as `null` in typed API summaries.

## Configuration

```dotenv
SETTLEMENT_RISK_ENABLED=true
SETTLEMENT_RISK_LOOKBACK_SESSIONS=120
```

`SETTLEMENT_RISK_LOOKBACK_SESSIONS` accepts 30 through 500 sessions. The score
thresholds, weights, ATR period, and invalidation rule are policy constants rather
than public settings so one policy version remains reproducible.

## Limitations

- Daily bars cannot determine whether an invalidation level was touched before a
  favorable move within the same session.
- Volume availability does not provide order-book depth or guaranteed executable
  liquidity.
- Suspension warnings are inferred from zero-volume flat bars and are not an official
  exchange-status feed.
- Corporate actions must already be normalized by the upstream data path.
- The score excludes Vietnam market regime, event calendars, and deterministic news
  classification until dedicated sources exist.

## Rollback

Set `SETTLEMENT_RISK_ENABLED=false` to stop producing new risk blocks. Reverting the
feature leaves the Vietnam calendar, settlement-aware portfolio ledger, and PR4 sale
guardrails operational. Existing reports containing the optional block remain
readable.
