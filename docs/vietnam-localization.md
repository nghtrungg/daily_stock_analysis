# Vietnam-Only Local Build

This profile keeps the Web and Desktop applications in English, generates stock-analysis reports in Vietnamese, limits new analysis to Vietnamese securities, and stores monetary values as actual VND. It is intended for a private local installation rather than a replacement for every legacy compatibility path in the upstream project.

## Local profile

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

- `STOCK_LIST` is the local watchlist. Use the explicit `.VN` suffix so routing is unambiguous.
- `ENABLED_MARKETS=vn` prevents new API and CLI analysis of foreign symbols. The bundled stock index is also Vietnam-only, and its upstream multi-market refresh is disabled.
- `REPORT_LANGUAGE=vi` selects Vietnamese prompts and report rendering; application navigation and settings remain English.
- `DATABASE_PATH` points to a new SQLite file. The original database is not migrated or deleted, so it remains available as a rollback copy.
- `NOTIFICATION_TIMEZONE` keeps notification quiet hours on Vietnam local time.
- `SCHEDULE_TIMES` contains all daily runs. `SCHEDULE_TIME` is the fallback used when that list is empty.
- `SCHEDULE_TIMEZONE` makes the schedule independent of the workstation's timezone.
- `TRADING_DAY_CHECK_ENABLED` skips Vietnam weekends. The current Vietnam calendar implementation is weekday-based and does not know official exchange holidays.
- `MARKET_REVIEW_ENABLED=false` and `DAILY_MARKET_CONTEXT_ENABLED=false` prevent the legacy foreign-index review from entering a Vietnam report.
- `MAX_WORKERS=1` keeps provider calls serial for a stable local workload. `ENABLE_VN_ADVANCED_FLOW=false` avoids requiring the optional licensed provider; the free order-flow path remains available.

Do not copy `.env.example` over an existing `.env` without first preserving its API keys and notification credentials.

## Vietnam schedule

The local schedule is anchored to the HOSE trading day:

- `09:20` is shortly after the opening call auction ends at 09:15, allowing the first report to use early continuous-session prices.
- `15:10` is after negotiated trading closes at 15:00, so the second report can use the complete daily session rather than an ATC-only snapshot.

See the [official HOSE trading schedule](https://staticfile.hsx.vn/Uploads/UploadDocuments/2372196/2.Thoi%20gian%20giao%20dich.pdf). Times are interpreted in `Asia/Ho_Chi_Minh` (ICT, UTC+7).

This schedule does not yet encode an authoritative exchange-holiday calendar. Check the [HOSE 2026 holiday notice](https://staticfile.hsx.vn/Uploads/UploadDocuments/2428610/20251209%20-%20HOSE%20-%20Notice%20of%20trading%20holiday%20schedule%20for%202026%20-%20PV.pdf) and stop or override scheduled runs on exchange holidays when necessary.

## Local run

Run repository commands through Command Prompt, use the repository virtual environment, and enable UTF-8:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& set \"SCHEDULE_ENABLED=false\"& .venv\Scripts\python.exe main.py --dry-run --stocks VNM.VN --no-notify --no-market-review"
```

The process-level schedule override above makes this a one-off validation even though the local `.env` enables scheduling. Remove `--dry-run` only when the configured data and LLM providers are ready for a real Vietnamese report.

Start the scheduled worker with:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --schedule --no-market-review"
```

Start only the API/Web service, without the scheduler, with:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --serve-only --host 127.0.0.1 --port 8000"
```

The database at `data/stock_analysis_vn.db` is created on first use. Back it up before schema changes. To inspect older data, stop the application and temporarily point `DATABASE_PATH` at a copied database; do not merge old foreign-market rows into the Vietnam database without an explicit migration and review.

The Desktop application identifies itself as **Daily Stock Analysis Vietnam**. Update checks and automatic installation are disabled in this local build, so an upstream desktop package cannot replace the localized runtime or its database. Restoring updates requires a separately reviewed release feed, signed artifacts, runtime-data backup tests, and an explicit rollback plan.

## Validation

Run deterministic backend checks before any provider-backed smoke test:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest -m \"not network\""
```

Validate the Web application separately:

```bat
cmd.exe /d /c "cd apps\dsa-web && npm ci && npm run lint && npm run build"
```

For Desktop changes, build the Web application first and then run:

```bat
cmd.exe /d /c "cd apps\dsa-desktop && npm install && npm run build"
```

Vietnam provider prices are normalized to actual VND before persistence and rendering. Portfolio currency defaults to `VND` and user-visible money uses Vietnamese locale formatting.

When `REPORT_LANGUAGE=vi`, the report schema still validates required fields and types, and the language gate rejects generated payloads containing Han script so the existing retry/fallback path can run. This provides structural and language-integrity confidence; a successful test run is not evidence that a forecast or investment conclusion is financially correct.

For Vietnam symbols, explicitly zero-relevance news results are excluded from both the LLM evidence prompt and database persistence. Analysis-history news and diagnostic snapshots are also sanitized before storage so legacy Han labels do not leak into the isolated local database.

## Safety boundaries

The following boundaries are intentional:

- Dormant foreign-market adapters, database compatibility fields, and Chinese-language compatibility mappings remain in the source tree. Removing them broadly could break provider fallbacks, historical-data parsing, tests, or upstream interoperability. `ENABLED_MARKETS=vn`, the Vietnam-only stock index, API/CLI guards, and the isolated database keep those paths inactive for this local profile.
- Desktop update checks and installation are disabled. Reusing the upstream release channel would risk replacing the local Web bundle, executable behavior, configuration, or database assumptions with an incompatible multi-market build.
- Vietnam market review is intentionally disabled. The legacy review flow depends on non-Vietnamese benchmark assumptions; enabling it without a dedicated VN-Index/HNX-Index implementation would produce misleading output.
- The active Portfolio page disables the legacy CITIC/CMB/Huatai CSV import card. Manual VND accounting remains available; CSV import should be re-enabled only after adding and validating a Vietnamese broker adapter.
- The two schedule times are based on HOSE sessions. HNX and UPCOM session nuances, exceptional exchange announcements, and official holiday-calendar automation are not modelled yet.
- Structural tests can verify currency normalization, schema completeness, language, routing, and rendering. They cannot guarantee live provider correctness, LLM factuality, or longitudinal investment accuracy. Evaluate confidence over a meaningful history of stored outcomes and backtests before relying on the reports for decisions.

If a future change proposes deleting legacy adapters, rewriting an existing database in place, re-enabling market review, or automating trades from generated advice, treat it as a separate high-risk migration with backups, compatibility tests, live-data validation, and a rollback plan.
