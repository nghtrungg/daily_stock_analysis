# -*- coding: utf-8 -*-
"""Regression tests for Vietnam `.VN` market routing."""

from unittest.mock import patch

import pandas as pd

from data_provider.base import BaseFetcher, DataFetchError, DataFetcherManager, normalize_stock_code
from data_provider.vn_fetcher import VnFetcher
from data_provider.vn_provider import _normalize_kline_frame, get_vietnam_ownership_snapshot
from src.core.trading_calendar import (
    MARKET_TIMEZONE,
    MarketPhase,
    get_effective_trading_date,
    get_market_for_stock,
    infer_market_phase,
    is_market_open,
)
from src.market_context import detect_market, get_market_guidelines
from src.services.stock_code_utils import is_code_like, normalize_code


class _FakeFetcher(BaseFetcher):
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.priority = 0 if name != "VnFetcher" else 4
        self.calls = []
        self.should_fail = should_fail

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise NotImplementedError

    def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
        self.calls.append(stock_code)
        if self.should_fail:
            raise DataFetchError(f"{self.name} should not be called for {stock_code}")
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-07-08")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
                "amount": [100000.0],
                "pct_chg": [0.0],
            }
        )


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-07"), pd.Timestamp("2026-07-08")],
            "open": [95.0, 100.0],
            "high": [101.0, 103.0],
            "low": [94.0, 98.0],
            "close": [100.0, 102.0],
            "volume": [1000, 1100],
        }
    )


def test_normalize_and_detect_vn_suffix_codes() -> None:
    assert normalize_stock_code("fpt.vn") == "FPT.VN"
    assert normalize_code("vnm.vn") == "VNM.VN"
    assert is_code_like("HPG.VN") is True

    assert detect_market("FPT.VN") == "vn"
    assert get_market_for_stock("FPT.VN") == "vn"
    assert get_market_for_stock("FPT") == "us"
    assert MARKET_TIMEZONE["vn"] == "Asia/Ho_Chi_Minh"


def test_market_guidelines_for_vn_keep_vietnam_context() -> None:
    guidelines = get_market_guidelines("FPT.VN", lang="en")

    assert "Vietnam stock" in guidelines
    assert "VND" in guidelines
    assert "Northbound flows" in guidelines


def test_vietnam_calendar_uses_hose_weekday_sessions_without_exchange_calendars() -> None:
    tz = "Asia/Ho_Chi_Minh"

    assert is_market_open("vn", pd.Timestamp("2026-07-10").date()) is True
    assert is_market_open("vn", pd.Timestamp("2026-07-11").date()) is False
    assert infer_market_phase("vn", pd.Timestamp("2026-07-10 09:00", tz=tz)) == MarketPhase.INTRADAY
    assert infer_market_phase("vn", pd.Timestamp("2026-07-10 11:30", tz=tz)) == MarketPhase.LUNCH_BREAK
    assert infer_market_phase("vn", pd.Timestamp("2026-07-10 14:30", tz=tz)) == MarketPhase.CLOSING_AUCTION
    assert infer_market_phase("vn", pd.Timestamp("2026-07-10 14:45", tz=tz)) == MarketPhase.POSTMARKET
    assert get_effective_trading_date("vn", pd.Timestamp("2026-07-10 14:44", tz=tz)) == pd.Timestamp("2026-07-09").date()
    assert get_effective_trading_date("vn", pd.Timestamp("2026-07-10 14:45", tz=tz)) == pd.Timestamp("2026-07-10").date()


def test_data_fetcher_manager_routes_vn_daily_only_to_vn_fetcher() -> None:
    efinance = _FakeFetcher("EfinanceFetcher", should_fail=True)
    akshare = _FakeFetcher("AkshareFetcher", should_fail=True)
    yfinance = _FakeFetcher("YfinanceFetcher", should_fail=True)
    vn = _FakeFetcher("VnFetcher")
    manager = DataFetcherManager(fetchers=[efinance, akshare, yfinance, vn])

    with patch("data_provider.base.record_provider_run_started"), patch("data_provider.base.record_provider_run"):
        df, source = manager.get_daily_data("fpt.vn")

    assert source == "VnFetcher"
    assert not df.empty
    assert efinance.calls == []
    assert akshare.calls == []
    assert yfinance.calls == []
    assert vn.calls == ["FPT.VN"]


def test_default_provider_filter_disables_non_vietnam_market_fetchers() -> None:
    cn = _FakeFetcher("EfinanceFetcher")
    us = _FakeFetcher("FinnhubFetcher")
    vn = _FakeFetcher("VnFetcher")

    enabled = DataFetcherManager._filter_fetchers_for_enabled_markets(
        [cn, us, vn], {"vn"}
    )

    assert [fetcher.name for fetcher in enabled] == ["VnFetcher"]


