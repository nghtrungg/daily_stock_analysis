# Notification Capabilities

Daily Stock Analysis can send reports and alerts through enterprise WeChat, Feishu, DingTalk, Telegram, Discord, Slack, and email, depending on configuration.

Notification failures should not break the main analysis flow unless fail-fast behavior is explicitly required. Route-specific delivery should use `NotificationService.send(..., route_type=<route>)`. Alert delivery uses `route_type="alert"` and alert channel configuration.

Common variables include `WECHAT_WEBHOOK_URL`, `FEISHU_WEBHOOK_URL`, `DINGTALK_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `EMAIL_SENDER`, `EMAIL_PASSWORD`, and `NOTIFICATION_ALERT_CHANNELS`.

Delivery statuses describe notification delivery only: `sent`, `no_channel`, `partial_failed`, and `all_failed`. They must not be treated as analysis data-quality statuses. Diagnostics must redact tokens, full webhook URLs, email passwords, bot secrets, cookies, and authorization headers.
