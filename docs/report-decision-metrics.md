# Explainable Decision Metrics

Completed stock reports expose an additive `dashboard.decision_metrics` object. Older reports without this object remain valid and render with the legacy layout.

## Score breakdown

The final 0-100 composite score is decomposed into fixed point budgets:

| Component | Maximum points |
| --- | ---: |
| Trend | 30 |
| Momentum | 20 |
| Volume | 15 |
| Market | 15 |
| Fundamental | 20 |

The deterministic finalizer reconciles the component sum to the final score after action, phase, evidence, and market-data guardrails. Model-proposed rationales are retained when valid. When the model omits the breakdown, the finalizer allocates the guarded score across the fixed budgets and marks those rows as estimated. If volume is partial or unconfirmed, its score contribution is zero and the row is explicitly unavailable. The score is a composite decision indicator, not a probability.

The displayed score band comes from `src/schemas/decision_scale.py`. Scores 40 and 45 are both in the 40-59 watch band; 45 represents five additional composite points but does not cross an action threshold.

## Evidence confidence

Evidence confidence measures input coverage and reliability. It does not measure the probability that the price will rise or that a trade will win.

The fixed factor weights are OHLC 25%, trend 25%, volume 15%, market 15%, news 10%, and fundamentals 10%. The calculation reuses AnalysisContextPack block scores and the final OHLC/volume quality checks. A qualitative low or medium confidence guardrail caps the numeric result so the two report fields cannot contradict one another.

Each factor is rendered as available, limited, or missing with a short reason. Missing fundamentals or news lower confidence; they do not automatically become bearish evidence.

## Scenario outlook and risk matrix

The tactical outlook contains three mutually exclusive scenarios for the next 1-5 sessions:

- Downside.
- Sideways.
- Upside or technical rebound.

Probabilities are normalized to exactly 100%. The same canonical scenario objects render both the probability summary and the risk matrix, so conditions, targets, and actions cannot drift between sections. Targets use actual VND for `.VN` symbols. Conditions and targets must come from supplied support, resistance, volume, trading-plan, or daily-market evidence.

Scenario probabilities are labeled `uncalibrated` unless a future version supplies a versioned historical calibration with sample counts. They must not be described as backtested probabilities.

## Trade expectancy

Trade expectancy is available only when the existing long-plan validator accepts the Entry/SL/TP geometry. R:R is calculated deterministically for each displayed entry level against the one canonical final-invalidation stop; it is never shared across different entries.

The first implementation uses the upside scenario probability as a conservative long-trade win estimate and labels the source `scenario_estimate`. Expected Value is before fees, tax, and slippage:

```text
EV(R) = P(win) * Reward/Risk - P(loss) * 1R
```

For example, R:R 1:4 with a 32% win estimate produces `+0.60R`, not `-0.12R`. If the plan is invalid, win probability and EV are unavailable instead of being fabricated. If EV is negative, the report marks entry prices as a potential observation zone and leaves the buy order unactivated; price levels alone are not an active buy signal.

The existing DecisionSignal directional win rate is not reused as TP-before-SL probability because those measurement contracts are different.

## Compatibility and rollback

The contract is optional and stored inside the existing report dashboard JSON; it requires no SQLite migration. Full Markdown renders all details, while brief and WeChat reports show a compact summary.

Rollback consists of removing the `apply_decision_metrics` calls from both analysis paths in `src/core/pipeline.py` and the matching template blocks. Existing report and DecisionSignal records remain readable.
