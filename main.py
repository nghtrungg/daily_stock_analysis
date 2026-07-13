# -*- coding: utf-8 -*-
"""
===============================================
Daily Stock Analysis - main orchestration entry
===============================================

Responsibilities:
1. Coordinate the end-to-end stock analysis workflow.
2. Run a deliberately small worker pool.
3. Isolate failures so one symbol does not stop the batch.
4. Provide the command-line interface.

Examples:
    python main.py              # Run once
    python main.py --debug      # Enable debug logging
    python main.py --dry-run    # Fetch data without AI analysis

Trading principles used by the analysis:
- Avoid chasing extended prices; do not buy when deviation exceeds 5%.
- Trade with the trend when MA5 > MA10 > MA20.
- Prefer efficient setups with concentrated ownership.
- Prefer lower-volume pullbacks to MA5/MA10 support.
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from dotenv import dotenv_values
from src.config import setup_env

_INITIAL_PROCESS_ENV = dict(os.environ)
setup_env()

# Proxy configuration is controlled by USE_PROXY and disabled by default.
# GitHub Actions always skips local proxy configuration.
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    # Local development proxy; configure PROXY_HOST and PROXY_PORT in .env.
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

if os.getenv("DSA_PACKAGED_ALPHASIFT_IMPORT_PROBE") == "1":
    import importlib
    import sys

    try:
        importlib.import_module("alphasift.dsa_adapter")
    except Exception as exc:
        print(f"ERROR: packaged AlphaSift adapter import failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("OK: packaged AlphaSift adapter import succeeded")
    sys.exit(0)

import argparse
import logging
import sys
import time
import uuid
from datetime import date, datetime, timezone, timedelta

from src.webui_frontend import prepare_webui_frontend_assets
from src.config import get_config, Config
from src.logging_config import setup_logging
from src.services.stock_list_parser import split_stock_list
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.services.market_symbol_utils import is_vn_market_symbol


logger = logging.getLogger(__name__)
_RUNTIME_ENV_FILE_KEYS = set()
_PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})


def _get_active_env_path() -> Path:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return Path(env_file)
    return Path(__file__).resolve().parent / ".env"


def _is_public_bind_host(host: str) -> bool:
    return (host or "").strip().lower() in _PUBLIC_BIND_HOSTS


def _warn_if_public_webui_without_auth(host: str) -> None:
    if not _is_public_bind_host(host):
        return

    from src.auth import is_auth_enabled

    if is_auth_enabled():
        return
    logger.warning(
        "WEBUI_HOST=%s binds the Web UI to a public interface while "
        "ADMIN_AUTH_ENABLED=false. Keep this service behind a trusted network "
        "boundary or enable admin authentication before exposing it.",
        host,
    )


def _resolve_web_service_bind(args: argparse.Namespace, config: Config) -> Tuple[str, int]:
    """Resolve the effective Web/API bind address from CLI first, then config."""
    host = args.host if args.host is not None else (config.webui_host or "127.0.0.1")
    port = args.port if args.port is not None else config.webui_port
    return host, port


def _read_active_env_values() -> Optional[Dict[str, str]]:
    env_path = _get_active_env_path()
    if not env_path.exists():
        return {}

    try:
        values = dotenv_values(env_path)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Failed to read configuration file %s; keeping current environment: %s", env_path, exc)
        return None

    return {
        str(key): "" if value is None else str(value)
        for key, value in values.items()
        if key is not None
    }


_ACTIVE_ENV_FILE_VALUES = _read_active_env_values() or {}
_RUNTIME_ENV_FILE_KEYS = {
    key for key in _ACTIVE_ENV_FILE_VALUES
    if key not in _INITIAL_PROCESS_ENV
}

# setup_env() already ran at import time above.
_env_bootstrapped = True


def _bootstrap_environment() -> None:
    """Load .env and apply optional local proxy settings.

    Guarded to be idempotent so it can safely be called from lazy-import
    paths used by API / bot consumers.
    """
    global _env_bootstrapped
    if _env_bootstrapped:
        return

    from src.config import setup_env

    setup_env()

    if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
        proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
        proxy_port = os.getenv("PROXY_PORT", "10809")
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url

    _env_bootstrapped = True


def _setup_bootstrap_logging(debug: bool = False) -> None:
    """Initialize stderr-only logging before config is loaded.

    File handlers are deferred until ``config.log_dir`` is known (via the
    subsequent ``setup_logging()`` call) so that healthy runs never create
    log files in a hard-coded directory.
    """
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)


def _setup_runtime_logging(log_dir: str, debug: bool = False) -> bool:
    """Switch to configured logging, falling back to console on file I/O errors."""
    try:
        setup_logging(log_prefix="stock_analysis", debug=debug, log_dir=log_dir)
        return True
    except OSError as exc:
        logger.warning(
            "File logging initialization failed; falling back to console output. "
            "Log directory %r cannot be written or created: %s. "
            "The official Docker entrypoint repairs default mounted-directory permissions. "
            "If this persists, check --user, read-only mounts, rootless Docker, or NFS write restrictions.",
            log_dir,
            exc,
        )
        return False


def _get_stock_analysis_pipeline():
    """Lazily import StockAnalysisPipeline for external consumers.

    Also ensures env/proxy bootstrap has run so that API / bot consumers
    that never call ``main()`` still get ``USE_PROXY`` applied.
    """
    _bootstrap_environment()
    from src.core.pipeline import StockAnalysisPipeline as _Pipeline

    return _Pipeline


class _LazyPipelineDescriptor:
    """Descriptor that resolves StockAnalysisPipeline on first attribute access."""

    _resolved = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        if self._resolved is None:
            self._resolved = _get_stock_analysis_pipeline()
        return self._resolved


class _ModuleExports:
    StockAnalysisPipeline = _LazyPipelineDescriptor()


_exports = _ModuleExports()


def __getattr__(name: str):
    if name == "StockAnalysisPipeline":
        return _exports.StockAnalysisPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reload_env_file_values_preserving_overrides() -> None:
    """Refresh `.env`-managed env vars without clobbering process env overrides."""
    global _RUNTIME_ENV_FILE_KEYS

    latest_values = _read_active_env_values()
    if latest_values is None:
        return

    managed_keys = {
        key for key in latest_values
        if key not in _INITIAL_PROCESS_ENV
    }

    for key in _RUNTIME_ENV_FILE_KEYS - managed_keys:
        os.environ.pop(key, None)

    for key in managed_keys:
        os.environ[key] = latest_values[key]

    _RUNTIME_ENV_FILE_KEYS = managed_keys


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Daily Stock Analysis for the Vietnam market',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python main.py                         # Run once
  python main.py --debug                 # Enable debug logging
  python main.py --dry-run               # Fetch data without AI analysis
  python main.py --stocks VNM.VN,MBB.VN  # Analyze selected Vietnam symbols
  python main.py --no-notify             # Disable notifications
  python main.py --check-notify          # Validate notification configuration only
  python main.py --single-notify         # Notify after each completed symbol
  python main.py --schedule              # Enable scheduled execution
  python main.py --market-review         # Run market review only (legacy markets)
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Fetch data without running AI analysis'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='Comma-separated stock symbols (overrides configuration)'
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='Disable notifications'
    )

    parser.add_argument(
        '--check-notify',
        action='store_true',
        help='Validate notification channels without sending a message'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='Notify after each completed symbol instead of sending one batch notification'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='Worker count (defaults to the configured value)'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Enable daily scheduled execution'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='Do not run immediately when the scheduler starts'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='Run market review only (legacy markets)'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='Skip market review analysis'
    )

    parser.add_argument(
        '--force-run',
        action='store_true',
        help='Run even when the market calendar reports a non-trading day'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='Start the Web management interface'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='Start the Web service without automatic analysis'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='Start FastAPI and also execute the analysis task'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='Start FastAPI without automatic analysis'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='FastAPI port (WEBUI_PORT, default 8000)'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=None,
        help='FastAPI bind address (WEBUI_HOST, default 127.0.0.1)'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='Do not save analysis context snapshots'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='Backtest historical analysis results'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='Backtest one stock symbol only'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='Backtest evaluation window in trading days (uses configuration by default)'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='Recalculate backtests even when results already exist'
    )

    return parser.parse_args()


def _compute_trading_day_filter(
    config: Config,
    args: argparse.Namespace,
    stock_codes: List[str],
) -> Tuple[List[str], Optional[str], bool]:
    """
    Compute filtered stock list and effective market review region (Issue #373).

    Returns:
        (filtered_codes, effective_region, should_skip_all)
        - effective_region None = use config default (check disabled)
        - effective_region '' = all relevant markets closed, skip market review
        - should_skip_all: skip entire run when no stocks and no market review to run
    """
    force_run = getattr(args, 'force_run', False)
    if force_run or not getattr(config, 'trading_day_check_enabled', True):
        return (stock_codes, None, False)

    from src.core.trading_calendar import (
        get_market_for_stock,
        get_open_markets_today,
        compute_effective_region,
    )

    open_markets = get_open_markets_today()
    filtered_codes = []
    for code in stock_codes:
        mkt = get_market_for_stock(code)
        if mkt in open_markets or mkt is None:
            filtered_codes.append(code)

    if config.market_review_enabled and not getattr(args, 'no_market_review', False):
        effective_region = compute_effective_region(
            getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
        )
    else:
        effective_region = None

    should_skip_all = (not filtered_codes) and (effective_region or '') == ''
    return (filtered_codes, effective_region, should_skip_all)


def _run_market_review_with_shared_lock(
    config: Config,
    run_market_review_func: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    from src.core.market_review_lock import (
        release_market_review_lock,
        try_acquire_market_review_lock,
    )

    lock_token = try_acquire_market_review_lock(config)
    if lock_token is None:
        logger.warning("A market review is already running; skipping this duplicate request")
        return None

    try:
        params = dict(kwargs)
        params.setdefault("config", config)
        return run_market_review_func(**params)
    finally:
        release_market_review_lock(lock_token)


def _is_multi_market_region(region: str) -> bool:
    normalized = str(region or "").strip().lower()
    if not normalized:
        return False
    if normalized == "both":
        return True
    parts = {item.strip() for item in normalized.split(",") if item.strip()}
    return len(parts) > 1


def _refresh_stock_index_cache_for_analysis(config: Config) -> None:
    """Best-effort stock-index refresh for CLI/scheduled analysis paths."""
    try:
        from src.services.stock_index_remote_service import (
            refresh_remote_stock_index_cache,
            settings_from_config,
        )

        result = refresh_remote_stock_index_cache(settings_from_config(config))
        if result.refreshed:
            logger.info("[stock-index] Refreshed the stock-index cache before analysis: %s", result.cache_path)
        elif result.error:
            logger.debug("[stock-index] Refresh did not complete; continuing with the local index: %s", result.error)
    except Exception as exc:  # noqa: BLE001 - stock index freshness must not block analysis.
        logger.warning("[stock-index] Refresh failed; continuing analysis with the local index: %s", exc)


def _prime_daily_market_context(
    config: Config,
    pipeline: Any,
    *,
    region: str,
    no_market_review: bool,
    allow_generate: bool,
    force_refresh: bool = False,
    target_date: Optional[date] = None,
    return_full_report: bool = False,
    require_current_query_match: bool = False,
) -> Union[str, Tuple[str, str]]:
    """Load/reuse the run's market context, avoiding unbounded background generation."""
    if no_market_review or not region:
        return ("", "") if return_full_report else ""

    from src.services.daily_market_context import DailyMarketContextService

    if not _is_multi_market_region(region):
        service = getattr(pipeline, "_daily_market_context_service", None)
        if service is None:
            service = DailyMarketContextService(db_manager=pipeline.db)
            pipeline._daily_market_context_service = service
    else:
        service = DailyMarketContextService(db_manager=pipeline.db)

    get_context_kwargs = {
        "region": region,
        "config": config,
        "notifier": pipeline.notifier,
        "analyzer": pipeline.analyzer,
        "search_service": pipeline.search_service,
        "force_refresh": force_refresh,
        "allow_generate": allow_generate,
        "persist_market_review_history": False,
        "target_date": target_date,
        "require_query_id_match": require_current_query_match,
    }
    current_query_id = getattr(pipeline, "query_id", None)
    if isinstance(current_query_id, str) and current_query_id.strip():
        get_context_kwargs["current_query_id"] = current_query_id

    context = service.get_context(**get_context_kwargs)
    if context is None:
        return ("", "") if return_full_report else ""

    # Runtime context generation is preload-only and must not replace the full
    # market review run, except the query-scoped fallback after that run fails.
    if context.source != "analysis_history" and not (
        require_current_query_match and context.source == "market_review_runtime"
    ):
        return ("", "") if return_full_report else ""

    summary = str(getattr(context, "summary", ""))
    full_report = str(getattr(context, "full_report", "") or "")
    if return_full_report:
        return summary, full_report
    return summary


def _can_reuse_market_context_for_review(summary: str, region: str) -> bool:
    if not summary:
        return False
    normalized = str(region or "").strip().lower()
    if normalized == "both":
        return False
    parts = {item.strip() for item in normalized.split(",") if item.strip()}
    return len(parts) <= 1


def _resolve_daily_market_context_market(market: str, normalized_region: str) -> str:
    if "," not in normalized_region:
        return market
    parts = [item.strip() for item in normalized_region.split(",") if item.strip()]
    if parts and all(item in {"jp", "kr"} for item in parts):
        return parts[0]
    return market


def _resolve_daily_market_context_target_date(
    region: str,
    current_time: datetime,
) -> date:
    normalized_region = str(region or "cn").strip().lower()
    market = normalized_region if normalized_region in {"cn", "hk", "us", "jp", "kr"} else "cn"

    from src.core.trading_calendar import get_effective_trading_date

    return get_effective_trading_date(
        _resolve_daily_market_context_market(market, normalized_region),
        current_time=current_time,
    )


def _market_review_report_text(review_result: Any) -> str:
    if review_result is None:
        return ""
    report = getattr(review_result, "report", None)
    if isinstance(report, str):
        return report
    return review_result if isinstance(review_result, str) else ""


def _save_reused_market_review_report(
    notifier: Any,
    market_report: str,
    *,
    config: Config,
    trigger_source: str,
    region: str,
) -> None:
    body = str(market_report or "").strip()
    if not body:
        return
    title = (
        "# 🎯 Market Review"
        if str(getattr(config, "report_language", "zh")).strip().lower() == "en"
        else "# 🎯 Tổng quan thị trường"
    )
    if not any(
        body.startswith(item)
        for item in (
            "# 🎯 Tổng quan thị trường",
            "# 🎯 Market Review",
            "# 🎯 \u5927\u76d8\u590d\u76d8",  # Legacy stored-report compatibility.
        )
    ):
        body = f"{title}\n\n{body}"
    try:
        date_str = datetime.now().strftime('%Y%m%d')
        report_filename = f"market_review_{date_str}.md"
        filepath = notifier.save_report_to_file(body, report_filename)
        logger.info(
            "[MarketReview] component=market_review action=save_reused_report "
            "trigger_source=%s region=%s path=%s",
            trigger_source,
            region,
            filepath,
        )
    except Exception as exc:
        logger.warning("Failed to save the market review from reusable context: %s", exc)


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
    *,
    raise_errors: bool = False,
) -> bool:
    """
    Execute the complete workflow (stock analysis and optional market review).

    This is the scheduler's main task entry point.
    """
    # Import pipeline modules outside the broad try/except so that import-time
    # failures propagate to the caller instead of being silently swallowed.
    from src.core.market_review import run_market_review
    from src.core.pipeline import StockAnalysisPipeline

    try:
        _refresh_stock_index_cache_for_analysis(config)

        # Issue #529: Hot-reload STOCK_LIST from .env on each scheduled run
        if stock_codes is None:
            config.refresh_stock_list()

        # Issue #373: Trading day filter (per-stock, per-market)
        effective_codes = stock_codes if stock_codes is not None else config.stock_list
        filtered_codes, effective_region, should_skip = _compute_trading_day_filter(
            config, args, effective_codes
        )
        if should_skip:
            logger.info(
                "All relevant markets are closed today; skipping execution. "
                "Use --force-run to override the calendar check."
            )
            return True
        if set(filtered_codes) != set(effective_codes):
            skipped = set(effective_codes) - set(filtered_codes)
            logger.info("Skipped symbols whose markets are closed today: %s", skipped)
        stock_codes = filtered_codes

        # The --single-notify CLI option overrides configuration (#55).
        if getattr(args, 'single_notify', False):
            config.single_stock_notify = True

        # Issue #190: combine stock analysis and market review notifications.
        merge_notification = (
            getattr(config, 'merge_email_notification', False)
            and config.market_review_enabled
            and not getattr(args, 'no_market_review', False)
            and not config.single_stock_notify
        )

        # Create the analysis pipeline.
        save_context_snapshot = None
        if getattr(args, 'no_context_snapshot', False):
            save_context_snapshot = False
        query_id = uuid.uuid4().hex
        market_review_region = (
            effective_region
            if effective_region is not None
            else (getattr(config, 'market_review_region', 'cn') or 'cn')
        )
        should_run_market_review = (
            config.market_review_enabled
            and not args.no_market_review
            and (market_review_region or '') != ''
        )
        should_use_daily_market_context = (
            should_run_market_review
            and getattr(config, 'daily_market_context_enabled', True)
        )
        analysis_reference_time = datetime.now(timezone.utc)
        daily_market_context_target_date = None
        if should_use_daily_market_context:
            daily_market_context_target_date = _resolve_daily_market_context_target_date(
                market_review_region,
                analysis_reference_time,
            )
        market_report = ""
        market_context_summary = ""
        market_context_full_report = ""
        market_context_generated_during_stock = False
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers,
            query_id=query_id,
            query_source="cli",
            save_context_snapshot=save_context_snapshot,
            daily_market_context_enabled=should_use_daily_market_context,
            daily_market_context_allow_generate=should_use_daily_market_context,
        )
        if should_use_daily_market_context:
            # Prompt-side context can reuse historical summaries, while full-merge
            # content must avoid silently reusing unrelated historical reports.
            _prime_daily_market_context(
                config,
                pipeline=pipeline,
                region=market_review_region,
                no_market_review=args.no_market_review,
                allow_generate=False,
                target_date=daily_market_context_target_date,
                return_full_report=False,
            )
            (
                market_context_summary,
                market_context_full_report,
            ) = _prime_daily_market_context(
                config,
                pipeline=pipeline,
                region=market_review_region,
                no_market_review=args.no_market_review,
                allow_generate=False,
                target_date=daily_market_context_target_date,
                return_full_report=True,
                require_current_query_match=True,
            )

        # 1. Run stock analysis.
        results = pipeline.run(
            stock_codes=stock_codes,
            dry_run=args.dry_run,
            send_notification=not args.no_notify,
            merge_notification=merge_notification,
            current_time=analysis_reference_time,
        )

        if should_use_daily_market_context and not market_context_summary:
            (
                market_context_summary,
                market_context_full_report,
            ) = _prime_daily_market_context(
                config,
                pipeline=pipeline,
                region=market_review_region,
                no_market_review=args.no_market_review,
                allow_generate=False,
                target_date=daily_market_context_target_date,
                return_full_report=True,
                require_current_query_match=True,
            )
            market_context_generated_during_stock = bool(market_context_summary)

        # Issue #128: delay between stock analysis and market review.
        analysis_delay = getattr(config, 'analysis_delay', 0)

        # 2. Run market review when enabled and not in stock-only mode.
        if should_run_market_review:
            schedule_mode = bool(
                getattr(args, 'schedule', False)
                or getattr(config, 'schedule_enabled', False)
            )
            review_trigger_source = "schedule" if schedule_mode else "cli"
            can_reuse_market_context = (
                _can_reuse_market_context_for_review(
                    market_context_summary,
                    market_review_region,
                )
                if should_use_daily_market_context
                else False
            )

            can_skip_market_review = (
                (merge_notification or market_context_generated_during_stock)
                and can_reuse_market_context
                and bool(market_context_full_report or market_context_summary)
            )
            if can_skip_market_review:
                market_report = market_context_full_report or market_context_summary
                logger.info(
                    "Reusable market context is available; skipping duplicate review generation."
                )
                _save_reused_market_review_report(
                    pipeline.notifier,
                    market_report,
                    config=config,
                    trigger_source=review_trigger_source,
                    region=market_review_region,
                )
                if (
                    market_context_generated_during_stock
                    and not merge_notification
                    and not args.no_notify
                    and pipeline.notifier.is_available()
                ):
                    if pipeline.notifier.send(
                        f"# 📈 Tổng quan thị trường\n\n{market_report}",
                        email_send_to_all=True,
                        route_type="report",
                    ):
                        logger.info("Sent the market review using context from this run")
                    else:
                        logger.warning("Failed to send the market review from reusable context")

            review_result = None
            if not can_skip_market_review:
                if analysis_delay > 0:
                    logger.info(
                        "Waiting %s seconds before market review to respect API rate limits...",
                        analysis_delay,
                    )
                    time.sleep(analysis_delay)

                review_result = _run_market_review_with_shared_lock(
                    config,
                    run_market_review,
                    notifier=pipeline.notifier,
                    analyzer=pipeline.analyzer,
                    search_service=pipeline.search_service,
                    send_notification=not args.no_notify,
                    merge_notification=merge_notification,
                    override_region=market_review_region,
                    query_id=query_id,
                    trigger_source=review_trigger_source,
                )
                # Retry the reusable history/cache lookup to avoid a concurrent-run race.
                if not review_result and should_use_daily_market_context:
                    (
                        market_context_summary,
                        market_context_full_report,
                    ) = _prime_daily_market_context(
                        config,
                        pipeline=pipeline,
                        region=market_review_region,
                        no_market_review=args.no_market_review,
                        allow_generate=False,
                        target_date=daily_market_context_target_date,
                        return_full_report=True,
                        require_current_query_match=True,
                    )
                    can_reuse_market_context = _can_reuse_market_context_for_review(
                        market_context_summary,
                        market_review_region,
                    )
                elif not review_result:
                    can_reuse_market_context = False

            # Retain the review for optional downstream Lark document generation.
            if review_result:
                market_report = _market_review_report_text(review_result)
            elif can_reuse_market_context:
                market_report = market_context_full_report or market_context_summary

        # Issue #190: combined stock-analysis and market-review notification.
        if merge_notification and (results or market_report) and not args.no_notify:
            parts = []
            if market_report:
                parts.append(f"# 📈 Tổng quan thị trường\n\n{market_report}")
            if results:
                dashboard_content = pipeline.notifier.generate_aggregate_report(
                    results,
                    getattr(config, 'report_type', 'simple'),
                )
                parts.append(f"# 🚀 Bảng điều khiển quyết định cổ phiếu\n\n{dashboard_content}")
            if parts:
                combined_content = "\n\n---\n\n".join(parts)
                if pipeline.notifier.is_available():
                    if pipeline.notifier.send(combined_content, email_send_to_all=True, route_type="report"):
                        logger.info("Sent the combined stock-analysis and market-review notification")
                    else:
                        logger.warning("Failed to send the combined notification")

        # Log a concise run summary.
        if results:
            logger.info("\n===== Analysis summary =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"score {r.sentiment_score} | {r.trend_prediction}"
                )

        logger.info("\nAnalysis task completed")

        # Optionally generate a Lark cloud document.
        try:
            from src.feishu_doc import FeishuDocManager

            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("Creating a Lark cloud document...")

                # 1. Prepare the title.
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} Tổng quan thị trường"

                # 2. Combine stock analysis and market review content.
                full_content = ""

                # Include market review content when available.
                if market_report:
                    full_content += f"# 📈 Tổng quan thị trường\n\n{market_report}\n\n---\n\n"

                # Include the stock dashboard produced for the configured report type.
                if results:
                    dashboard_content = pipeline.notifier.generate_aggregate_report(
                        results,
                        getattr(config, 'report_type', 'simple'),
                    )
                    full_content += f"# 🚀 Bảng điều khiển quyết định cổ phiếu\n\n{dashboard_content}"

                # 3. Create the document.
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info("Created the Lark cloud document: %s", doc_url)
                    # Optionally notify the group with the document link.
                    if not args.no_notify:
                        pipeline.notifier.send(
                            f"[{now.strftime('%Y-%m-%d %H:%M')}] Đã tạo báo cáo: {doc_url}",
                            route_type="report",
                        )

        except Exception as e:
            logger.error("Failed to generate the Lark document: %s", e)

        # === Auto backtest ===
        try:
            if getattr(config, 'backtest_enabled', False):
                from src.services.backtest_service import BacktestService

                logger.info("Starting automatic backtesting...")
                service = BacktestService()
                stats = service.run_backtest(
                    force=False,
                    eval_window_days=getattr(config, 'backtest_eval_window_days', 10),
                    min_age_days=getattr(config, 'backtest_min_age_days', 14),
                    limit=200,
                )
                logger.info(
                    f"Automatic backtesting completed: processed={stats.get('processed')} saved={stats.get('saved')} "
                    f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
                )
        except Exception as e:
            logger.warning("Automatic backtesting failed and was ignored: %s", e)

        return True

    except Exception as e:
        logger.exception("Analysis workflow failed: %s", e)
        if raise_errors:
            raise
        return False


