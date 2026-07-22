# Vietnam-Only Core Build

This repository is a local Python analyzer for Vietnam securities. It intentionally excludes Web, HTTP API, Desktop, Docker, and cloud-deployment surfaces.

## Required profile

Keep these values in `.env`:

```dotenv
STOCK_LIST=VNM.VN,MBB.VN
ENABLED_MARKETS=vn
STOCK_INDEX_REMOTE_UPDATE_ENABLED=false
REPORT_TYPE=full
REPORT_LANGUAGE=vi
DATABASE_PATH=./data/stock_analysis_vn.db
NOTIFICATION_TIMEZONE=Asia/Ho_Chi_Minh
SCHEDULE_ENABLED=true
SCHEDULE_TIME=15:10
SCHEDULE_TIMES=09:20,15:10
SCHEDULE_TIMEZONE=Asia/Ho_Chi_Minh
SCHEDULE_RUN_IMMEDIATELY=false
TRADING_DAY_CHECK_ENABLED=true
MARKET_REVIEW_ENABLED=false
DAILY_MARKET_CONTEXT_ENABLED=false
MAX_WORKERS=1
ENABLE_VN_ADVANCED_FLOW=false
```

Use explicit `.VN` suffixes, actual VND values, and Vietnamese report output. The bundled symbol index is stored at `src/data/stocks.index.json`.

## Run locally

Use Command Prompt, the repository virtual environment, and UTF-8:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& set \"SCHEDULE_ENABLED=false\"& .venv\Scripts\python.exe main.py --dry-run --stocks VNM.VN --no-notify --no-market-review"
```

Start the scheduled worker with:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --schedule --no-market-review"
```

The two default local times are shortly after the HOSE opening auction and after the trading session. The calendar is weekday-based and does not encode official exchange holidays.

## Storage and future migration

SQLite remains the source of truth at `data/stock_analysis_vn.db`. Back it up before schema changes. A future Supabase migration should be a separate, tested data migration that preserves analysis history, decision signals, portfolio records, timestamps, and actual-VND semantics; removing the old SQLite file is not part of that migration until reconciliation succeeds.

## Validation

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest -m \"not network\""
```

Provider and LLM tests establish software behavior only; they do not validate investment conclusions.

## Report evidence and decision guardrails

Vietnam reports apply deterministic checks before an LLM result is saved or rendered:

- A daily candle is usable only when all OHLC values are positive and satisfy `low <= open/close <= high`. The pipeline never substitutes the previous close for a missing opening price.
- An invalid real-time candle may be replaced only by a valid same-day daily candle. If no valid replacement exists, the report may show the observed close but must suppress candle patterns, support/resistance conclusions, and selling-pressure claims. The final action is downgraded to `watch`, the score is neutralized, and confidence becomes low.
- Intraday cumulative volume is not compared with a completed prior session. Completed-session volume is admitted as evidence when a daily source is available, when two same-day sources agree within 20%, or when a single-source value is not an extreme outlier. A source conflict or an unconfirmed ratio below 0.2x or above 5x is displayed as a limitation and excluded from demand, selling-pressure, and money-flow conclusions.
- `latest_news`, short-term catalysts, and short-term risk alerts require a verifiable `YYYY-MM-DD` publication date inside the configured news window. Older financial results can remain only as explicitly historical fundamental context.
- The report separates tactical evidence (1–5 sessions), medium-term evidence (1–3 months), and fundamental evidence (6–12 months). MA200, ownership, and long-term operating data cannot independently determine the tactical action.
- The action taxonomy is explicit: `sell` means exit the full position; `reduce` means trim exposure; `hold` means keep the position without adding; `watch` means wait for confirmation; and `avoid` means do not initiate a position. Aggregate reports count `reduce` separately from `sell`.
- Entry prices are conditional zones. The final report requires price acceptance, a reversal/structure confirmation, completed-session volume confirmation, and a non-deteriorating VN-Index before treating the zone as actionable.
- Scores are composite model indicators, not calibrated probabilities. R:R is derived as `(target - entry) / (entry - stop)` from the displayed levels and is accompanied by that formula in the report.

Rollback is localized: remove the calls to the market-data and report-evidence guardrails from `src/core/pipeline.py` to restore the previous decision flow. The raw quote and context snapshot remain available for diagnosis; no database migration is involved.
