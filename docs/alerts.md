# Local Alerts

Optional event monitoring remains available during scheduled CLI execution. Alert rules, trigger history, notification attempts, and cooldown state use the existing SQLite repositories so they remain available for a future database migration.

Enable the worker with `AGENT_EVENT_MONITOR_ENABLED=true` and configure its interval and rules through `.env.example`. The scheduler starts the worker in-process; there is no Web alert center or HTTP alert API in this build.

Alert evaluation and notification failures are isolated from the primary analysis task. Back up `data/stock_analysis_vn.db` before schema or migration work.

