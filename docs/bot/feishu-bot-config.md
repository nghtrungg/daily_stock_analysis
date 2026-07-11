# Feishu Bot Configuration

Configure Feishu notifications by creating a Feishu bot webhook and setting `FEISHU_WEBHOOK_URL`. If signature verification is enabled, configure the supported signing secret as well.

Feishu delivery is one notification channel. A Feishu failure should not break the main analysis flow when other channels are available. Logs and diagnostics must not print the full webhook URL or signing secret.
