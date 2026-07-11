# Changelog

All notable changes to this project should be documented here.

## [Unreleased]

- [improvement] Add an `ENABLED_MARKETS` provider allowlist with a Vietnam-only default and make scheduled network smoke opt-in.
- [docs] Add a Vietnam-focused GitHub Actions Variables and Secrets template for scheduled analysis.
- [improvement] Make Vietnam the default analysis experience with `VNM.VN`, Vietnamese reports, and non-Vietnam market-review context disabled by default.
- [feature] Add MFI(14) and CMF(20) OHLCV-derived money-flow indicators to reports, explicitly distinguishing them from investor-category order-flow data.
- [feature] Fetch and expose disclosed Vietnam ownership records through vnstock/KBS when available, without mislabelling them as daily net buying or selling.
- [fix] Derive the MA20 support/resistance role from the current close and prevent report narratives from treating a confirmed close above MA20 as overhead resistance.
- [fix] Require source-backed company-specific causal links before reports present broad policy themes, including public investment, as earnings catalysts.
- [fix] Normalize Vietnam daily OHLC bars and cached report snapshots when vnstock uses VND but the live quote uses thousand VND, preventing mixed-unit price reports.
- [fix] Localize Vietnam report status, decision-signal chrome, and stability fallback advice in Vietnamese.

- [docs] Translate Markdown documentation and collaboration instructions into English.
- [feature] Recognize `.VN` tickers and route Vietnamese stocks through the vnstock-backed provider with intraday active-bar merging.
- [improvement] Localize Vietnamese `.VN` stock prompts and news search queries.
- [improvement] Add Vietnam midday-break prompt handling, Vietnamese markdown dashboard labels, and time-aware VN news search terms.
- [fix] Normalize vnstock daily bars to the shared provider frame contract so Vietnam analysis reaches technical indicators.
- [improvement] Use the published HOSE weekday session baseline for Vietnam market-phase handling instead of an unavailable exchange-calendars code.
- [chore] Remove unused Claude Code compatibility governance checks.
- [fix] Localize Vietnamese decision-action labels so `.VN` report rendering completes.

## Historical Notes

Earlier changelog entries were maintained in Chinese. This file now keeps an English summary-oriented format so maintainers and agents can read the project history consistently.

When adding new entries, use the flat `[Unreleased]` format:

```markdown
- [type] description
```

Allowed `type` values are `feature`, `improvement`, `fix`, `docs`, `test`, and `chore`. Maintainers may reorganize entries into categorized release sections at release time.