def run_scheduled_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
) -> bool:
    """Run scheduled analysis with failures propagated to the scheduler."""
    return run_full_analysis(config, args, stock_codes, raise_errors=True)


def _run_analysis_with_runtime_scheduler_lock(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
) -> None:
    from src.services.runtime_scheduler import run_with_global_analysis_lock

    # Keep startup/triggered analysis in sync with API runtime scheduler and
    # run-now entrypoint. Blocking is expected here because startup paths should
    # wait for an in-flight job before returning a response.
    run_with_global_analysis_lock(
        task_runner=run_full_analysis,
        config=config,
        args=args,
        stock_codes=stock_codes,
        blocking=True,
    )


def start_api_server(host: str, port: int, config: Config) -> None:
    """
    Start the FastAPI service in a background thread.

    Args:
        host: Bind address.
        port: Bind port.
        config: Application configuration.
    """
    import socket
    import threading
    import uvicorn

    probe = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise RuntimeError(f"FastAPI port is not available: {host}:{port}") from exc
    finally:
        probe.close()

    level_name = (config.log_level or "INFO").lower()
    use_config_signal_handlers = True
    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "log_level": level_name,
        "log_config": None,
    }
    # Import the ASGI app object in the calling thread instead of handing uvicorn
    # the "api.app:app" import string. With the string, uvicorn imports the app
    # lazily inside the server thread, and that import (litellm + the full app
    # tree, ~10s+ on constrained hosts) runs inside the startup probe window
    # below, tripping the 3.0s timeout and causing a restart loop on slower
    # machines. Importing first keeps the heavy work out of the probe window;
    # genuine import failures still surface immediately to the caller.
    from api.app import app as fastapi_app

    try:
        uvicorn_config = uvicorn.Config(
            fastapi_app,
            install_signal_handlers=False,
            **uvicorn_kwargs,
        )
    except TypeError:
        # Older uvicorn versions do not accept install_signal_handlers in
        # Config; fall back and only disable signal handling via Server attribute
        # when it's a boolean flag.
        use_config_signal_handlers = False
        uvicorn_config = uvicorn.Config(
            fastapi_app,
            **uvicorn_kwargs,
        )
    uvicorn_server = uvicorn.Server(config=uvicorn_config)
    if not use_config_signal_handlers:
        install_signal_handlers = getattr(uvicorn_server, "install_signal_handlers", None)
        if isinstance(install_signal_handlers, bool):
            uvicorn_server.install_signal_handlers = False

    startup_error: list[BaseException] = []

    def run_server():
        try:
            uvicorn_server.run()
        except Exception as exc:  # noqa: BLE001 - surface startup issues to caller promptly
            startup_error.append(exc)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    timeout_seconds = 3.0
    wait_deadline = time.time() + timeout_seconds
    while time.time() < wait_deadline:
        if startup_error:
            raise RuntimeError(
                f"FastAPI server failed to start: {host}:{port}; {startup_error[0]}"
            )
        if uvicorn_server.started:
            logger.info("FastAPI service started: http://%s:%s", host, port)
            return
        if not thread.is_alive():
            break
        time.sleep(0.05)

    if startup_error:
        raise RuntimeError(f"FastAPI server failed to start: {host}:{port}; {startup_error[0]}")
    if uvicorn_server.started:
        logger.info("FastAPI service started: http://%s:%s", host, port)
        return
    if not thread.is_alive():
        raise RuntimeError(f"FastAPI exited immediately after startup: {host}:{port}")

    raise RuntimeError(f"FastAPI did not start within {timeout_seconds:.1f}s: {host}:{port}")


