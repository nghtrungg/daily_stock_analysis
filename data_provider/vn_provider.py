# -*- coding: utf-8 -*-
"""Vietnam stock-market helpers backed by the free ``vnstock`` package.

The functions in this module are intentionally lightweight and fail-open:
upstream API drift, invalid tickers, empty responses, or transient network
errors return empty payloads instead of interrupting the main analysis flow.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

KLINE_COLUMNS = ["date", "open", "high", "low", "close", "volume"]

_KLINE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "date": (
        "date",
        "datetime",
        "time",
        "timestamp",
        "trading_date",
        "tradingdate",
    ),
    "open": ("open", "open_price", "openprice", "price_open", "o"),
    "high": ("high", "high_price", "highprice", "price_high", "h"),
    "low": ("low", "low_price", "lowprice", "price_low", "l"),
    "close": (
        "close",
        "close_price",
        "closeprice",
        "price_close",
        "matched_price",
        "c",
    ),
    "volume": (
        "volume",
        "vol",
        "trading_volume",
        "matched_volume",
        "total_volume",
        "v",
    ),
}

_PROFILE_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "company_name": (
        "company_name",
        "company",
        "organ_name",
        "org_name",
        "name",
        "short_name",
        "organ_short_name",
        "company_short_name",
    ),
    "exchange": (
        "exchange",
        "exchange_code",
        "exchange_name",
        "floor",
        "floor_code",
        "listing_exchange",
    ),
    "industry": (
        "industry",
        "industry_name",
        "icb_name",
        "sector",
        "sector_name",
        "business_line",
    ),
    "business_model": (
        "business_model",
        "business_summary",
        "company_profile",
        "overview",
        "description",
        "history",
    ),
    "listing_date": ("listing_date", "listed_date", "list_date"),
    "website": ("website", "url", "web_site"),
    "charter_capital": ("charter_capital", "capital", "listed_capital"),
    "outstanding_shares": (
        "outstanding_shares",
        "shares_outstanding",
        "listed_volume",
        "listed_shares",
    ),
}

_METRIC_ALIASES: Dict[str, Tuple[str, ...]] = {
    "pe_ratio": (
        "pe_ratio",
        "p_e",
        "p_e_ratio",
        "pe",
        "price_earnings_ratio",
        "price_to_earnings",
        "price_to_earnings_ratio",
    ),
    "pb_ratio": (
        "pb_ratio",
        "p_b",
        "p_b_ratio",
        "pb",
        "price_book_ratio",
        "price_to_book",
        "price_to_book_ratio",
    ),
    "roe": ("roe", "return_on_equity", "return_on_equity_ratio"),
}

_INTRADAY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "time": (
        "time",
        "datetime",
        "timestamp",
        "trading_time",
        "match_time",
        "order_time",
    ),
    "price": (
        "price",
        "match_price",
        "matched_price",
        "last_price",
        "close",
    ),
    "volume": (
        "volume",
        "match_volume",
        "matched_volume",
        "vol",
        "quantity",
        "total_volume",
    ),
    "side": (
        "side",
        "match_type",
        "order_type",
        "type",
        "buy_sell",
        "buysell",
    ),
}

_QUOTE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "price": ("price", "last_price", "match_price", "close", "matched_price"),
    "reference_price": ("reference_price", "ref_price", "basic_price"),
    "bid_price": ("bid_price", "best_bid", "bid1_price", "bid_1_price", "buy_price_1"),
    "bid_volume": ("bid_volume", "best_bid_volume", "bid1_volume", "bid_1_volume", "buy_volume_1"),
    "ask_price": ("ask_price", "best_ask", "ask1_price", "ask_1_price", "sell_price_1"),
    "ask_volume": ("ask_volume", "best_ask_volume", "ask1_volume", "ask_1_volume", "sell_volume_1"),
}


def get_vietnam_kline(ticker: str, days: int = 30) -> pd.DataFrame:
    """Return recent daily OHLCV bars for a Vietnamese stock ticker.

    Args:
        ticker: Vietnamese stock symbol, such as ``VNM``, ``FPT``, or ``ACB``.
        days: Calendar lookback window ending on the current local date.

    Returns:
        A DataFrame with columns ``date, open, high, low, close, volume``.
        ``date`` is a pandas datetime column. The frame uses a regular index so
        it is compatible with the shared provider normalization pipeline.
        Errors and no-data responses return an empty frame with the same shape.
    """

    symbol = _normalize_ticker(ticker)
    if not symbol:
        logger.warning("vnstock kline request skipped: empty ticker")
        return _empty_kline_frame()

    lookback_days = _coerce_days(days)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=lookback_days)
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    try:
        raw_df = _fetch_ohlcv(symbol, start_text, end_text, lookback_days)
        normalized = _normalize_kline_frame(raw_df)
        if normalized.empty:
            logger.warning(
                "vnstock returned no OHLCV rows for %s in %s..%s",
                symbol,
                start_text,
                end_text,
            )
            return _empty_kline_frame()
        return normalized
    except (TimeoutError, ConnectionError) as exc:
        logger.warning(
            "vnstock network timeout while fetching OHLCV for %s: %s",
            symbol,
            _short_error(exc),
        )
        return _empty_kline_frame()
    except Exception as exc:
        logger.warning(
            "vnstock OHLCV fetch failed for %s: %s",
            symbol,
            _short_error(exc),
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        return _empty_kline_frame()


def get_vietnam_intraday_snapshot(ticker: str) -> dict:
    """Return a current-day intraday snapshot for a Vietnamese ticker.

    The snapshot combines today's trade tape with the best available real-time
    quote data. It is useful during the HOSE/HNX midday break and after market
    close because the morning-session volume is calculated from observed
    trades up to 11:30 local exchange time.
    """

    symbol = _normalize_ticker(ticker)
    if not symbol:
        logger.warning("vnstock intraday request skipped: empty ticker")
        return {}

    errors: List[str] = []

    try:
        trades = _normalize_intraday_trades(_fetch_intraday_trades(symbol))
    except Exception as exc:
        trades = pd.DataFrame(columns=["time", "price", "volume", "side"])
        errors.append(f"trades: {_short_error(exc)}")

    try:
        quote = _normalize_quote_payload(_fetch_realtime_quote(symbol))
    except Exception as exc:
        quote = {}
        errors.append(f"quote: {_short_error(exc)}")

    if trades.empty and not quote:
        logger.warning(
            "vnstock returned no intraday data for %s: %s",
            symbol,
            "; ".join(errors) or "empty response",
        )
        return {}

    snapshot = _build_intraday_snapshot(symbol, trades, quote)
    if errors:
        snapshot["errors"] = errors
    return snapshot


def get_vietnam_market_flow_snapshot(
    ticker: str,
    *,
    include_advanced: bool = False,
) -> dict:
    """Return VN active order flow plus optional foreign/proprietary flow.

    Active buy/sell pressure is derived from the free intraday trade tape.
    Foreign and proprietary flow are only requested from ``vnstock_data``
    when explicitly enabled; the free ``vnstock`` package does not expose
    those endpoints.
    """
    symbol = _normalize_ticker(ticker)
    if not symbol:
        return {}

    errors: List[str] = []
    try:
        trades = _normalize_intraday_trades(_fetch_intraday_trades(symbol))
    except Exception as exc:
        trades = pd.DataFrame(columns=["time", "price", "volume", "side"])
        errors.append(f"active_order_flow: {_short_error(exc)}")

    buy_volume = _safe_float(trades.loc[trades["side"] == "buy", "volume"].sum()) or 0.0
    sell_volume = _safe_float(trades.loc[trades["side"] == "sell", "volume"].sum()) or 0.0
    unknown_volume = _safe_float(
        trades.loc[~trades["side"].isin(["buy", "sell"]), "volume"].sum()
    ) or 0.0
    classified_volume = buy_volume + sell_volume
    stock_flow: Dict[str, Any] = {
        "active_buy_volume": buy_volume,
        "active_sell_volume": sell_volume,
        "active_unknown_volume": unknown_volume,
        "active_net_volume": buy_volume - sell_volume,
    }
    if classified_volume > 0:
        stock_flow["active_buy_ratio"] = round(buy_volume / classified_volume, 6)
        stock_flow["active_sell_ratio"] = round(sell_volume / classified_volume, 6)
        stock_flow["active_imbalance"] = round(
            (buy_volume - sell_volume) / classified_volume,
            6,
        )

    advanced: Dict[str, Any] = {}
    if include_advanced:
        try:
            advanced = _fetch_vnstock_data_market_flows(symbol)
        except Exception as exc:
            errors.append(f"advanced_flow: {_short_error(exc)}")
    for flow_name in ("foreign_flow", "proprietary_flow"):
        flow = advanced.get(flow_name)
        if isinstance(flow, dict):
            prefix = "foreign" if flow_name == "foreign_flow" else "proprietary"
            for key, value in flow.items():
                if key not in {"time", "date"} and value is not None:
                    stock_flow[f"{prefix}_{key}"] = value

    coverage = {
        "active_order_flow": "ok" if classified_volume > 0 else "missing",
        "foreign_flow": "ok" if isinstance(advanced.get("foreign_flow"), dict) else "not_configured",
        "proprietary_flow": "ok" if isinstance(advanced.get("proprietary_flow"), dict) else "not_configured",
    }
    payload: Dict[str, Any] = {
        "ticker": symbol,
        "market": "VN",
        "source": "vnstock_data+vnstock" if advanced else "vnstock",
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "stock_flow": stock_flow,
        "coverage": coverage,
    }
    if errors:
        payload["errors"] = errors
    return payload


def get_vietnam_company_profile(ticker: str) -> dict:
    """Return company profile and key valuation metrics for a VN ticker.

    The returned dict keeps the most useful fields at top level and preserves
    all flattened profile fields under ``profile`` for future scoring needs.
    P/E, P/B, and ROE are exposed as ``pe_ratio``, ``pb_ratio``, and ``roe``.
    """

    symbol = _normalize_ticker(ticker)
    if not symbol:
        logger.warning("vnstock profile request skipped: empty ticker")
        return {}

    profile_errors: List[str] = []

    try:
        profile = _flatten_profile(_fetch_company_info(symbol))
    except Exception as exc:
        profile = {}
        profile_errors.append(f"profile: {_short_error(exc)}")

    try:
        metrics = _extract_financial_metrics(_fetch_financial_ratios(symbol))
    except Exception as exc:
        metrics = {}
        profile_errors.append(f"ratios: {_short_error(exc)}")

    if not profile and not metrics:
        logger.warning(
            "vnstock returned no company profile data for %s: %s",
            symbol,
            "; ".join(profile_errors) or "empty response",
        )
        return {}

    payload: Dict[str, Any] = {
        "ticker": symbol,
        "market": "VN",
        "source": "vnstock",
        "profile": profile,
        "metrics": metrics,
        "pe_ratio": metrics.get("pe_ratio"),
        "pb_ratio": metrics.get("pb_ratio"),
        "roe": metrics.get("roe"),
    }

    if profile_errors:
        payload["errors"] = profile_errors

    for target, aliases in _PROFILE_FIELD_ALIASES.items():
        value = _pick_by_alias(profile, aliases)
        if value is not None:
            payload[target] = value

    return {key: value for key, value in payload.items() if value is not None}


def get_vietnam_ownership_snapshot(ticker: str) -> dict:
    """Return disclosed ownership records for a Vietnam-listed company.

    This is ownership structure, not a daily net-buy/net-sell feed.  Preserve
    provider field names so downstream consumers do not invent investor
    categories that the source did not disclose.
    """
    symbol = _normalize_ticker(ticker)
    if not symbol:
        return {}
    try:
        frame = _to_dataframe(_call_company_ownership(symbol))
    except Exception as exc:
        logger.warning("vnstock ownership fetch failed for %s: %s", symbol, _short_error(exc))
        return {}
    if frame.empty:
        return {}

    records = []
    for raw in frame.head(50).to_dict(orient="records"):
        record = {
            _snake_key(key): _to_python(value)
            for key, value in raw.items()
            if _snake_key(key) and _to_python(value) is not None
        }
        if record:
            records.append(record)
    if not records:
        return {}
    return {
        "ticker": symbol,
        "market": "VN",
        "source": "vnstock",
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "records": records,
        "record_count": len(records),
    }


def _fetch_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    count: int,
) -> pd.DataFrame:
    attempts: List[Tuple[str, Callable[[], Any]]] = [
        (
            "Market.equity.ohlcv",
            lambda: _call_market_ohlcv(symbol, start_date, end_date, count),
        ),
        (
            "Quote.history",
            lambda: _call_quote_history(symbol, start_date, end_date, count),
        ),
        (
            "stock_historical_data",
            lambda: _call_legacy_stock_history(symbol, start_date, end_date),
        ),
    ]
    return _first_non_empty_dataframe(attempts, "OHLCV")


def _fetch_company_info(symbol: str) -> pd.DataFrame:
    attempts: List[Tuple[str, Callable[[], Any]]] = [
        ("Reference.company.info", lambda: _call_reference_company_info(symbol)),
        ("Company.overview", lambda: _call_company_overview(symbol)),
        ("company_profile", lambda: _call_legacy_company_profile(symbol)),
    ]
    return _first_non_empty_dataframe(attempts, "company profile")


def _fetch_intraday_trades(symbol: str) -> pd.DataFrame:
    attempts: List[Tuple[str, Callable[[], Any]]] = [
        ("Market.equity.trades", lambda: _call_market_equity_method(symbol, "trades")),
        ("Quote.intraday", lambda: _call_quote_intraday(symbol)),
        ("stock_intraday_data", lambda: _call_legacy_intraday_data(symbol)),
    ]
    return _first_non_empty_dataframe(attempts, "intraday trades")


def _fetch_vnstock_data_market_flows(symbol: str) -> Dict[str, Any]:
    """Fetch sponsor-only VN flows through the documented Unified UI."""
    try:
        from vnstock_data import Market
    except ImportError:
        return {}

    equity = Market().equity(symbol)
    result: Dict[str, Any] = {}
    for key, method_name in (
        ("foreign_flow", "foreign_flow"),
        ("proprietary_flow", "proprietary_flow"),
    ):
        method = getattr(equity, method_name, None)
        if not callable(method):
            continue
        try:
            normalized = _normalize_vnstock_data_flow(method())
        except Exception as exc:
            logger.warning("vnstock_data %s failed for %s: %s", method_name, symbol, _short_error(exc))
            continue
        if normalized:
            result[key] = normalized
    return result


def _normalize_vnstock_data_flow(data: Any) -> Dict[str, Any]:
    """Normalize the documented buy/sell/net volume and value columns."""
    frame = _to_dataframe(data)
    if frame.empty:
        return {}
    normalized_columns = {_normalize_key(column): column for column in frame.columns}
    time_column = _resolve_column(
        normalized_columns,
        ("time", "date", "trading_date", "tradingdate"),
    )
    if time_column is not None:
        frame = frame.assign(
            __flow_time=pd.to_datetime(frame[time_column], errors="coerce")
        ).sort_values("__flow_time", na_position="first")
    row = frame.iloc[-1]
    aliases = {
        "buy_volume": ("buy_vol", "buy_volume"),
        "buy_value": ("buy_val", "buy_value"),
        "sell_volume": ("sell_vol", "sell_volume"),
        "sell_value": ("sell_val", "sell_value"),
        "net_volume": ("net_vol", "net_volume"),
        "net_value": ("net_val", "net_value"),
    }
    result: Dict[str, Any] = {}
    if time_column is not None:
        raw_time = row.get(time_column)
        if raw_time is not None and not pd.isna(raw_time):
            result["date"] = str(raw_time)
    for target, field_aliases in aliases.items():
        source = _resolve_column(normalized_columns, field_aliases)
        if source is None:
            continue
        value = _safe_float(row.get(source))
        if value is not None:
            result[target] = value
    return result


def _fetch_realtime_quote(symbol: str) -> pd.DataFrame:
    attempts: List[Tuple[str, Callable[[], Any]]] = [
        ("Market.equity.quote", lambda: _call_market_equity_method(symbol, "quote")),
        ("Market.quote", lambda: _call_market_quote(symbol)),
    ]
    return _first_non_empty_dataframe(attempts, "realtime quote")


def _fetch_financial_ratios(symbol: str) -> pd.DataFrame:
    attempts: List[Tuple[str, Callable[[], Any]]] = [
        ("Fundamental.equity.ratios", lambda: _call_fundamental_ratios(symbol)),
        ("Finance.ratio", lambda: _call_finance_ratio(symbol)),
        ("financial_ratio", lambda: _call_legacy_financial_ratio(symbol)),
    ]
    return _first_non_empty_dataframe(attempts, "financial ratios")


def _call_market_equity_method(symbol: str, method_name: str) -> Any:
    from vnstock import Market

    market = Market()
    equity_accessor = getattr(market, "equity")
    variants = (
        {"symbol": symbol, "source": "kbs"},
        {"symbol": symbol},
        {"ticker": symbol},
        {},
    )

    if callable(equity_accessor):
        try:
            equity = equity_accessor(symbol=symbol)
            method = getattr(equity, method_name)
            return _call_first_supported(method, variants)
        except TypeError:
            method = getattr(equity_accessor, method_name)
            return _call_first_supported(method, variants)

    method = getattr(equity_accessor, method_name)
    return _call_first_supported(method, variants)


def _call_market_quote(symbol: str) -> Any:
    from vnstock import Market

    market = Market()
    return _call_first_supported(
        market.quote,
        (
            {"symbols": [symbol], "source": "kbs"},
            {"symbols": [symbol]},
            {"symbol": symbol, "source": "kbs"},
            {"symbol": symbol},
        ),
    )


def _call_market_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    count: int,
) -> Any:
    from vnstock import Market

    market = Market()
    equity_accessor = getattr(market, "equity")

    if callable(equity_accessor):
        try:
            equity = equity_accessor(symbol=symbol)
            return _call_ohlcv_method(equity.ohlcv, start_date, end_date, count)
        except TypeError:
            return _call_ohlcv_method(
                lambda **kwargs: equity_accessor.ohlcv(symbol=symbol, **kwargs),
                start_date,
                end_date,
                count,
            )

    return _call_ohlcv_method(
        lambda **kwargs: equity_accessor.ohlcv(symbol=symbol, **kwargs),
        start_date,
        end_date,
        count,
    )


def _call_ohlcv_method(
    method: Callable[..., Any],
    start_date: str,
    end_date: str,
    count: int,
) -> Any:
    call_variants = (
        {
            "start": start_date,
            "end": end_date,
            "interval": "1D",
            "count": count,
            "source": "kbs",
        },
        {
            "start": start_date,
            "end": end_date,
            "interval": "1D",
            "count": count,
        },
        {
            "start": start_date,
            "end": end_date,
            "resolution": "1D",
            "length": count,
        },
    )
    return _call_first_supported(method, call_variants)


def _call_quote_history(
    symbol: str,
    start_date: str,
    end_date: str,
    count: int,
) -> Any:
    from vnstock import Quote

    quote = Quote(symbol=symbol, source="kbs")
    return _call_first_supported(
        quote.history,
        (
            {
                "start": start_date,
                "end": end_date,
                "interval": "1D",
                "count_back": count,
            },
            {"start": start_date, "end": end_date, "interval": "1D"},
            {"start": start_date, "end": end_date, "resolution": "1D"},
        ),
    )


def _call_quote_intraday(symbol: str) -> Any:
    from vnstock import Quote

    try:
        quote = Quote(symbol=symbol, source="kbs")
    except TypeError:
        quote = Quote(symbol=symbol)

    intraday_method = (
        getattr(quote, "intraday", None)
        or getattr(quote, "trades", None)
        or getattr(quote, "time_sales", None)
    )
    if intraday_method is None:
        raise AttributeError("Quote object has no intraday/trades/time_sales method")

    return _call_first_supported(
        intraday_method,
        (
            {"page_size": 10000},
            {"page": 0, "page_size": 10000},
            {"limit": 10000},
            {},
        ),
    )


def _call_legacy_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
) -> Any:
    from vnstock import stock_historical_data

    return _call_first_supported(
        stock_historical_data,
        (
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "resolution": "1D",
                "type": "stock",
                "beautify": True,
            },
            {
                "symbol": symbol,
                "start": start_date,
                "end": end_date,
                "resolution": "1D",
            },
        ),
    )


def _call_legacy_intraday_data(symbol: str) -> Any:
    from vnstock import stock_intraday_data

    return _call_first_supported(
        stock_intraday_data,
        (
            {"symbol": symbol, "page_size": 10000},
            {"ticker": symbol, "page_size": 10000},
            {"symbol": symbol},
            {"ticker": symbol},
        ),
    )


def _call_reference_company_info(symbol: str) -> Any:
    from vnstock import Reference

    ref = Reference()
    company_accessor = getattr(ref, "company")

    if callable(company_accessor):
        company = company_accessor(symbol=symbol)
        return _call_first_supported(company.info, ({"source": "kbs"}, {}))

    return _call_first_supported(
        company_accessor.info,
        ({"symbol": symbol, "source": "kbs"}, {"symbol": symbol}),
    )


def _call_company_overview(symbol: str) -> Any:
    from vnstock import Company

    try:
        company = Company(symbol=symbol, source="kbs")
    except TypeError:
        company = Company(symbol=symbol)
    if hasattr(company, "overview"):
        return company.overview()
    if hasattr(company, "profile"):
        return company.profile()
    raise AttributeError("Company object has neither overview nor profile")


def _call_company_ownership(symbol: str) -> Any:
    """Call the documented KBS company ownership endpoint across API variants."""
    from vnstock import Company

    try:
        company = Company(symbol=symbol, source="kbs")
    except TypeError:
        company = Company(symbol=symbol)
    ownership_method = getattr(company, "ownership", None)
    if ownership_method is None:
        raise AttributeError("Company object has no ownership method")
    return _call_first_supported(ownership_method, ({}, {"symbol": symbol}))


def _call_legacy_company_profile(symbol: str) -> Any:
    from vnstock import company_profile

    return _call_first_supported(
        company_profile,
        ({"symbol": symbol}, {"ticker": symbol}),
    )


def _call_fundamental_ratios(symbol: str) -> Any:
    from vnstock import Fundamental

    equity = Fundamental().equity(symbol=symbol)
    ratio_method = getattr(equity, "ratios", None) or getattr(equity, "ratio")
    return _call_first_supported(
        ratio_method,
        (
            {"period": "year", "orient": "report"},
            {"orient": "report"},
            {"period": "year"},
            {},
        ),
    )


def _call_finance_ratio(symbol: str) -> Any:
    from vnstock import Finance

    try:
        finance = Finance(symbol=symbol, source="kbs")
    except TypeError:
        finance = Finance(symbol=symbol)
    ratio_method = getattr(finance, "ratio", None) or getattr(finance, "ratios")
    return _call_first_supported(
        ratio_method,
        (
            {"period": "year"},
            {"period": "year", "lang": "en"},
            {},
        ),
    )


def _call_legacy_financial_ratio(symbol: str) -> Any:
    from vnstock import financial_ratio

    return _call_first_supported(
        financial_ratio,
        (
            {"symbol": symbol, "report_range": "yearly", "is_all": True},
            {"ticker": symbol, "report_range": "yearly", "is_all": True},
            {"symbol": symbol},
        ),
    )


def _call_first_supported(
    method: Callable[..., Any],
    call_variants: Iterable[Dict[str, Any]],
) -> Any:
    errors: List[str] = []
    for kwargs in call_variants:
        try:
            return method(**kwargs)
        except TypeError as exc:
            errors.append(_short_error(exc))
            continue
    raise TypeError("; ".join(errors) or "no supported call signature")


def _first_non_empty_dataframe(
    attempts: Iterable[Tuple[str, Callable[[], Any]]],
    label: str,
) -> pd.DataFrame:
    errors: List[str] = []
    for name, attempt in attempts:
        try:
            df = _to_dataframe(attempt())
            if not df.empty:
                return df
            errors.append(f"{name}: empty")
        except ImportError as exc:
            errors.append(f"{name}: import failed ({_short_error(exc)})")
        except Exception as exc:
            errors.append(f"{name}: {_short_error(exc)}")

    raise ValueError(f"vnstock {label} attempts failed: {'; '.join(errors)}")


def _normalize_kline_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = _to_dataframe(df)
    if df.empty:
        return _empty_kline_frame()

    work = df.copy()
    if not any(_normalize_key(col) in _KLINE_ALIASES["date"] for col in work.columns):
        if isinstance(work.index, pd.DatetimeIndex):
            work = work.reset_index()

    selected: Dict[str, pd.Series] = {}
    normalized_columns = {_normalize_key(col): col for col in work.columns}
    for target, aliases in _KLINE_ALIASES.items():
        source_col = _resolve_column(normalized_columns, aliases)
        if source_col is not None:
            selected[target] = work[source_col]

    missing = [column for column in KLINE_COLUMNS if column not in selected]
    if missing:
        raise ValueError(f"vnstock OHLCV response missing columns: {missing}")

    normalized = pd.DataFrame(selected, columns=KLINE_COLUMNS)
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=["date", "close"])
    normalized = normalized.sort_values("date").reset_index(drop=True)
    if normalized.empty:
        return _empty_kline_frame()

    return normalized[KLINE_COLUMNS]


def _normalize_intraday_trades(df: pd.DataFrame) -> pd.DataFrame:
    df = _to_dataframe(df)
    if df.empty:
        return pd.DataFrame(columns=["time", "price", "volume", "side"])

    work = df.copy()
    if not any(_normalize_key(col) in _INTRADAY_ALIASES["time"] for col in work.columns):
        if isinstance(work.index, pd.DatetimeIndex):
            work = work.reset_index()

    normalized_columns = {_normalize_key(col): col for col in work.columns}
    selected: Dict[str, Any] = {}
    for target, aliases in _INTRADAY_ALIASES.items():
        source_col = _resolve_column(normalized_columns, aliases)
        if source_col is not None:
            selected[target] = work[source_col]

    if "price" not in selected or "volume" not in selected:
        raise ValueError("vnstock intraday response missing price or volume column")

    result = pd.DataFrame(selected)
    if "time" in result.columns:
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
    else:
        result["time"] = pd.NaT
    result["price"] = pd.to_numeric(result["price"], errors="coerce")
    result["volume"] = pd.to_numeric(result["volume"], errors="coerce")
    if "side" not in result.columns:
        result["side"] = ""
    result["side"] = result["side"].astype(str).map(_normalize_trade_side)

    result = result.dropna(subset=["price", "volume"])
    result = result[result["volume"] > 0]
    if result.empty:
        return pd.DataFrame(columns=["time", "price", "volume", "side"])
    return result.sort_values("time", na_position="first").reset_index(drop=True)


def _normalize_quote_payload(data: Any) -> Dict[str, Any]:
    df = _to_dataframe(data)
    if df.empty:
        return {}

    row = df.iloc[0].to_dict()
    normalized_columns = {_normalize_key(key): key for key in row}
    quote: Dict[str, Any] = {}
    for target, aliases in _QUOTE_ALIASES.items():
        source = _resolve_column(normalized_columns, aliases)
        if source is None:
            continue
        quote[target] = _safe_float(row.get(source))

    quote["raw"] = {
        _snake_key(key): _to_python(value)
        for key, value in row.items()
        if _snake_key(key) and _to_python(value) is not None
    }
    return {key: value for key, value in quote.items() if value is not None}


def _build_intraday_snapshot(
    symbol: str,
    trades: pd.DataFrame,
    quote: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now()
    morning_cutoff = pd.Timestamp.combine(now.date(), datetime.strptime("11:30", "%H:%M").time())

    trading_date = None
    if not trades.empty and trades["time"].notna().any():
        trading_date = trades["time"].dropna().max().date().isoformat()

    total_volume = _safe_float(trades["volume"].sum()) if not trades.empty else None
    morning_trades = trades
    if not trades.empty and trades["time"].notna().any():
        dated_trades = trades[trades["time"].dt.date == now.date()]
        if not dated_trades.empty:
            morning_trades = dated_trades[dated_trades["time"] <= morning_cutoff]
    morning_volume = _safe_float(morning_trades["volume"].sum()) if not morning_trades.empty else None

    latest_price = quote.get("price")
    if latest_price is None and not trades.empty:
        latest_price = _safe_float(trades.iloc[-1].get("price"))

    payload: Dict[str, Any] = {
        "ticker": symbol,
        "market": "VN",
        "source": "vnstock",
        "as_of": now.isoformat(timespec="seconds"),
        "trading_date": trading_date or now.date().isoformat(),
        "latest_price": latest_price,
        "total_volume": total_volume,
        "morning_volume": morning_volume,
        "vwap": _calculate_vwap(trades),
        "price_distribution": _price_distribution(trades),
        "bid_ask_momentum": _bid_ask_momentum(trades, quote),
        "quote": {key: value for key, value in quote.items() if key != "raw"},
    }
    if "raw" in quote:
        payload["quote_raw"] = quote["raw"]
    return {key: value for key, value in payload.items() if value is not None}


def _price_distribution(trades: pd.DataFrame, max_levels: int = 20) -> List[Dict[str, Any]]:
    if trades.empty:
        return []

    grouped = (
        trades.groupby("price", dropna=True)["volume"]
        .sum()
        .sort_values(ascending=False)
        .head(max_levels)
    )
    return [
        {"price": float(price), "volume": float(volume)}
        for price, volume in grouped.sort_index().items()
    ]


def _bid_ask_momentum(trades: pd.DataFrame, quote: Dict[str, Any]) -> Dict[str, Any]:
    momentum: Dict[str, Any] = {
        "bid_price": quote.get("bid_price"),
        "bid_volume": quote.get("bid_volume"),
        "ask_price": quote.get("ask_price"),
        "ask_volume": quote.get("ask_volume"),
    }

    bid_volume = _safe_float(momentum.get("bid_volume")) or 0.0
    ask_volume = _safe_float(momentum.get("ask_volume")) or 0.0
    depth_total = bid_volume + ask_volume
    if depth_total > 0:
        momentum["depth_imbalance"] = round((bid_volume - ask_volume) / depth_total, 6)

    if not trades.empty and "side" in trades.columns:
        buy_volume = _safe_float(trades.loc[trades["side"] == "buy", "volume"].sum()) or 0.0
        sell_volume = _safe_float(trades.loc[trades["side"] == "sell", "volume"].sum()) or 0.0
        side_total = buy_volume + sell_volume
        momentum["buy_volume"] = buy_volume
        momentum["sell_volume"] = sell_volume
        if side_total > 0:
            momentum["trade_imbalance"] = round((buy_volume - sell_volume) / side_total, 6)

    return {key: value for key, value in momentum.items() if value is not None}


def _calculate_vwap(trades: pd.DataFrame) -> Optional[float]:
    if trades.empty:
        return None
    turnover = (trades["price"] * trades["volume"]).sum()
    volume = trades["volume"].sum()
    if volume <= 0:
        return None
    return round(float(turnover / volume), 6)


def _normalize_trade_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "b", "bu", "mua", "bid"} or "buy" in text or "mua" in text:
        return "buy"
    if text in {"sell", "s", "sd", "ban", "ask"} or "sell" in text or "ban" in text:
        return "sell"
    return "unknown" if text else ""


def _flatten_profile(data: Any) -> Dict[str, Any]:
    df = _to_dataframe(data)
    if df.empty:
        return {}

    key_col, value_col = _find_key_value_columns(df)
    if key_col and value_col:
        result = {}
        for _, row in df.iterrows():
            key = _snake_key(row.get(key_col))
            value = _to_python(row.get(value_col))
            if key and value is not None:
                result[key] = value
        return result

    row = df.iloc[0].to_dict()
    return {
        _snake_key(key): _to_python(value)
        for key, value in row.items()
        if _snake_key(key) and _to_python(value) is not None
    }


def _extract_financial_metrics(data: Any) -> Dict[str, Optional[float]]:
    df = _to_dataframe(data)
    if df.empty:
        return {}

    metrics: Dict[str, Optional[float]] = {}
    latest_record = _latest_wide_record(df)
    if latest_record:
        for metric, aliases in _METRIC_ALIASES.items():
            for key, value in latest_record.items():
                if _matches_alias(key, aliases):
                    metrics[metric] = _safe_float(value)
                    break

    item_columns = [
        col
        for col in df.columns
        if _normalize_key(col) in ("item_id", "item", "item_en", "metric", "ratio", "name")
    ]
    period_columns = _period_value_columns(df, item_columns)

    for metric, aliases in _METRIC_ALIASES.items():
        if metrics.get(metric) is not None:
            continue
        for _, row in df.iterrows():
            if not any(_matches_alias(row.get(col), aliases) for col in item_columns):
                continue
            value = _latest_numeric_value(row, period_columns)
            if value is not None:
                metrics[metric] = value
                break

    return {key: value for key, value in metrics.items() if value is not None}


def _latest_wide_record(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}

    work = df.copy()
    date_col = None
    for col in work.columns:
        if _normalize_key(col) in ("date", "time", "period", "year", "report_date"):
            date_col = col
            break

    if date_col is not None:
        sort_values = pd.to_datetime(work[date_col], errors="coerce")
        if sort_values.notna().any():
            work = work.assign(_sort_date=sort_values).sort_values("_sort_date")

    return work.iloc[-1].to_dict()


def _period_value_columns(
    df: pd.DataFrame,
    item_columns: Iterable[Any],
) -> List[Any]:
    item_set = set(item_columns)
    metadata = {
        "item",
        "item_en",
        "item_id",
        "metric",
        "ratio",
        "name",
        "unit",
        "levels",
        "row_number",
        "ticker",
        "symbol",
    }
    candidates = [
        col
        for col in df.columns
        if col not in item_set and _normalize_key(col) not in metadata
    ]
    return sorted(candidates, key=_period_sort_key)


def _latest_numeric_value(row: pd.Series, columns: Iterable[Any]) -> Optional[float]:
    for col in reversed(list(columns)):
        value = _safe_float(row.get(col))
        if value is not None:
            return value
    return None


def _period_sort_key(column: Any) -> Tuple[int, int, str]:
    text = str(column)
    match = re.search(r"(?P<year>20\d{2}|19\d{2})(?:\D*Q?(?P<quarter>[1-4]))?", text)
    if match:
        year = int(match.group("year"))
        quarter = int(match.group("quarter") or 4)
        return year, quarter, text
    return 0, 0, text


def _find_key_value_columns(df: pd.DataFrame) -> Tuple[Optional[Any], Optional[Any]]:
    normalized = {_normalize_key(col): col for col in df.columns}
    key_col = _resolve_column(normalized, ("key", "field", "item", "name", "metric"))
    value_col = _resolve_column(normalized, ("value", "val", "content", "description"))
    if key_col is not None and value_col is not None and len(df) > 1:
        return key_col, value_col
    return None, None


def _pick_by_alias(payload: Dict[str, Any], aliases: Iterable[str]) -> Any:
    for key, value in payload.items():
        if _matches_alias(key, aliases) and value is not None:
            return value
    return None


def _matches_alias(value: Any, aliases: Iterable[str]) -> bool:
    candidate = _normalize_key(value)
    if not candidate:
        return False
    normalized_aliases = {_normalize_key(alias) for alias in aliases}
    compact_candidate = candidate.replace("_", "")
    compact_aliases = {alias.replace("_", "") for alias in normalized_aliases}
    return candidate in normalized_aliases or compact_candidate in compact_aliases


def _resolve_column(
    normalized_columns: Dict[str, Any],
    aliases: Iterable[str],
) -> Optional[Any]:
    for alias in aliases:
        normalized_alias = _normalize_key(alias)
        if normalized_alias in normalized_columns:
            return normalized_columns[normalized_alias]
    return None


def _to_dataframe(data: Any) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, pd.Series):
        return data.to_frame().T
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        for key in ("data", "Data", "result", "results", "rows"):
            if key in data:
                nested = _to_dataframe(data[key])
                if not nested.empty:
                    return nested
        return pd.DataFrame([data])
    return pd.DataFrame()


def _empty_kline_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=KLINE_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _normalize_ticker(ticker: str) -> str:
    text = str(ticker or "").strip().upper()
    if not text:
        return ""
    for prefix in ("HOSE:", "HSX:", "HNX:", "UPCOM:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    if text.endswith(".VN"):
        text = text[:-3]
    return text.strip()


def _coerce_days(days: int) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError):
        logger.warning("Invalid days value for vnstock kline: %r; using 30", days)
        return 30
    return max(1, value)


def _safe_float(value: Any) -> Optional[float]:
    value = _to_python(value)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    try:
        numeric = float(text)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _to_python(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text)
    return text.strip("_")


def _snake_key(value: Any) -> str:
    return _normalize_key(value)


def _short_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return " ".join(message.split())


__all__ = [
    "get_vietnam_kline",
    "get_vietnam_intraday_snapshot",
    "get_vietnam_company_profile",
]