def test_vn_fetcher_strips_suffix_and_merges_active_intraday_bar_before_indicators() -> None:
    snapshot = {
        "ticker": "FPT",
        "trading_date": "2026-07-09",
        "latest_price": 110.0,
        "total_volume": 1500,
        "quote": {"reference_price": 102.0},
        "as_of": "2026-07-09T10:15:00",
    }

    with patch("data_provider.vn_fetcher.vn_provider.get_vietnam_kline", return_value=_daily_frame()) as kline, patch(
        "data_provider.vn_fetcher.vn_provider.get_vietnam_intraday_snapshot",
        return_value=snapshot,
    ) as intraday:
        df = VnFetcher().get_daily_data("FPT.VN", start_date="2026-07-01", end_date="2026-07-09")

    kline.assert_called_once()
    assert kline.call_args.kwargs["days"] == 9
    intraday.assert_called_once_with("FPT")
    assert list(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"))[-1] == "2026-07-09"
    assert float(df.iloc[-1]["close"]) == 110.0
    assert float(df.iloc[-1]["volume"]) == 1500.0
    assert float(df.iloc[-1]["amount"]) == 165000.0
    assert "ma5" in df.columns


def test_vn_fetcher_normalizes_vnd_daily_bars_to_live_quote_unit() -> None:
    daily = _daily_frame()
    daily[["open", "high", "low", "close"]] *= 1000
    snapshot = {
        "ticker": "VNM",
        "trading_date": "2026-07-09",
        "latest_price": 102.0,
        "total_volume": 1500,
        "quote": {"reference_price": 100.0},
    }

    with patch("data_provider.vn_fetcher.vn_provider.get_vietnam_kline", return_value=daily), patch(
        "data_provider.vn_fetcher.vn_provider.get_vietnam_intraday_snapshot", return_value=snapshot
    ):
        df = VnFetcher().get_daily_data("VNM.VN", start_date="2026-07-01", end_date="2026-07-09")

    assert float(df.iloc[0]["open"]) == 95.0
    assert float(df.iloc[-2]["close"]) == 102.0
    assert float(df.iloc[-1]["open"]) == 102.0
    assert float(df.iloc[-1]["pct_chg"]) == 0.0


def test_vn_kline_normalization_uses_date_column_without_ambiguous_index() -> None:
    normalized = _normalize_kline_frame(_daily_frame())

    assert normalized.index.name is None
    assert isinstance(normalized.index, pd.RangeIndex)
    assert list(normalized.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_vn_fetcher_accepts_date_as_both_column_and_index_from_provider() -> None:
    provider_frame = _daily_frame().set_index("date", drop=False)

    with patch("data_provider.vn_fetcher.vn_provider.get_vietnam_kline", return_value=provider_frame), patch(
        "data_provider.vn_fetcher.vn_provider.get_vietnam_intraday_snapshot",
        return_value={},
    ):
        df = VnFetcher().get_daily_data("FPT.VN", start_date="2026-07-01", end_date="2026-07-09")

    assert len(df) == 2
    assert list(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")) == ["2026-07-07", "2026-07-08"]
    assert "ma5" in df.columns


def test_vn_realtime_quote_uses_stripped_symbol() -> None:
    snapshot = {
        "ticker": "VNM",
        "trading_date": "2026-07-09",
        "latest_price": 88.0,
        "total_volume": 2000,
        "quote": {"reference_price": 80.0},
        "as_of": "2026-07-09T10:15:00",
    }

    with patch(
        "data_provider.vn_fetcher.vn_provider.get_vietnam_intraday_snapshot",
        return_value=snapshot,
    ) as intraday:
        quote = VnFetcher().get_realtime_quote("VNM.VN")

    intraday.assert_called_once_with("VNM")
    assert quote is not None
    assert quote.code == "VNM.VN"
    assert quote.market == "vn"
    assert quote.currency == "VND"
    assert quote.price == 88.0
    assert quote.volume == 2000


def test_vn_ownership_snapshot_preserves_disclosed_provider_records() -> None:
    raw = pd.DataFrame(
        [{"Shareholder Name": "Example Fund", "Ownership Percent": 12.5, "Holder Type": "Institution"}]
    )

    with patch("data_provider.vn_provider._call_company_ownership", return_value=raw):
        snapshot = get_vietnam_ownership_snapshot("VNM")

    assert snapshot["ticker"] == "VNM"
    assert snapshot["source"] == "vnstock"
    assert snapshot["record_count"] == 1
    assert snapshot["records"][0]["shareholder_name"] == "Example Fund"
    assert snapshot["records"][0]["ownership_percent"] == 12.5


def test_data_fetcher_manager_exposes_vn_ownership_separately_from_chip_data() -> None:
    class _OwnershipFetcher(_FakeFetcher):
        def get_ownership_structure(self, stock_code):
            self.calls.append(stock_code)
            return {"records": [{"shareholder_name": "Example Fund"}]}

    vn = _OwnershipFetcher("VnFetcher")
    manager = DataFetcherManager(fetchers=[vn])

    ownership = manager.get_ownership_structure("VNM.VN")

    assert ownership["records"][0]["shareholder_name"] == "Example Fund"
    assert vn.calls == ["VNM.VN"]


def test_vn_is_first_class_on_write_paths() -> None:
    from src.services.decision_signal_service import DecisionSignalService
    from src.services.intelligence_service import _ALLOWED_MARKETS
    from src.services.portfolio_service import VALID_MARKETS

    assert DecisionSignalService._normalize_market("vn") == "vn"
    assert "vn" in VALID_MARKETS
    assert "vn" in _ALLOWED_MARKETS
