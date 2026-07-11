# -*- coding: utf-8 -*-
"""Vietnam market fetcher adapter for the repository data-provider pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from . import vn_provider
from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import UnifiedRealtimeQuote, safe_float, safe_int
from src.services.market_symbol_utils import is_vn_market_symbol, vn_market_base_symbol

logger = logging.getLogger(__name__)


class _VnstockRealtimeSource:
    value = "vnstock"


_VNSTOCK_SOURCE = _VnstockRealtimeSource()


class VnFetcher(BaseFetcher):
    """Fetch Vietnamese daily and live snapshot data through ``vn_provider``."""

    name = "VnFetcher"
    priority = 4

    def is_available_for_request(self, capability: str = "") -> bool:
        return capability in {"", "daily_data", "realtime_quote", "stock_name", "ownership"}

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        symbol = self._local_symbol(stock_code)
        if not symbol:
            raise DataFetchError(f"{stock_code} is not a Vietnam stock symbol")

        days = self._lookback_days(start_date, end_date)
        daily = vn_provider.get_vietnam_kline(symbol, days=days)
        if daily is None or daily.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)
        return self._merge_intraday_snapshot(daily, vn_provider.get_vietnam_intraday_snapshot(symbol))

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        work = self._ensure_date_column_frame(df)

        for column in ("amount", "pct_chg"):
            if column not in work.columns:
                work[column] = 0.0

        normalized = work[[column for column in STANDARD_COLUMNS if column in work.columns]].copy()
        for column in STANDARD_COLUMNS:
            if column not in normalized.columns:
                normalized[column] = 0.0
        return normalized[STANDARD_COLUMNS]

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        symbol = self._local_symbol(stock_code)
        if not symbol:
            return None

        snapshot = vn_provider.get_vietnam_intraday_snapshot(symbol)
        if not snapshot:
            return None

        price = safe_float(snapshot.get("latest_price"))
        if price is None or price <= 0:
            return None

        quote_payload = snapshot.get("quote") if isinstance(snapshot.get("quote"), dict) else {}
        pre_close = safe_float(quote_payload.get("reference_price"))
        volume = safe_int(snapshot.get("total_volume") or snapshot.get("morning_volume"))
        amount = price * volume if volume is not None else None
        change_amount = price - pre_close if pre_close and pre_close > 0 else None
        change_pct = (change_amount / pre_close * 100) if change_amount is not None and pre_close else None

        return UnifiedRealtimeQuote(
            code=f"{symbol}.VN",
            name=str(snapshot.get("name") or symbol),
            source=_VNSTOCK_SOURCE,
            market="vn",
            currency="VND",
            data_quality="partial" if snapshot.get("errors") else "ok",
            price=price,
            change_pct=change_pct,
            change_amount=change_amount,
            volume=volume,
            amount=amount,
            open_price=pre_close,
            high=price,
            low=price,
            pre_close=pre_close,
            provider_timestamp=snapshot.get("as_of"),
        )

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        symbol = self._local_symbol(stock_code)
        if not symbol:
            return None
        profile = vn_provider.get_vietnam_company_profile(symbol)
        return profile.get("company_name") or profile.get("name") or symbol

    def get_ownership_structure(self, stock_code: str) -> dict:
        """Return disclosed ownership records; never label them as order flow."""
        symbol = self._local_symbol(stock_code)
        return vn_provider.get_vietnam_ownership_snapshot(symbol) if symbol else {}

    @staticmethod
    def _local_symbol(stock_code: str) -> str:
        if not is_vn_market_symbol(stock_code):
            return ""
        return vn_market_base_symbol(stock_code)

    @staticmethod
    def _lookback_days(start_date: str, end_date: str) -> int:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return 30
        return max(1, (end - start).days + 1)

    @classmethod
    def _merge_intraday_snapshot(cls, daily: pd.DataFrame, snapshot: dict[str, Any]) -> pd.DataFrame:
        if not snapshot:
            return daily

        price = safe_float(snapshot.get("latest_price"))
        if price is None or price <= 0:
            return daily

        trading_date = pd.to_datetime(snapshot.get("trading_date"), errors="coerce")
        if pd.isna(trading_date):
            return daily
        trading_day = trading_date.normalize()

        work = cls._ensure_date_column_frame(daily)
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        work = work.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
        if work.empty:
            return daily

        # vnstock endpoints do not consistently use the same price unit.  Some
        # daily OHLC responses are in VND (for example 55,700), while the live
        # quote for the same instrument is expressed in thousand VND (56.5).
        # Compare overlapping sources instead of applying a ticker- or
        # threshold-based conversion, then normalize the full OHLC history
        # before indicators and the active bar are calculated.
        work = cls._align_daily_price_unit(work, price)

        volume = safe_float(snapshot.get("total_volume") or snapshot.get("morning_volume")) or 0.0
        last_close = safe_float(work.iloc[-1].get("close")) or price
        prior_rows = work[work["date"].dt.normalize() < trading_day]
        previous_close = safe_float(prior_rows.iloc[-1].get("close")) if not prior_rows.empty else last_close
        pct_chg = ((price - previous_close) / previous_close * 100) if previous_close and previous_close > 0 else 0.0
        amount = price * volume if volume else 0.0

        same_day = work["date"].dt.normalize() == trading_day
        if same_day.any():
            idx = work.index[same_day][-1]
            open_price = safe_float(work.loc[idx].get("open")) or previous_close or price
            existing_high = safe_float(work.loc[idx].get("high")) or price
            existing_low = safe_float(work.loc[idx].get("low")) or price
            work.loc[idx, "open"] = open_price
            work.loc[idx, "high"] = max(existing_high, price, open_price)
            work.loc[idx, "low"] = min(existing_low, price, open_price)
            work.loc[idx, "close"] = price
            if volume:
                work.loc[idx, "volume"] = volume
                work.loc[idx, "amount"] = amount
            work.loc[idx, "pct_chg"] = pct_chg
            return work

        open_price = previous_close or price
        active_row = {
            "date": trading_day,
            "open": open_price,
            "high": max(open_price, price),
            "low": min(open_price, price),
            "close": price,
            "volume": volume,
            "amount": amount,
            "pct_chg": pct_chg,
        }
        return pd.concat([work, pd.DataFrame([active_row])], ignore_index=True)

    @staticmethod
    def _align_daily_price_unit(daily: pd.DataFrame, quote_price: float) -> pd.DataFrame:
        """Align daily OHLC prices to a live quote when they differ by 1,000x.

        Vietnamese providers legitimately expose prices in either VND or
        thousand VND.  A factor close to 1,000 is a clear unit mismatch; other
        differences are normal price movement and must remain untouched.
        """
        if quote_price <= 0 or daily.empty:
            return daily

        last_close = safe_float(daily.iloc[-1].get("close"))
        if last_close is None or last_close <= 0:
            return daily

        ratio = last_close / quote_price
        if not 900 <= ratio <= 1100:
            return daily

        aligned = daily.copy()
        for column in ("open", "high", "low", "close"):
            if column in aligned.columns:
                aligned[column] = pd.to_numeric(aligned[column], errors="coerce") / 1000.0
        logger.warning(
            "Normalized Vietnam daily OHLC from VND to thousand VND to match live quote (ratio %.2f)",
            ratio,
        )
        return aligned

    @staticmethod
    def _ensure_date_column_frame(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure a ``date`` column is not also retained as an index level."""
        work = df.copy()
        if work.index.name == "date" and "date" in work.columns:
            return work.reset_index(drop=True)
        if "date" not in work.columns and isinstance(work.index, pd.DatetimeIndex):
            return work.reset_index()
        return work
