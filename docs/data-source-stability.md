# Data Source Stability And Failure Handling

Token-backed providers are preferred for scheduled and batch workloads. Free providers are useful defaults but may be rate-limited or change upstream interfaces. A single provider failure should not break the whole analysis flow unless fail-fast behavior is explicitly required.

Use these data-quality terms consistently: `available`, `missing`, `not_supported`, `fallback`, `stale`, `estimated`, `partial`, and `fetch_failed`. Diagnostics should explain provider, fallback, stale data, and missing-field conditions without exposing secrets.

Provider changes should cover timeout, retry, fallback, field normalization, and diagnostic redaction.
