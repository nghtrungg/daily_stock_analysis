# -*- coding: utf-8 -*-
"""
===================================
交易日历模块 (Issue #373 / Issue #1386 P0)
===================================

职责：
1. 按市场（A股/港股/美股/日股/韩股/台股）判断当日是否为交易日
2. 按市场时区取“今日”日期，避免服务器 UTC 导致日期错误
3. 支持 per-stock 过滤：只分析当日开市市场的股票
4. 提供 regular-session 市场阶段推断基线，不改变现有分析入口行为

依赖：exchange-calendars（可选，交易日判断不可用时 fail-open，阶段推断不可用时 unknown）
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from src.services.market_symbol_utils import get_suffix_market, is_vn_market_symbol

logger = logging.getLogger(__name__)

# Exchange-calendars availability
_XCALS_AVAILABLE = False
try:
    import exchange_calendars as xcals
    _XCALS_AVAILABLE = True
except ImportError:
    logger.warning(
        "exchange-calendars not installed; trading day check disabled. "
        "Run: pip install exchange-calendars"
    )

# Market -> exchange code (exchange-calendars). Vietnam has no supported
# exchange-calendars identifier, so its regular HOSE session is handled below.
MARKET_EXCHANGE = {"cn": "XSHG", "hk": "XHKG", "us": "XNYS", "jp": "XTKS", "kr": "XKRX", "tw": "XTAI", "vn": None}

# Market -> IANA timezone for "today"
MARKET_TIMEZONE = {
    "cn": "Asia/Shanghai",
    "hk": "Asia/Hong_Kong",
    "us": "America/New_York",
    "jp": "Asia/Tokyo",
    "kr": "Asia/Seoul",
    "tw": "Asia/Taipei",
    "vn": "Asia/Ho_Chi_Minh",
}

# P0 market phase baseline (Issue #1386). This is an intentionally small
# regular-session inference layer; it does not change existing fail-open
# trading-day filtering or effective-date behavior.
# tw: TWSE/TPEx run a 13:25-13:30 closing call auction (5 min). JP/KR use
# regular-session closing auction windows before the 15:30 close (JP 5 min,
# KR 10 min). Without an entry here .get(market, 0) yields a zero-width
# window, so the last regular-session minutes stay INTRADAY until POSTMARKET.
_CLOSING_AUCTION_WINDOW_MINUTES = {
    "cn": 3,
    "hk": 10,
    "us": 5,
    "jp": 5,
    "kr": 10,
    "tw": 5,
    "vn": 15,
}

# HOSE listed-stock sessions published by HOSE: 09:00-11:30 and 13:00-14:45,
# with the 14:30-14:45 closing call auction. This is a weekday session baseline;
# exchange holidays remain a future calendar-data integration.
_VN_OPEN_TIME = time(9, 0)
_VN_BREAK_START = time(11, 30)
_VN_BREAK_END = time(13, 0)
_VN_CLOSE_TIME = time(14, 45)
_VN_ESTIMATED_SELLABLE_TIME = time(13, 0)
_VN_CALENDAR_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "config" / "market_calendars" / "vn"
)
VN_SETTLEMENT_POLICY_VERSION = "vn-equity-t2-2022-08-29"
_SUPPORTED_ANALYSIS_PHASES = {
    "auto",
    "premarket",
    "intraday",
    "postmarket",
}


class MarketPhase(str, Enum):
    """Regular-session market phase labels for Issue #1386 P0."""

    PREMARKET = "premarket"
    INTRADAY = "intraday"
    LUNCH_BREAK = "lunch_break"
    CLOSING_AUCTION = "closing_auction"
    POSTMARKET = "postmarket"
    NON_TRADING = "non_trading"
    UNKNOWN = "unknown"


class VNCalendarCoverage(str, Enum):
    """Quality of the bundled calendar data for one year."""

    CONFIRMED = "confirmed"
    MISSING = "missing"
    MALFORMED = "malformed"


