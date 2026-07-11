# AnalysisContextPack Contract

`AnalysisContextPack` is an internal contract for organizing the data used by stock analysis. It clarifies whether data is available, missing, unsupported, fallback, stale, estimated, partial, or failed to fetch without exposing private raw payloads.

Existing context surfaces include `storage.get_analysis_context()`, `enhanced_context`, `analysis_history.context_snapshot`, Agent executor message context, and Agent orchestrator `AgentContext`. Preserve `analysis_history.context_snapshot.enhanced_context.date` for backtest compatibility.

The internal schema defines `PACK_VERSION = "1.0"`, `AnalysisSubject`, `AnalysisContextItem`, `AnalysisContextBlock`, `DataQuality`, and `AnalysisContextPack`. Timestamps should be ISO 8601 where datetime semantics are required.

Field quality statuses are `available`, `missing`, `not_supported`, `fallback`, `stale`, `estimated`, `partial`, and `fetch_failed`. These describe input data quality, not whether analysis, alerts, backtests, or notifications succeeded.

`AnalysisContextBuilder` is an assembler, not a fetcher. It builds from already available pipeline artifacts and must not call providers, SearchService, Agent tools, databases, or fetchers by itself.

Public surfaces should expose only low-sensitive overviews. Do not expose full pack raw values, full news text, raw trend/chip/fundamental payloads, API keys, tokens, cookies, full webhook URLs, email passwords, secrets, authorization values, sendkeys, or license keys.

No DB migration is required for the pack overview. Old history without pack overview or data quality should continue to render. Rollback removes pack prompt summary, overview, and data-quality integration through code revert.
