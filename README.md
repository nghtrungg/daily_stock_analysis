# Daily Stock Analysis Vietnam

A private, Vietnam-focused AI stock-analysis workspace. It analyzes Vietnam securities, creates Vietnamese decision reports, and provides English Web and Desktop management surfaces.

> This local build is for research and operational support, not investment advice. Market data and AI-generated conclusions can be incomplete or wrong; make independent decisions and consult a licensed adviser where appropriate.

## What this build supports

- Vietnam watchlists using explicit symbols such as `VNM.VN`, `MBB.VN`, `FPT.VN`, and `HPG.VN`
- Vietnam-market data, technical analysis, relevant news, and Vietnamese schema-gated decision reports
- Actual-VND storage and presentation, portfolio tracking, historical reports, alerts, and backtest outcome measurement
- A local FastAPI/Web workspace and a packaged Desktop application named **Daily Stock Analysis Vietnam**
- Optional scheduled runs at 09:20 and 15:10 in `Asia/Ho_Chi_Minh`, plus configured notification delivery

The project intentionally does not enable the inherited multi-market analysis routes, upstream stock-index refresh, automatic Desktop updates, or legacy market review. The latter uses non-Vietnam benchmarks and must not be used as a Vietnam market summary.

## Quick start

1. Create a virtual environment, install dependencies, then copy `.env.example` to `.env`.
2. Configure at least one supported LLM provider and a watchlist. Keep `.VN` suffixes so symbol routing is unambiguous.
3. Run a no-notification dry run before requesting a real report.

```dotenv
STOCK_LIST=VNM.VN,MBB.VN
ENABLED_MARKETS=vn
REPORT_LANGUAGE=vi
DATABASE_PATH=./data/stock_analysis_vn.db
```

On this Windows workspace, run commands through Command Prompt with the repository virtual environment:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --dry-run --stocks VNM.VN --no-notify --no-market-review"
```

Remove `--dry-run` only after the data and LLM providers are ready. The default local profile enables scheduling, so use the documented one-off command above for safe validation.

## Run modes

```bat
:: Start the Vietnam-time scheduler
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --schedule --no-market-review"

:: Start only the local API/Web service
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --serve-only --host 127.0.0.1 --port 8000"
```

Open `http://127.0.0.1:8000` for the Web workspace and `http://127.0.0.1:8000/docs` for API documentation. Legacy `--webui` options remain aliases for the service options.

## Operating boundaries

- The schedule is weekday-based. Check HOSE holiday announcements and stop or override automated runs when needed.
- The local database is isolated at `data/stock_analysis_vn.db`; back it up before schema changes. Do not mix legacy foreign-market rows into it without an explicit migration.
- Vietnam advanced foreign/proprietary flow is optional. The free order-flow path works without the optional licensed provider.
- Desktop update checks and automatic installation are disabled to prevent an upstream package from replacing the localized runtime or data assumptions.

## Documentation

- [Vietnam local profile, schedule, validation, and rollback boundaries](docs/vietnam-localization.md)
- [Environment variables and provider configuration](docs/full-guide_EN.md)
- [Deployment guidance](docs/DEPLOY_EN.md)
- [Alert behavior](docs/alerts.md)
- [Prediction measurement baseline](docs/decision-signals.md)
- [Change history](docs/CHANGELOG.md)

## Validation

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest -m \"not network\""
cmd.exe /d /c "cd apps\dsa-web && npm ci && npm run lint && npm run build"
cmd.exe /d /c "cd apps\dsa-desktop && npm install && npm run build"
```

## License

[MIT License](LICENSE)