class VNCalendarDayClassification(str, Enum):
    """Trading and settlement state for one Vietnam-local date."""

    TRADING_AND_SETTLEMENT_DAY = "trading_and_settlement_day"
    TRADING_DAY = "trading_day"
    SETTLEMENT_DAY = "settlement_day"
    NON_TRADING_CLOSURE = "non_trading_closure"
    SETTLEMENT_ONLY_CLOSURE = "settlement_only_closure"
    WEEKEND = "weekend"
    UNKNOWN = "unknown"


class SettlementCalculationStatus(str, Enum):
    CONFIRMED = "confirmed"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VNCalendarYear:
    year: int
    calendar_version: str
    trading_closures: frozenset[date]
    settlement_closures: frozenset[date]
    coverage: VNCalendarCoverage
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VNCalendarDay:
    calendar_date: date
    is_trading_day: bool
    is_settlement_day: bool
    classification: VNCalendarDayClassification
    coverage: VNCalendarCoverage
    calendar_version: str
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SettlementCalculationResult:
    trade_date: date
    settlement_date: date
    estimated_sellable_at: datetime
    calendar_version: str
    policy_version: str
    calculation_status: SettlementCalculationStatus
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "settlement_date": self.settlement_date.isoformat(),
            "estimated_sellable_at": self.estimated_sellable_at.isoformat(),
            "calendar_version": self.calendar_version,
            "policy_version": self.policy_version,
            "calculation_status": self.calculation_status.value,
            "warnings": list(self.warnings),
        }