def _is_truthy_env(var_name: str, default: str = "true") -> bool:
    """Parse common truthy / falsy environment values."""
    value = os.getenv(var_name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}


def start_bot_stream_clients(config: Config) -> None:
    """Start bot stream clients when enabled in config."""
    # Start the DingTalk Stream client when configured.
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Dingtalk Stream client: {exc}")

    # Start the Lark Stream client when configured.
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Feishu Stream client: {exc}")


def _resolve_scheduled_stock_codes(stock_codes: Optional[List[str]]) -> Optional[List[str]]:
    """Scheduled runs should always read the latest persisted watchlist."""
    if stock_codes is not None:
        logger.warning(
            "--stocks was supplied in scheduled mode. Scheduled runs ignore the startup "
            "snapshot and reload the latest STOCK_LIST before every execution."
        )
    return None


def _reload_runtime_config() -> Config:
    """Reload config from the latest persisted `.env` values for scheduled runs."""
    _reload_env_file_values_preserving_overrides()
    Config.reset_instance()
    return get_config()


def _build_schedule_time_provider(default_schedule_time: str):
    """Read the latest schedule time directly from the active config file.

    Fallback order:
    1. Process-level env override (set before launch) → honour it.
    2. Persisted config file value (written by WebUI) → use it.
    3. Documented system default ``"18:00"`` → always fall back here so
       that clearing SCHEDULE_TIME in WebUI correctly resets the schedule.
    """
    from src.core.config_manager import ConfigManager

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider() -> str:
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return os.getenv("SCHEDULE_TIME", default_schedule_time)

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip()
        if schedule_time:
            return schedule_time
        return _SYSTEM_DEFAULT_SCHEDULE_TIME

    return _provider


