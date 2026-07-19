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
        return capability in {
            "",
            "daily_data",
            "realtime_quote",
            "stock_name",
            "company_profile",
            "ownership",
            "market_flow",
        }

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
        work = self._scale_thousand_vnd_frame(work)

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

        raw_price = safe_float(snapshot.get("latest_price"))
        if raw_price is None or raw_price <= 0:
            return None

        daily = vn_provider.get_vietnam_kline(symbol, days=30)
        _, price, _quote_scale = self._reconcile_actual_vnd(daily, raw_price)

        quote_payload = snapshot.get("quote") if isinstance(snapshot.get("quote"), dict) else {}
        pre_close = safe_float(quote_payload.get("reference_price"))
        pre_close = self._normalize_related_quote_price(pre_close, price)
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
        profile = self.get_company_profile(stock_code)
        return profile.get("company_name") or profile.get("name") or symbol

    def get_company_profile(self, stock_code: str) -> dict:
        """Return Vietnam company profile and valuation ratios."""
        symbol = self._local_symbol(stock_code)
        return vn_provider.get_vietnam_company_profile(symbol) if symbol else {}

    def get_ownership_structure(self, stock_code: str) -> dict:
        """Return disclosed ownership records; never label them as order flow."""
        symbol = self._local_symbol(stock_code)
        return vn_provider.get_vietnam_ownership_snapshot(symbol) if symbol else {}

    def get_market_flow(self, stock_code: str) -> dict:
        """Return active order flow and optional sponsor-backed investor flow."""
        from src.config import get_config

        symbol = self._local_symbol(stock_code)
        if not symbol:
            return {}
        include_advanced = bool(getattr(get_config(), "enable_vn_advanced_flow", False))
        return vn_provider.get_vietnam_market_flow_snapshot(
            symbol,
            include_advanced=include_advanced,
        )

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

        # vnstock endpoints do not consistently use the same price unit. Daily
        # OHLC can be actual VND (for example 56,000), while the live quote is
        # expressed in thousand VND (56.6). Reconcile overlapping sources and
        # scale the smaller one upward so every downstream value is actual VND.
        work, price, _ = cls._reconcile_actual_vnd(work, price)

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
    def _reconcile_actual_vnd(
        daily: pd.DataFrame,
        quote_price: float,
    ) -> tuple[pd.DataFrame, float, float]:
        """Reconcile daily and quote prices into actual VND.

        Vietnamese providers legitimately expose prices in either VND or
        thousand VND. A factor close to 1,000 is a clear unit mismatch. The
        lower-valued source is therefore scaled upward; normal price movement
        remains untouched. The returned multiplier records the live-price
        conversion only; related snapshot fields are reconciled independently
        because one provider response can mix units.
        """
        if quote_price <= 0:
            return daily, quote_price, 1.0

        # A live quote can remain available when the daily-history endpoint is
        # degraded. vnstock/KBS live equity prices below 1,000 use the market's
        # thousand-VND display convention, so preserve actual-VND output even
        # without a daily close to use as the reconciliation anchor.
        if daily.empty:
            if quote_price < 1000:
                return daily, quote_price * 1000.0, 1000.0
            return daily, quote_price, 1.0

        last_close = safe_float(daily.iloc[-1].get("close"))
        if last_close is None or last_close <= 0:
            if quote_price < 1000:
                return daily, quote_price * 1000.0, 1000.0
            return daily, quote_price, 1.0

        # The vnstock/KBS equity endpoints expose both OHLC and live quotes in
        # thousand-VND units (for example 56.6 for 56,600 VND). When both
        # sources use that documented market convention there is no 1,000x
        # mismatch to detect, so normalize the pair explicitly here.
        if last_close < 1000 and quote_price < 1000:
            aligned = VnFetcher._scale_thousand_vnd_frame(daily)
            logger.info("Normalized Vietnam market prices from thousand VND to actual VND")
            return aligned, quote_price * 1000.0, 1000.0

        ratio = last_close / quote_price
        if 900 <= ratio <= 1100:
            logger.warning(
                "Normalized Vietnam live quote from thousand VND to VND (ratio %.2f)",
                ratio,
            )
            return daily, quote_price * 1000.0, 1000.0

        inverse_ratio = quote_price / last_close
        if 900 <= inverse_ratio <= 1100:
            aligned = daily.copy()
            for column in ("open", "high", "low", "close", "amount"):
                if column in aligned.columns:
                    aligned[column] = pd.to_numeric(aligned[column], errors="coerce") * 1000.0
            logger.warning(
                "Normalized Vietnam daily prices from thousand VND to VND (ratio %.2f)",
                inverse_ratio,
            )
            return aligned, quote_price, 1.0

        return daily, quote_price, 1.0

    @staticmethod
    def _normalize_related_quote_price(value: Optional[float], actual_price: float) -> Optional[float]:
        """Align a snapshot reference price to an already normalized live price.

        Some VN quote payloads mix units within one response: ``latest_price``
        may use thousand VND while ``reference_price`` is already actual VND.
        Scale only the related field that is still below 1,000 when the live
        price has already been normalized to actual VND.
        """
        if value is None or value <= 0:
            return value
        if actual_price >= 1000 and value < 1000:
            return value * 1000.0
        return value

    @staticmethod
    def _scale_thousand_vnd_frame(daily: pd.DataFrame) -> pd.DataFrame:
        """Convert a vnstock/KBS price frame from thousand VND to VND once."""
        if daily is None or daily.empty or "close" not in daily.columns:
            return daily
        closes = pd.to_numeric(daily["close"], errors="coerce").dropna()
        if closes.empty or float(closes.median()) >= 1000:
            return daily
        aligned = daily.copy()
        for column in ("open", "high", "low", "close", "amount"):
            if column in aligned.columns:
                aligned[column] = pd.to_numeric(aligned[column], errors="coerce") * 1000.0
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