@dataclass
class MarketPhaseContext:
    """Runtime market-phase context for stock analysis plumbing."""

    market: Optional[str]
    phase: MarketPhase
    market_local_time: datetime
    session_date: date
    effective_daily_bar_date: date
    is_trading_day: Optional[bool]
    is_market_open_now: Optional[bool]
    is_partial_bar: Optional[bool]
    minutes_to_open: Optional[int] = None
    minutes_to_close: Optional[int] = None
    trigger_source: str = "system"
    analysis_intent: str = "auto"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe representation for runtime context passing."""
        return {
            "market": self.market,
            "phase": self.phase.value,
            "market_local_time": self.market_local_time.isoformat(),
            "session_date": self.session_date.isoformat(),
            "effective_daily_bar_date": self.effective_daily_bar_date.isoformat(),
            "is_trading_day": self.is_trading_day,
            "is_market_open_now": self.is_market_open_now,
            "is_partial_bar": self.is_partial_bar,
            "minutes_to_open": self.minutes_to_open,
            "minutes_to_close": self.minutes_to_close,
            "trigger_source": self.trigger_source,
            "analysis_intent": self.analysis_intent,
            "warnings": list(self.warnings),
        }


def _parse_vn_calendar_dates(values: Any, *, year: int, field_name: str) -> frozenset[date]:
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    parsed = set()
    for value in values:
        parsed_date = date.fromisoformat(str(value))
        if parsed_date.year != year:
            raise ValueError(f"{field_name} contains a date outside {year}")
        parsed.add(parsed_date)
    return frozenset(parsed)


def load_vn_calendar_year(
    year: int,
    *,
    calendar_directory: Optional[Path] = None,
) -> VNCalendarYear:
    """Load and validate one versioned Vietnam calendar year."""
    directory = Path(calendar_directory or _VN_CALENDAR_DIRECTORY)
    calendar_path = directory / f"{int(year)}.json"
    if not calendar_path.is_file():
        return VNCalendarYear(
            year=int(year),
            calendar_version=f"vn-{int(year)}-weekend-only",
            trading_closures=frozenset(),
            settlement_closures=frozenset(),
            coverage=VNCalendarCoverage.MISSING,
            warnings=(f"calendar_year_missing:{int(year)}",),
        )

    try:
        payload = json.loads(calendar_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("calendar root must be an object")
        if payload.get("market") != "vn":
            raise ValueError("market must be 'vn'")
        if int(payload.get("year")) != int(year):
            raise ValueError("calendar year does not match filename")
        if payload.get("timezone") != MARKET_TIMEZONE["vn"]:
            raise ValueError("calendar timezone must be Asia/Ho_Chi_Minh")
        calendar_version = str(payload.get("calendar_version") or "").strip()
        if not calendar_version:
            raise ValueError("calendar_version is required")
        trading_closures = _parse_vn_calendar_dates(
            payload.get("trading_closures"),
            year=int(year),
            field_name="trading_closures",
        )
        settlement_closures = _parse_vn_calendar_dates(
            payload.get("settlement_closures"),
            year=int(year),
            field_name="settlement_closures",
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Malformed Vietnam calendar %s: %s", calendar_path, exc)
        return VNCalendarYear(
            year=int(year),
            calendar_version=f"vn-{int(year)}-malformed-weekend-only",
            trading_closures=frozenset(),
            settlement_closures=frozenset(),
            coverage=VNCalendarCoverage.MALFORMED,
            warnings=(f"calendar_year_malformed:{int(year)}",),
        )

    return VNCalendarYear(
        year=int(year),
        calendar_version=calendar_version,
        trading_closures=trading_closures,
        settlement_closures=settlement_closures,
        coverage=VNCalendarCoverage.CONFIRMED,
    )


def get_vn_calendar_day(
    check_date: date,
    *,
    calendar_directory: Optional[Path] = None,
) -> VNCalendarDay:
    """Return independent trading and settlement state for a Vietnam date."""
    calendar = load_vn_calendar_year(
        check_date.year,
        calendar_directory=calendar_directory,
    )
    is_weekend = check_date.weekday() >= 5
    trading_closed = is_weekend or check_date in calendar.trading_closures
    settlement_closed = is_weekend or check_date in calendar.settlement_closures
    is_trading_day = not trading_closed
    is_settlement_day = not settlement_closed

    if is_weekend:
        classification = VNCalendarDayClassification.WEEKEND
    elif calendar.coverage != VNCalendarCoverage.CONFIRMED:
        classification = VNCalendarDayClassification.UNKNOWN
    elif trading_closed and settlement_closed:
        classification = VNCalendarDayClassification.NON_TRADING_CLOSURE
    elif settlement_closed:
        classification = VNCalendarDayClassification.SETTLEMENT_ONLY_CLOSURE
    elif trading_closed:
        classification = VNCalendarDayClassification.SETTLEMENT_DAY
    else:
        classification = VNCalendarDayClassification.TRADING_AND_SETTLEMENT_DAY

    return VNCalendarDay(
        calendar_date=check_date,
        is_trading_day=is_trading_day,
        is_settlement_day=is_settlement_day,
        classification=classification,
        coverage=calendar.coverage,
        calendar_version=calendar.calendar_version,
        warnings=calendar.warnings,
    )


def calculate_vn_settlement(
    trade_time: datetime,
    *,
    settlement_sessions: int = 2,
    calendar_directory: Optional[Path] = None,
) -> SettlementCalculationResult:
    """Calculate a Vietnam equity settlement estimate from settlement sessions."""
    if isinstance(settlement_sessions, bool) or settlement_sessions < 0:
        raise ValueError("settlement_sessions must be a non-negative integer")
    if not isinstance(settlement_sessions, int):
        raise TypeError("settlement_sessions must be an integer")
    if not isinstance(trade_time, datetime):
        raise TypeError("trade_time must be a datetime")

    local_trade_time = get_market_now("vn", current_time=trade_time)
    trade_date = local_trade_time.date()
    warnings: List[str] = []
    versions: List[str] = []
    coverages: List[VNCalendarCoverage] = []

    def observe(calendar_day: VNCalendarDay) -> None:
        if calendar_day.calendar_version not in versions:
            versions.append(calendar_day.calendar_version)
        coverages.append(calendar_day.coverage)
        for warning in calendar_day.warnings:
            _add_warning_code(warnings, warning)

    trade_calendar_day = get_vn_calendar_day(
        trade_date,
        calendar_directory=calendar_directory,
    )
    observe(trade_calendar_day)
    if not trade_calendar_day.is_trading_day:
        _add_warning_code(warnings, "trade_date_not_trading_day")

    settlement_date = trade_date
    remaining_sessions = settlement_sessions
    while remaining_sessions:
        settlement_date += timedelta(days=1)
        calendar_day = get_vn_calendar_day(
            settlement_date,
            calendar_directory=calendar_directory,
        )
        observe(calendar_day)
        if calendar_day.is_settlement_day:
            remaining_sessions -= 1

    if VNCalendarCoverage.MALFORMED in coverages or not trade_calendar_day.is_trading_day:
        status = SettlementCalculationStatus.UNKNOWN
    elif VNCalendarCoverage.MISSING in coverages:
        status = SettlementCalculationStatus.DEGRADED
    else:
        status = SettlementCalculationStatus.CONFIRMED

    sellable_at = datetime.combine(
        settlement_date,
        _VN_ESTIMATED_SELLABLE_TIME,
        tzinfo=ZoneInfo(MARKET_TIMEZONE["vn"]),
    )
    return SettlementCalculationResult(
        trade_date=trade_date,
        settlement_date=settlement_date,
        estimated_sellable_at=sellable_at,
        calendar_version="+".join(versions),
        policy_version=VN_SETTLEMENT_POLICY_VERSION,
        calculation_status=status,
        warnings=tuple(warnings),
    )


def get_market_for_stock(code: str) -> Optional[str]:
    """
    Infer market region for a stock code.

    Returns:
        'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw' | None (None = unrecognized, fail-open: treat as open)
    """
    if not code or not isinstance(code, str):
        return None
    code = (code or "").strip().upper()

    from data_provider import is_us_stock_code, is_us_index_code, is_hk_stock_code

    if is_vn_market_symbol(code):
        return "vn"
    if is_us_stock_code(code) or is_us_index_code(code):
        return "us"
    if is_hk_stock_code(code):
        return "hk"
    suffix_market = get_suffix_market(code)
    if suffix_market:
        return suffix_market
    # A-share: 6-digit numeric
    if code.isdigit() and len(code) == 6:
        return "cn"
    return None


def is_market_open(market: str, check_date: date) -> bool:
    """
    Check if the given market is open on the given date.

    Fail-open: returns True if exchange-calendars unavailable or date out of range.

    Args:
        market: 'cn' | 'hk' | 'us'
        check_date: Date to check

    Returns:
        True if trading day (or fail-open), False otherwise
    """
    if market == "vn":
        return get_vn_calendar_day(check_date).is_trading_day
    if not _XCALS_AVAILABLE:
        return True
    ex = MARKET_EXCHANGE.get(market)
    if not ex:
        return True
    try:
        cal = xcals.get_calendar(ex)
        session = datetime(check_date.year, check_date.month, check_date.day)
        return cal.is_session(session)
    except Exception as e:
        logger.warning("trading_calendar.is_market_open fail-open: %s", e)
        return True


def get_market_now(
    market: Optional[str], current_time: Optional[datetime] = None
) -> datetime:
    """
    Return current time in the market's local timezone.

    If current_time is naive, treat it as already expressed in the market timezone.
    Unknown markets fall back to the given datetime (or local system time).
    """
    tz_name = MARKET_TIMEZONE.get(market or "")

    if current_time is None:
        if tz_name:
            return datetime.now(ZoneInfo(tz_name))
        return datetime.now()

    if not tz_name:
        return current_time

    tz = ZoneInfo(tz_name)
    if current_time.tzinfo is None:
        return current_time.replace(tzinfo=tz)
    return current_time.astimezone(tz)


def _previous_vn_weekday(check_date: date) -> date:
    previous = check_date - timedelta(days=1)
    while not get_vn_calendar_day(previous).is_trading_day:
        previous -= timedelta(days=1)
    return previous


def _vn_session_bounds(market_now: datetime) -> Tuple[datetime, datetime]:
    return (
        datetime.combine(market_now.date(), _VN_OPEN_TIME, tzinfo=market_now.tzinfo),
        datetime.combine(market_now.date(), _VN_CLOSE_TIME, tzinfo=market_now.tzinfo),
    )


def _infer_vn_market_phase(market_now: datetime) -> MarketPhase:
    if not get_vn_calendar_day(market_now.date()).is_trading_day:
        return MarketPhase.NON_TRADING

    session_open, session_close = _vn_session_bounds(market_now)
    break_start = datetime.combine(market_now.date(), _VN_BREAK_START, tzinfo=market_now.tzinfo)
    break_end = datetime.combine(market_now.date(), _VN_BREAK_END, tzinfo=market_now.tzinfo)
    closing_start = session_close - timedelta(minutes=_CLOSING_AUCTION_WINDOW_MINUTES["vn"])

    if market_now < session_open:
        return MarketPhase.PREMARKET
    if market_now >= session_close:
        return MarketPhase.POSTMARKET
    if market_now < break_start:
        return MarketPhase.INTRADAY
    if market_now < break_end:
        return MarketPhase.LUNCH_BREAK
    if market_now < closing_start:
        return MarketPhase.INTRADAY
    return MarketPhase.CLOSING_AUCTION


def get_effective_trading_date(
    market: Optional[str], current_time: Optional[datetime] = None
) -> date:
    """
    Resolve the latest reusable daily-bar date for checkpoint/resume logic.

    Rules:
    - Non-trading day / holiday: previous trading session
    - Trading day before market close: previous completed trading session
    - Trading day after market close: current trading session
    - Calendar lookup failure: fail-open to market-local natural date
    """
    market_now = get_market_now(market, current_time=current_time)
    fallback_date = market_now.date()

    if market == "vn":
        if not get_vn_calendar_day(market_now.date()).is_trading_day:
            return _previous_vn_weekday(market_now.date())
        _, session_close = _vn_session_bounds(market_now)
        return market_now.date() if market_now >= session_close else _previous_vn_weekday(market_now.date())

    if not _XCALS_AVAILABLE:
        return fallback_date

    ex = MARKET_EXCHANGE.get(market or "")
    tz_name = MARKET_TIMEZONE.get(market or "")
    if not ex or not tz_name:
        return fallback_date

    try:
        cal = xcals.get_calendar(ex)
        local_date = market_now.date()

        if not cal.is_session(local_date):
            return cal.date_to_session(local_date, direction="previous").date()

        session = cal.date_to_session(local_date, direction="previous")
        session_close = cal.session_close(session)
        if hasattr(session_close, "tz_convert"):
            close_local = session_close.tz_convert(tz_name).to_pydatetime()
        elif session_close.tzinfo is not None:
            close_local = session_close.astimezone(ZoneInfo(tz_name))
        else:
            close_local = session_close.replace(tzinfo=ZoneInfo(tz_name))

        if market_now >= close_local:
            return session.date()

        return cal.previous_session(session).date()
    except Exception as e:
        logger.warning("trading_calendar.get_effective_trading_date fail-open: %s", e)
        return fallback_date


def _as_market_datetime(value: Any, tz_name: str) -> Optional[datetime]:
    """
    Convert exchange-calendar timestamps into market-local datetimes.

    Returns None for missing or pandas NaT-like values. Naive datetimes are
    interpreted as already expressed in the target market timezone, matching
    get_market_now()'s current_time contract.
    """
    if value is None:
        return None
    if pd.isna(value):
        return None

    try:
        if isinstance(value, pd.Timestamp):
            if value.tzinfo is None:
                dt = value.to_pydatetime()
            else:
                dt = value.tz_convert(tz_name).to_pydatetime()
        elif isinstance(value, datetime):
            dt = value
        elif hasattr(value, "to_pydatetime"):
            dt = value.to_pydatetime()
        else:
            return None
    except (AttributeError, TypeError, ValueError):
        return None

    tz = ZoneInfo(tz_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def infer_market_phase(
    market: Optional[str], current_time: Optional[datetime] = None
) -> MarketPhase:
    """
    Infer the regular-session market phase for a market.

    This P0 helper is intentionally fail-closed: unknown markets, unavailable
    exchange calendars, and calendar errors return ``MarketPhase.UNKNOWN``.
    That differs from ``is_market_open()`` and ``get_effective_trading_date()``,
    which keep their existing fail-open behavior for backwards compatibility.

    ``premarket`` and ``postmarket`` mean before/after the regular trading
    session only; they do not imply that extended-hours quote data is available.
    ``closing_auction`` uses a small per-market near-close heuristic window and
    does not model full exchange auction microstructure.
    """
    if market not in MARKET_EXCHANGE or market not in MARKET_TIMEZONE:
        return MarketPhase.UNKNOWN
    market_now = get_market_now(market, current_time=current_time)
    if market == "vn":
        return _infer_vn_market_phase(market_now)
    if not _XCALS_AVAILABLE:
        return MarketPhase.UNKNOWN

    ex = MARKET_EXCHANGE[market]
    tz_name = MARKET_TIMEZONE[market]
    local_date = market_now.date()

    try:
        cal = xcals.get_calendar(ex)
        if not cal.is_session(local_date):
            return MarketPhase.NON_TRADING

        session = cal.date_to_session(local_date, direction="previous")
        session_open = _as_market_datetime(cal.session_open(session), tz_name)
        session_close = _as_market_datetime(cal.session_close(session), tz_name)
        if session_open is None or session_close is None:
            return MarketPhase.UNKNOWN

        if market_now < session_open:
            return MarketPhase.PREMARKET
        if market_now >= session_close:
            return MarketPhase.POSTMARKET

        # Calendars without session_has_break may still expose break timestamps.
        has_break = True
        if hasattr(cal, "session_has_break"):
            has_break = bool(cal.session_has_break(session))

        break_start = None
        break_end = None
        if has_break:
            break_start = _as_market_datetime(cal.session_break_start(session), tz_name)
            break_end = _as_market_datetime(cal.session_break_end(session), tz_name)

        window_minutes = _CLOSING_AUCTION_WINDOW_MINUTES.get(market, 0)
        closing_window_start = session_close - timedelta(minutes=window_minutes)

        if break_start is not None and break_end is not None:
            if market_now < break_start:
                return MarketPhase.INTRADAY
            if market_now < break_end:
                return MarketPhase.LUNCH_BREAK
            if market_now < closing_window_start:
                return MarketPhase.INTRADAY
            return MarketPhase.CLOSING_AUCTION

        if market_now < closing_window_start:
            return MarketPhase.INTRADAY
        return MarketPhase.CLOSING_AUCTION
    except Exception as e:
        logger.warning("trading_calendar.infer_market_phase fail-closed: %s", e)
        return MarketPhase.UNKNOWN


def _add_warning_code(warnings: List[str], code: str) -> None:
    if code not in warnings:
        warnings.append(code)


def _phase_booleans(
    phase: MarketPhase,
) -> Tuple[Optional[bool], Optional[bool], Optional[bool]]:
    if phase == MarketPhase.UNKNOWN:
        return None, None, None

    is_trading_day = phase != MarketPhase.NON_TRADING
    is_market_open_now = phase in {
        MarketPhase.INTRADAY,
        MarketPhase.CLOSING_AUCTION,
    }
    is_partial_bar = phase in {
        MarketPhase.INTRADAY,
        MarketPhase.LUNCH_BREAK,
        MarketPhase.CLOSING_AUCTION,
    }
    return is_trading_day, is_market_open_now, is_partial_bar


def _session_open_close_for_today(
    market: str,
    market_now: datetime,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    tz_name = MARKET_TIMEZONE.get(market)
    if market == "vn":
        return (
            _vn_session_bounds(market_now)
            if get_vn_calendar_day(market_now.date()).is_trading_day
            else (None, None)
        )

    ex = MARKET_EXCHANGE.get(market)
    if not ex or not tz_name or not _XCALS_AVAILABLE:
        return None, None

    cal = xcals.get_calendar(ex)
    local_date = market_now.date()
    if not cal.is_session(local_date):
        return None, None

    session = cal.date_to_session(local_date, direction="previous")
    return (
        _as_market_datetime(cal.session_open(session), tz_name),
        _as_market_datetime(cal.session_close(session), tz_name),
    )


def _phase_minutes(
    market: Optional[str],
    market_now: datetime,
    phase: MarketPhase,
) -> Tuple[Optional[int], Optional[int], bool]:
    if (
        market not in MARKET_EXCHANGE
        or phase in {MarketPhase.UNKNOWN, MarketPhase.NON_TRADING, MarketPhase.POSTMARKET}
    ):
        return None, None, False
    if not _XCALS_AVAILABLE and market != "vn":
        return None, None, False

    try:
        session_open, session_close = _session_open_close_for_today(market, market_now)
    except Exception as e:
        logger.warning("trading_calendar.market_phase_context calendar_error: %s", e)
        return None, None, True

    if session_open is None or session_close is None:
        return None, None, False

    if phase == MarketPhase.PREMARKET and market_now < session_open:
        seconds = (session_open - market_now).total_seconds()
        return max(0, int(seconds // 60)), None, False

    if phase in {
        MarketPhase.INTRADAY,
        MarketPhase.LUNCH_BREAK,
        MarketPhase.CLOSING_AUCTION,
    } and market_now < session_close:
        seconds = (session_close - market_now).total_seconds()
        return None, max(0, int(seconds // 60)), False

    return None, None, False


def _normalize_analysis_phase(
    analysis_phase: Optional[str],
    analysis_intent: Optional[str],
) -> str:
    def _coerce(value: Optional[str]) -> str:
        if isinstance(value, MarketPhase):
            return value.value
        return str(value or "").strip().lower()

    requested = _coerce(analysis_phase) or "auto"
    legacy_intent = _coerce(analysis_intent)
    if requested == "auto" and legacy_intent and legacy_intent != "auto":
        requested = legacy_intent
    if requested not in _SUPPORTED_ANALYSIS_PHASES:
        raise ValueError(
            f"invalid analysis_phase: {requested}. "
            f"Must be one of {sorted(_SUPPORTED_ANALYSIS_PHASES)}"
        )
    return requested


def build_market_phase_context(
    *,
    market: Optional[str],
    current_time: Optional[datetime] = None,
    trigger_source: str = "system",
    analysis_intent: str = "auto",
    analysis_phase: str = "auto",
) -> MarketPhaseContext:
    """
    Build a JSON-safe runtime market-phase context for analysis plumbing.

    ``analysis_phase="auto"`` keeps calendar inference. Explicit supported
    phases override only the phase and derived flags/minute fields; they do
    not rewrite market-local time or the effective daily-bar date. The legacy
    ``analysis_intent`` argument remains a compatibility alias when
    ``analysis_phase`` is left as ``auto``.
    """
    requested_phase = _normalize_analysis_phase(analysis_phase, analysis_intent)
    market_now = get_market_now(market, current_time=current_time)
    warnings: List[str] = []

    if market not in MARKET_EXCHANGE or market not in MARKET_TIMEZONE:
        phase = MarketPhase.UNKNOWN
        _add_warning_code(warnings, "unknown_market")
    else:
        if not _XCALS_AVAILABLE and market != "vn":
            _add_warning_code(warnings, "calendar_unavailable")
        if market == "vn":
            vn_day = get_vn_calendar_day(market_now.date())
            if vn_day.coverage != VNCalendarCoverage.CONFIRMED:
                _add_warning_code(warnings, f"vn_calendar_{vn_day.coverage.value}")
        if requested_phase == "auto":
            phase = infer_market_phase(market, current_time=current_time)
            if phase == MarketPhase.UNKNOWN and _XCALS_AVAILABLE:
                _add_warning_code(warnings, "calendar_error")
        else:
            phase = MarketPhase(requested_phase)

    if requested_phase != "auto" and phase == MarketPhase.UNKNOWN:
        phase = MarketPhase(requested_phase)

    effective_daily_bar_date = get_effective_trading_date(
        market,
        current_time=current_time,
    )
    is_trading_day, is_market_open_now, is_partial_bar = _phase_booleans(phase)
    minutes_to_open, minutes_to_close, minutes_calendar_error = _phase_minutes(
        market,
        market_now,
        phase,
    )
    if minutes_calendar_error:
        _add_warning_code(warnings, "calendar_error")

    return MarketPhaseContext(
        market=market,
        phase=phase,
        market_local_time=market_now,
        session_date=market_now.date(),
        effective_daily_bar_date=effective_daily_bar_date,
        is_trading_day=is_trading_day,
        is_market_open_now=is_market_open_now,
        is_partial_bar=is_partial_bar,
        minutes_to_open=minutes_to_open,
        minutes_to_close=minutes_to_close,
        trigger_source=trigger_source or "system",
        analysis_intent=requested_phase,
        warnings=warnings,
    )


def get_open_markets_today() -> Set[str]:
    """
    Get markets that are open today (by each market's local timezone).

    Returns:
        Set of market keys that are trading today
    """
    if not _XCALS_AVAILABLE:
        return set(MARKET_TIMEZONE)
    result: Set[str] = set()
    for mkt, tz_name in MARKET_TIMEZONE.items():
        try:
            tz = ZoneInfo(tz_name)
            today = datetime.now(tz).date()
            if is_market_open(mkt, today):
                result.add(mkt)
        except Exception as e:
            logger.warning("get_open_markets_today fail-open for %s: %s", mkt, e)
            result.add(mkt)
    return result


def compute_effective_region(
    config_region: str, open_markets: Set[str]
) -> Optional[str]:
    """
    Compute effective market review region given config and open markets.

    Args:
        config_region: From MARKET_REVIEW_REGION ('cn' | 'hk' | 'us' | 'jp' | 'kr' | 'both' or comma subset)
        open_markets: Markets open today

    Returns:
        None: caller uses config default (check disabled)
        '': all relevant markets closed, skip market review
        'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'both': effective subset for today
    """
    markets = ("cn", "hk", "us", "jp", "kr")
    normalized = (config_region or "cn").strip().lower()
    if not normalized:
        normalized = "cn"

    requested = {
        item.strip() for item in normalized.split(",") if item.strip()
    }
    if not requested:
        requested = {"cn"}

    if "both" in requested:
        requested = set(markets)
    else:
        # Ignore invalid tokens and only keep known markets.
        requested = {item for item in requested if item in markets}

    if not requested:
        # No valid market token left after filtering; follow parser fallback behavior.
        requested = {"cn"}

    # single explicit region: keep single-region return semantics (empty when closed)
    if len(requested) == 1:
        region = next(iter(requested))
        return region if region in open_markets else ""

    # multi-region subset: keep only markets open today, in canonical order
    open_selected = [m for m in markets if m in requested and m in open_markets]
    if not open_selected:
        return ""
    if len(open_selected) == 1:
        return open_selected[0]
    return ",".join(open_selected)
