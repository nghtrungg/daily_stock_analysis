# Market Support Boundaries

The project supports A-shares, Hong Kong stocks, US stocks, Japan stocks, Korea stocks, Taiwan stocks, Vietnam stocks, and ETFs where providers support them. Coverage differs by market and field.

Vietnam stocks must use the explicit `.VN` marker, for example `FPT.VN` or `VNM.VN`. The marker is preserved at repository input and persistence boundaries so routing can identify the market as `vn`; the data adapter strips it only when calling the vnstock-backed provider. During an open Vietnamese session, the VN adapter merges historical daily bars with the current intraday snapshot before technical indicators are calculated, so the latest RSI, MACD, and moving-average analysis can reflect the active trading bar.

## Vietnam-focused defaults

New installations default to `STOCK_LIST=VNM.VN` and `REPORT_LANGUAGE=vi`. The default market review and daily market-context injection are disabled because a Vietnam market-review source is not yet supported; this prevents an A-share or other non-Vietnam market context from appearing in a Vietnam stock report. Set the corresponding environment variables explicitly to re-enable those optional features.

`ENABLED_MARKETS=vn` also prevents built-in providers for other markets from being used by the default `DataFetcherManager`. It is an allowlist, not a deletion: set `ENABLED_MARKETS=all` or a comma-separated subset such as `vn,us` to restore the required providers. Restart the backend after changing this setting so the default provider manager is rebuilt. The scheduled network-smoke workflow is disabled unless the GitHub Actions variable `NETWORK_SMOKE_ENABLED=true` is set; it remains available through manual dispatch.

For the minimal GitHub Actions Variables and Secrets required by this Vietnam-focused setup, copy the appropriate values from [`github-actions-vietnam.env.example`](github-actions-vietnam.env.example). The template contains placeholders only and must not be filled with real secrets before committing.

Vietnam market-phase handling uses the published HOSE session baseline: 09:00-11:30, 13:00-14:45, and a 14:30-14:45 closing auction. A committed, versioned Vietnam calendar now distinguishes trading and settlement closures for covered years. Missing calendar years retain an explicit weekday-only fallback and settlement calculations report degraded coverage instead of claiming official accuracy. See [Vietnam Settlement Calendar And Schema Migrations](settlement-calendar.md).

Realtime quotes, daily bars, fundamentals, capital flow, chip distribution, news, announcements, social sentiment, and market breadth may not be available for every market. Unsupported fields should be reported as `not_supported`, not as generic failures.

Provider failure should degrade through the configured fallback chain. A single provider should not break the whole analysis flow unless fail-fast behavior is explicitly required. Use token-backed providers for scheduled or batch workloads and keep free providers as fallback when possible.

## Vietnam report data and presentation fallbacks

Vietnam valuation uses the vnstock company-profile ratio source for P/E and P/B instead of expecting those fields from the realtime quote. When either ratio is unavailable, the pipeline fills only the missing ratio with the mean of up to five distinct stored sessions. The report context marks this as `partial` and records the snapshot source and latest timestamp; it must not be presented as realtime data.

Buy Up/Sell Down uses trade-direction data from the current session when available. On weekends, holidays, or provider outages, the pipeline may reuse the latest stored session with confirmed coverage and labels it as a fallback with its `as_of` time. Foreign and proprietary net flow follow the same stale-data rule, but they are shown only when the optional `vnstock_data` integration supplied those feeds. Enable that integration with `ENABLE_VN_ADVANCED_FLOW=true`. A fallback snapshot is never relabeled as current-session flow.

Trade-direction flow is not chip distribution. Vietnam reports hide the chip-distribution block when no meaningful chip data exists instead of repeating an unavailable placeholder. If a real chip source becomes available, the block is rendered normally.

The Vietnamese report schema supports an evidence-gated sector health score, peer symbols, structured price-trigger scenarios, and a short closing summary. The model must return `score: null` with an unavailable explanation when the supplied sector evidence is insufficient; it must not infer a numerical score from ticker names alone. Decision scenarios are rendered as condition/action/invalidation rows so price guardrails remain scannable.
