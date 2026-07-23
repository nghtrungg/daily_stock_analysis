# Daily Stock Analysis Vietnam

A private, CLI-first AI stock-analysis workspace for Vietnam securities. It fetches market data and news, generates schema-gated Vietnamese reports, stores analysis history in SQLite, and can deliver reports through configured bot and notification channels.

> This project supports research, not investment advice. Market data and AI-generated conclusions can be incomplete or wrong.

## What this build supports

- Vietnam watchlists with explicit symbols such as `VNM.VN`, `MBB.VN`, `FPT.VN`, and `HPG.VN`
- Technical, fundamental, news, and LLM-assisted analysis with Vietnamese reports
- SQLite-compatible local analysis history at `data/stock_analysis_vn.db`, with signed per-run report projections into the shared Supabase dashboard
- Bot commands, stream clients, and notification delivery
- One-time analysis, backtesting, and weekday scheduling in `Asia/Ho_Chi_Minh`

The repository intentionally has no Web frontend, HTTP API, Desktop application, or Docker packaging. The inherited non-Vietnam market-review flow also remains disabled.

## Quick start

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and configure an LLM provider plus a `.VN` watchlist.
3. Run a no-notification dry run before requesting a real report.

```dotenv
STOCK_LIST=VNM.VN,MBB.VN
ENABLED_MARKETS=vn
REPORT_LANGUAGE=vi
DATABASE_PATH=./data/stock_analysis_vn.db
```

On this Windows workspace, use Command Prompt, UTF-8, and the repository virtual environment:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --dry-run --stocks VNM.VN --no-notify --no-market-review"
```

Start the local scheduler with:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --schedule --no-market-review"
```

## Operating boundaries

- The schedule is weekday-based and does not model official exchange holidays.
- Back up `data/stock_analysis_vn.db` before schema changes or migration work.
- Keep `ENABLED_MARKETS=vn`, explicit `.VN` symbols, actual VND values, and `REPORT_LANGUAGE=vi`.
- Stream-based Feishu and DingTalk bots can run with the scheduler without an HTTP server. HTTP webhook endpoints are not part of this core-only build.

## Documentation

- [Core usage and Vietnam-local boundaries](docs/vietnam-localization.md)
- [Bot commands](docs/bot-command_EN.md)
- [Notification configuration](docs/notifications.md)
- [LLM provider configuration](docs/llm-providers.md)
- [Change history](docs/CHANGELOG.md)
- [Shared Supabase report integration](docs/supabase-integration.md)

## Validation

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest -m \"not network\""
```

## License

[MIT License](LICENSE)
