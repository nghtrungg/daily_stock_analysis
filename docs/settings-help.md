# Settings Help

This page explains the main Web settings groups. Configure at least one LLM provider before running AI analysis. Configure data providers for better quote stability, and configure notification channels if scheduled reports or alerts should be delivered.

## Model Settings

Supported routes include Anspire, AIHubMix, Gemini, Anthropic, OpenAI-compatible providers, DeepSeek, Tongyi Qianwen, Claude, and local compatible deployments depending on environment support. Do not expose API keys in screenshots, logs, or PR comments.

## Data Sources

Token-backed providers such as Tushare, TickFlow, and Longbridge are generally more stable for scheduled and batch workloads. Free providers are useful defaults but may be rate-limited or change upstream interfaces.

## Notifications

Configure one or more notification channels. Alert notifications use the alert route when `route_type="alert"` is passed through `NotificationService`.

## Scheduling

```bash
python main.py --schedule
python main.py --serve --schedule
```

After settings changes, verify the affected runtime path: local CLI, Docker, GitHub Actions, Web, Desktop, API, notifications, or provider fallback.