def _build_schedule_times_provider(default_schedule_time: str):
    """Read the latest SCHEDULE_TIMES with SCHEDULE_TIME fallback."""
    from src.core.config_manager import ConfigManager
    from src.scheduler import normalize_schedule_times

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider():
        if "SCHEDULE_TIMES" in _INITIAL_PROCESS_ENV:
            return normalize_schedule_times(
                os.getenv("SCHEDULE_TIMES", ""),
                fallback_time=os.getenv("SCHEDULE_TIME", default_schedule_time),
            )
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return normalize_schedule_times(
                os.getenv("SCHEDULE_TIMES", ""),
                fallback_time=os.getenv("SCHEDULE_TIME", default_schedule_time),
            )

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip() or _SYSTEM_DEFAULT_SCHEDULE_TIME
        return normalize_schedule_times(
            config_map.get("SCHEDULE_TIMES", ""),
            fallback_time=schedule_time,
        )

    return _provider


def main() -> int:
    """
    Main process entry point.

    Returns:
        Process exit code (zero indicates success).
    """
    # Parse command-line arguments.
    args = parse_arguments()

    # Initialize bootstrap logging before configuration loading.
    try:
        _setup_bootstrap_logging(debug=args.debug)
    except Exception as exc:
        logging.basicConfig(
            level=logging.DEBUG if getattr(args, "debug", False) else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        logger.warning("Bootstrap logging failed; falling back to stderr: %s", exc)

    # Load configuration after bootstrap logging is available.
    try:
        config = get_config()
    except Exception as exc:
        logger.exception("Failed to load configuration: %s", exc)
        return 1

    # Switch to configured console and file logging.
    try:
        _setup_runtime_logging(config.log_dir, debug=args.debug)
    except Exception as exc:
        logger.exception("Failed to switch to the configured log directory: %s", exc)
        return 1

    logger.info("=" * 60)
    logger.info("Daily Stock Analysis Vietnam started")
    logger.info("Start time: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 60)

    # Validate configuration.
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    if getattr(args, "check_notify", False):
        from src.services.notification_diagnostics import (
            format_notification_diagnostics,
            run_notification_diagnostics,
        )

        result = run_notification_diagnostics(config)
        print(format_notification_diagnostics(result))
        return 0 if result.ok else 1

    # Parse and normalize stock symbols (Issue #355).
    stock_codes = None
    if args.stocks:
        stock_codes = [
            resolve_index_stock_code_for_analysis(c)
            for c in split_stock_list(args.stocks)
            if (c or "").strip()
        ]
        enabled_markets = {
            str(market).strip().lower()
            for market in (getattr(config, "enabled_markets", None) or [])
            if str(market).strip()
        }
        rejected_codes = (
            [code for code in stock_codes if not is_vn_market_symbol(code)]
            if enabled_markets == {"vn"}
            else []
        )
        if rejected_codes:
            logger.error(
                "This local installation accepts Vietnam symbols only; rejected: %s",
                ", ".join(rejected_codes),
            )
            return 2
        logger.info("Using stock symbols supplied on the command line: %s", stock_codes)

    # Map legacy --webui options to --serve options.
    if args.webui:
        args.serve = True
    if args.webui_only:
        args.serve_only = True

    # Preserve compatibility with the legacy WEBUI_ENABLED variable.
    if config.webui_enabled and not (args.serve or args.serve_only):
        args.serve = True

    # Start the Web service when enabled.
    start_serve = (args.serve or args.serve_only) and os.getenv("GITHUB_ACTIONS") != "true"

    if start_serve:
        args.host, args.port = _resolve_web_service_bind(args, config)
        _warn_if_public_webui_without_auth(args.host)

    bot_clients_started = False
    if start_serve:
        from src.services.runtime_scheduler import (
            CLI_SCHEDULER_OWNER_ENV,
            RUNTIME_SCHEDULER_ARGS_ENV,
            RUNTIME_SCHEDULER_FORCE_ENABLED_ENV,
            RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV,
            RUNTIME_SCHEDULER_SUPPRESS_START_ENV,
        )

        # The API runtime scheduler owns schedules once the Web/API service starts.
        # This keeps Web settings, status, and run-now actions attached to the real
        # scheduler instead of a separate CLI loop.
        os.environ.pop(CLI_SCHEDULER_OWNER_ENV, None)
        if args.serve_only:
            os.environ[RUNTIME_SCHEDULER_SUPPRESS_START_ENV] = "true"
        else:
            os.environ.pop(RUNTIME_SCHEDULER_SUPPRESS_START_ENV, None)
        runtime_schedule_requested = not args.serve_only and (
            args.schedule or config.schedule_enabled
        )
        if not args.serve_only and args.schedule:
            os.environ[RUNTIME_SCHEDULER_FORCE_ENABLED_ENV] = "true"
        else:
            os.environ.pop(RUNTIME_SCHEDULER_FORCE_ENABLED_ENV, None)
        if runtime_schedule_requested:
            runtime_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                runtime_run_immediately = False
            os.environ[RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV] = (
                "true" if runtime_run_immediately else "false"
            )
        else:
            os.environ.pop(RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV, None)
        os.environ[RUNTIME_SCHEDULER_ARGS_ENV] = json.dumps({
            "no_notify": bool(getattr(args, "no_notify", False)),
            "no_market_review": bool(getattr(args, "no_market_review", False)),
            "dry_run": bool(getattr(args, "dry_run", False)),
            "force_run": bool(getattr(args, "force_run", False)),
            "single_notify": bool(getattr(args, "single_notify", False)),
            "no_context_snapshot": bool(getattr(args, "no_context_snapshot", False)),
            "workers": getattr(args, "workers", None),
        })
        if not prepare_webui_frontend_assets():
            logger.warning("Web static assets are not ready; starting FastAPI without a usable Web page")
        try:
            start_api_server(host=args.host, port=args.port, config=config)
            bot_clients_started = True
        except Exception as e:
            logger.error("Failed to start FastAPI: %s", e)
            if args.serve_only:
                return 1
            start_serve = False

    if bot_clients_started:
        start_bot_stream_clients(config)

    # Web-service-only mode does not execute analysis automatically.
    if args.serve_only:
        logger.info("Mode: Web service only")
        logger.info("Web service: http://%s:%s", args.host, args.port)
        logger.info("Trigger analysis through /api/v1/analysis/analyze")
        logger.info("API documentation: http://%s:%s/docs", args.host, args.port)
        logger.info("Press Ctrl+C to exit...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nInterrupted by user; exiting")
        return 0

    try:
        # Mode 0: backtesting.
        if getattr(args, 'backtest', False):
            logger.info("Mode: backtesting")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"Backtesting completed: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # Mode 1: market review only.
        if args.market_review:
            enabled_markets = {
                str(market).strip().lower()
                for market in (getattr(config, "enabled_markets", None) or [])
                if str(market).strip()
            }
            if enabled_markets == {"vn"}:
                logger.error(
                    "Vietnam market review is disabled because the legacy implementation "
                    "uses non-Vietnam indices."
                )
                return 2
            from src.core.market_review import run_market_review
            from src.core.market_review_runtime import build_market_review_runtime

            # Issue #373: Trading day check for market-review-only mode.
            # Do NOT use _compute_trading_day_filter here: that helper checks
            # config.market_review_enabled, which would wrongly block an
            # explicit --market-review invocation when the flag is disabled.
            effective_region = None
            if not getattr(args, 'force_run', False) and getattr(config, 'trading_day_check_enabled', True):
                from src.core.trading_calendar import get_open_markets_today, compute_effective_region as _compute_region
                open_markets = get_open_markets_today()
                effective_region = _compute_region(
                    getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
                )
                if effective_region == '':
                    logger.info(
                        "Markets required for review are closed today; skipping execution. "
                        "Use --force-run to override the calendar check."
                    )
                    return 0

            logger.info("Mode: market review only")
            notifier, analyzer, search_service = build_market_review_runtime(config)

            _run_market_review_with_shared_lock(
                config,
                run_market_review,
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=not args.no_notify,
                override_region=effective_region,
                trigger_source="cli",
            )
            return 0

        # Mode 2: scheduled execution.
        if args.schedule or config.schedule_enabled:
            if start_serve:
                logger.info("Mode: Web/API runtime scheduler")
                logger.info("Web service: http://%s:%s", args.host, args.port)
                logger.info("Saved scheduler settings apply to the current Web/API process")
                logger.info("Press Ctrl+C to exit...")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("\nInterrupted by user; exiting")
                return 0

            logger.info("Mode: scheduled execution")
            logger.info("Daily execution time: %s", config.schedule_time)

            # Determine whether to run immediately:
            # Command line arg --no-run-immediately overrides config if present.
            # Otherwise use config (defaults to True).
            should_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                should_run_immediately = False

            logger.info("Run immediately at startup: %s", should_run_immediately)

            from src.scheduler import run_with_schedule
            scheduled_stock_codes = _resolve_scheduled_stock_codes(stock_codes)
            schedule_time_provider = _build_schedule_time_provider(config.schedule_time)
            schedule_times_provider = _build_schedule_times_provider(config.schedule_time)

            def scheduled_task():
                runtime_config = _reload_runtime_config()
                run_full_analysis(runtime_config, args, scheduled_stock_codes)

            background_tasks = []
            if getattr(config, 'agent_event_monitor_enabled', False):
                from src.services.alert_worker import AlertWorker

                interval_minutes = max(1, getattr(config, 'agent_event_monitor_interval_minutes', 5))
                alert_worker = AlertWorker(config_provider=_reload_runtime_config)

                def event_monitor_task():
                    stats = alert_worker.run_once()
                    triggered_count = stats.get("triggered", 0)
                    if triggered_count:
                        logger.info("[EventMonitor] Triggered %d alerts in this run", triggered_count)

                background_tasks.append({
                    "task": event_monitor_task,
                    "interval_seconds": interval_minutes * 60,
                    "run_immediately": True,
                    "name": "agent_event_monitor",
                })

            schedule_kwargs = {
                "task": scheduled_task,
                "schedule_time": config.schedule_time,
                "run_immediately": should_run_immediately,
                "background_tasks": background_tasks,
                "schedule_time_provider": schedule_time_provider,
            }
            if hasattr(config, "schedule_timezone"):
                schedule_kwargs["schedule_timezone"] = config.schedule_timezone
            if hasattr(config, "schedule_times"):
                schedule_kwargs["schedule_times"] = config.schedule_times
                schedule_kwargs["schedule_times_provider"] = schedule_times_provider
            run_with_schedule(**schedule_kwargs)
            return 0

        # Mode 3: normal one-time execution.
        if config.run_immediately:
            _run_analysis_with_runtime_scheduler_lock(config, args, stock_codes)
        else:
            logger.info("Analysis is not configured to run immediately (RUN_IMMEDIATELY=false)")

        logger.info("\nProgram execution completed")

        # Keep a non-scheduled API service alive when enabled.
        keep_running = start_serve and not (args.schedule or config.schedule_enabled)
        if keep_running:
            logger.info("API service is running (press Ctrl+C to exit)...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user; exiting")
        return 130

    except Exception as e:
        logger.exception("Program execution failed: %s", e)
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
