# Market Support Boundaries

The project supports A-shares, Hong Kong stocks, US stocks, Japan stocks, Korea stocks, Taiwan stocks, Vietnam stocks, and ETFs where providers support them. Coverage differs by market and field.

Vietnam stocks must use the explicit `.VN` marker, for example `FPT.VN` or `VNM.VN`. The marker is preserved at repository input and persistence boundaries so routing can identify the market as `vn`; the data adapter strips it only when calling the vnstock-backed provider. During an open Vietnamese session, the VN adapter merges historical daily bars with the current intraday snapshot before technical indicators are calculated, so the latest RSI, MACD, and moving-average analysis can reflect the active trading bar.

## Vietnam-focused defaults

New installations default to `STOCK_LIST=VNM.VN` and `REPORT_LANGUAGE=vi`. The default market review and daily market-context injection are disabled because a Vietnam market-review source is not yet supported; this prevents an A-share or other non-Vietnam market context from appearing in a Vietnam stock report. Set the corresponding environment variables explicitly to re-enable those optional features.

`ENABLED_MARKETS=vn` also prevents built-in providers for other markets from being used by the default `DataFetcherManager`. It is an allowlist, not a deletion: set `ENABLED_MARKETS=all` or a comma-separated subset such as `vn,us` to restore the required providers. Restart the backend after changing this setting so the default provider manager is rebuilt. The scheduled network-smoke workflow is disabled unless the GitHub Actions variable `NETWORK_SMOKE_ENABLED=true` is set; it remains available through manual dispatch.

For the minimal GitHub Actions Variables and Secrets required by this Vietnam-focused setup, copy the appropriate values from [`github-actions-vietnam.env.example`](github-actions-vietnam.env.example). The template contains placeholders only and must not be filled with real secrets before committing.

Vietnam market-phase handling uses the published HOSE weekday session baseline: 09:00-11:30, 13:00-14:45, and a 14:30-14:45 closing auction. Public-holiday closures are not yet modeled by a dedicated Vietnam exchange calendar, so scheduled runs should use `--force-run` when a manual run is intended on a local holiday.

Realtime quotes, daily bars, fundamentals, capital flow, chip distribution, news, announcements, social sentiment, and market breadth may not be available for every market. Unsupported fields should be reported as `not_supported`, not as generic failures.

Provider failure should degrade through the configured fallback chain. A single provider should not break the whole analysis flow unless fail-fast behavior is explicitly required. Use token-backed providers for scheduled or batch workloads and keep free providers as fallback when possible.
