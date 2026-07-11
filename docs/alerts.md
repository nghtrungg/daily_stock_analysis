# Realtime Alert Center

This document records the alert center baseline, data contract, phased implementation scope, compatibility boundaries, and rollback behavior.

Runtime alerts are scheduled by `src/services/alert_worker.py`. Rule evaluation reuses `src/services/alert_service.py` and the `EventMonitor` model from `src/agent/events.py`.

Configuration and runtime entry points: `AGENT_EVENT_MONITOR_ENABLED`, `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`, `AGENT_EVENT_ALERT_RULES_JSON`, schedule-mode `agent_event_monitor`, and `NotificationService.send(..., route_type="alert")`.

Supported executable rules are `price_cross`, `price_change_percent`, and `volume_spike`. Future placeholders such as `sentiment_shift`, `risk_flag`, and `custom` are not executable unless a later phase implements them.

`AGENT_EVENT_ALERT_RULES_JSON` remains a legacy source. The system must not automatically migrate, delete, overwrite, or rewrite user `.env` or Web settings.

Core entities are `alert_rule`, `alert_trigger`, `alert_notification`, and `alert_cooldown`. Diagnostics must not contain tokens, full webhook URLs, email passwords, bot secrets, cookies, or authorization headers.

Phase boundaries: P0 contract only; P1 Alert API MVP; P2 worker evaluates persistent plus legacy rules; P3 Web `/alerts`; P4 notification results and cooldown; P5 technical indicators; P6 watchlist/portfolio rules; P7 market-light rules; P8 user/deployment documentation.

Market rules use `target_scope=market` with targets `cn`, `hk`, `us`, `jp`, or `kr`. Supported market alert types are `market_light_status` and `market_light_score_drop`.

Rollback by reverting the relevant phase PR. Database tables created by earlier phases are not automatically deleted by code rollback; maintainers must decide whether to preserve or manually clean historical alert data.
