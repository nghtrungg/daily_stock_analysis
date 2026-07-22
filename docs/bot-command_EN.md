# Bot Commands

The `bot/` package provides unified commands for stream-based messaging clients. It remains part of the core-only build; no HTTP webhook server is included.

## Runtime

`main.py` starts Feishu and DingTalk stream clients when their individual enable flags and credentials are configured. Scheduled mode keeps the process alive for incoming commands. Outgoing Discord, Telegram, Slack, email, Feishu, DingTalk, and other notification senders remain available through `src/notification_sender/`.

## Commands

The dispatcher registers these command handlers:

- `/help`: show available commands.
- `/status`: show runtime and LLM configuration readiness.
- `/analyze <symbol>`: analyze an explicit stock symbol such as `VNM.VN`.
- `/batch <symbols>`: submit multiple symbols.
- `/history`: query stored analysis history.
- `/market`: market-related summary behavior retained by the bot layer; Vietnam legacy market review remains disabled.
- `/ask` and `/chat`: agent-assisted questions using stored context.
- `/research`: agent research workflow.
- `/strategies`: list or select analysis strategies.

Exact availability depends on credentials and enabled agent features. The Vietnam profile rejects foreign symbols for new analysis.

## Structure

- `bot/models.py`: normalized messages and responses.
- `bot/dispatcher.py`: parsing, rate limiting, command routing, and shared context.
- `bot/commands/`: command implementations.
- `bot/platforms/`: stream and platform adapters.

Platform adapters should normalize incoming messages before dispatch. Commands should reuse core services and repositories rather than duplicating analysis or persistence logic. Errors returned to users must be safe and must not expose secrets or raw provider responses.

## Configuration

Use `.env.example` as the canonical inventory for bot, stream-client, LLM, notification, rate-limit, and administrator settings. Run `python main.py --check-notify` before enabling real delivery.

