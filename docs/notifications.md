# Notifications

The core analyzer can send generated reports through configured notification channels and can start Feishu or DingTalk stream bots without an HTTP server.

Configure channels in `.env`; `.env.example` is the canonical key inventory. Supported sender modules live in `src/notification_sender/` and include Feishu, DingTalk, Discord, Telegram, Slack, email, ntfy, Gotify, Pushover, PushPlus, ServerChan, custom webhooks, and other optional integrations.

Run the non-destructive configuration diagnostic with:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --check-notify"
```

Notification routing, quiet hours, and deduplication remain configuration-driven. Keep `NOTIFICATION_TIMEZONE=Asia/Ho_Chi_Minh` for the Vietnam profile. A failure in one optional channel must not invalidate a completed analysis or prevent other configured channels from running.

Stream-based bot clients start from `main.py` when their individual enable flags and credentials are configured. HTTP webhook callbacks are not available in this core-only build.

