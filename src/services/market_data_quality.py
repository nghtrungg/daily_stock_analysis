# -*- coding: utf-8 -*-
"""Deterministic quality checks for daily OHLCV used by stock reports."""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional

from src.report_language import localize_confidence_level, localize_operation_advice
from src.schemas.decision_action import localize_action_label


OHLC_FIELDS = ("open", "high", "low", "close")
VOLUME_OUTLIER_LOW_RATIO = 0.20
VOLUME_OUTLIER_HIGH_RATIO = 5.0
VOLUME_CROSS_SOURCE_TOLERANCE = 0.20
OHLC_CROSS_SOURCE_TOLERANCE = 0.005


def _positive_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _same_date(value: Any, expected: str) -> bool:
    if value is None:
        return False
    return str(value)[:10] == str(expected)[:10]


def validate_ohlc(bar: Mapping[str, Any]) -> tuple[bool, str]:
    """Validate the exchange invariant ``low <= open/close <= high``."""

    values = {field: _positive_number(bar.get(field)) for field in OHLC_FIELDS}
    if any(value is None for value in values.values()):
        return False, "incomplete"
    open_price = values["open"]
    high = values["high"]
    low = values["low"]
    close = values["close"]
    if low > high or high < max(open_price, close) or low > min(open_price, close):
        return False, "invalid"
    return True, "valid"


def reconcile_daily_bar(
    *,
    historical_bar: Optional[Mapping[str, Any]],
    realtime_bar: Mapping[str, Any],
    market_date: str,
    previous_volume: Any = None,
    is_partial_bar: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile a real-time quote with an independently fetched daily bar.

    The function never invents OHLC values. A structurally invalid real-time
    candle is replaced only by a valid same-day daily candle; otherwise only
    independently observed fields such as the close are retained.
    """

    historical = dict(historical_bar or {})
    realtime = dict(realtime_bar or {})
    historical_same_day = _same_date(historical.get("date"), market_date)
    realtime_valid, realtime_reason = validate_ohlc(realtime)
    historical_valid, _ = validate_ohlc(historical) if historical_same_day else (False, "incomplete")
    issues: list[str] = []

    bar: dict[str, Any] = {"date": str(market_date)[:10]}
    if realtime_valid and historical_valid and not is_partial_bar:
        for field in OHLC_FIELDS:
            bar[field] = historical[field]
        ohlc_source = "historical_daily"
        ohlc_usable = True
        for field in OHLC_FIELDS:
            realtime_value = _positive_number(realtime.get(field))
            historical_value = _positive_number(historical.get(field))
            if (
                realtime_value is not None
                and historical_value is not None
                and abs(realtime_value - historical_value)
                / max(realtime_value, historical_value)
                > OHLC_CROSS_SOURCE_TOLERANCE
            ):
                issues.append("ohlc_source_conflict")
                break
    elif realtime_valid:
        for field in OHLC_FIELDS:
            bar[field] = realtime[field]
        ohlc_source = "realtime"
        ohlc_usable = True
        if is_partial_bar:
            issues.append("partial_session_ohlc")
    elif historical_valid:
        for field in OHLC_FIELDS:
            bar[field] = historical[field]
        ohlc_source = "historical_daily"
        ohlc_usable = True
        issues.append(f"realtime_ohlc_{realtime_reason}")
    else:
        close = _positive_number(realtime.get("close"))
        if close is not None:
            bar["close"] = realtime.get("close")
        ohlc_source = "close_only"
        ohlc_usable = False
        issues.append(f"realtime_ohlc_{realtime_reason}")

    realtime_volume = _positive_number(realtime.get("volume"))
    historical_volume = (
        _positive_number(historical.get("volume")) if historical_same_day else None
    )
    previous = _positive_number(previous_volume)
    volume_usable = False
    volume_confirmation = "missing"
    volume_source = "none"

    if is_partial_bar and realtime_volume is not None:
        bar["volume"] = realtime.get("volume")
        volume_confirmation = "partial_session"
        volume_source = "realtime"
        issues.append("partial_session_volume")
    elif realtime_volume is not None and historical_volume is not None:
        difference_ratio = abs(realtime_volume - historical_volume) / max(
            realtime_volume, historical_volume
        )
        # Prefer the daily endpoint for a completed bar. A material disagreement
        # remains visible and is not admitted as volume evidence.
        bar["volume"] = historical.get("volume")
        volume_source = "historical_daily"
        if difference_ratio <= VOLUME_CROSS_SOURCE_TOLERANCE:
            volume_usable = True
            volume_confirmation = "cross_source"
        else:
            volume_confirmation = "source_conflict"
            issues.append("volume_source_conflict")
    elif historical_volume is not None:
        bar["volume"] = historical.get("volume")
        volume_source = "historical_daily"
        volume_usable = True
        volume_confirmation = "daily_source"
    elif realtime_volume is not None:
        bar["volume"] = realtime.get("volume")
        volume_source = "realtime"
        volume_confirmation = "single_source"
        if previous is None:
            volume_usable = True
        else:
            ratio = realtime_volume / previous
            if ratio < VOLUME_OUTLIER_LOW_RATIO or ratio > VOLUME_OUTLIER_HIGH_RATIO:
                issues.append("volume_unconfirmed_outlier")
            else:
                volume_usable = True

    for field in ("amount", "pct_chg", "data_source", "realtime_source"):
        value = realtime.get(field)
        if value is not None:
            bar[field] = value

    if ohlc_source == "historical_daily":
        historical_source = historical.get("data_source") or historical.get("dataSource")
        if historical_source:
            bar["data_source"] = historical_source

    status = "blocked" if not ohlc_usable else "warning" if issues else "ok"
    quality = {
        "status": status,
        "issues": list(dict.fromkeys(issues)),
        "ohlc_usable": ohlc_usable,
        "ohlc_source": ohlc_source,
        "volume_usable": volume_usable,
        "volume_source": volume_source,
        "volume_confirmation": volume_confirmation,
        "is_partial_bar": bool(is_partial_bar),
    }
    bar["data_quality"] = quality
    return bar, quality


def apply_market_data_quality_guardrail(
    result: Any,
    data_quality: Optional[Mapping[str, Any]],
    *,
    report_language: str = "vi",
) -> list[str]:
    """Suppress conclusions that depend on untrusted OHLC or volume inputs."""

    if result is None or not isinstance(data_quality, Mapping):
        return []
    issues = [str(item) for item in data_quality.get("issues", [])]
    ohlc_usable = data_quality.get("ohlc_usable") is True
    volume_usable = data_quality.get("volume_usable") is True
    if ohlc_usable and volume_usable and not issues:
        return []

    changes: list[str] = []
    dashboard = result.dashboard if isinstance(getattr(result, "dashboard", None), dict) else {}
    result.dashboard = dashboard
    data_perspective = dashboard.setdefault("data_perspective", {})
    if not isinstance(data_perspective, dict):
        data_perspective = {}
        dashboard["data_perspective"] = data_perspective
    data_perspective["data_quality"] = dict(data_quality)

    phase = dashboard.setdefault("phase_decision", {})
    if not isinstance(phase, dict):
        phase = {}
        dashboard["phase_decision"] = phase
    limitations = phase.get("data_limitations")
    if not isinstance(limitations, list):
        limitations = []
    if not ohlc_usable:
        limitations.append(
            "OHLC phiên hiện tại không hợp lệ hoặc không đầy đủ; không dùng mẫu nến, hỗ trợ/kháng cự hay áp lực bán từ phiên này."
            if report_language == "vi"
            else "The current-session OHLC is invalid or incomplete; candle, support/resistance, and selling-pressure conclusions are suppressed."
        )
    elif "partial_session_ohlc" in issues:
        limitations.append(
            "OHLC hiện tại là nến đang hình thành; không xem đây là mẫu nến cả phiên đã xác nhận."
            if report_language == "vi"
            else "Current OHLC is a forming intraday candle and is not treated as a confirmed full-session pattern."
        )
    elif "ohlc_source_conflict" in issues:
        limitations.append(
            "Các nguồn OHLC cùng ngày có chênh lệch đáng kể; báo cáo ưu tiên dữ liệu ngày nhưng hạ độ tin cậy."
            if report_language == "vi"
            else "Same-day OHLC sources materially disagree; the daily endpoint is preferred and confidence is reduced."
        )
    if not volume_usable:
        limitations.append(
            "Khối lượng phiên hiện tại chưa được xác nhận bởi nguồn thứ hai hoặc chỉ là dữ liệu một phần; không kết luận dòng tiền biến mất."
            if report_language == "vi"
            else "Current-session volume is partial or lacks independent confirmation; no liquidity-disappearance conclusion is allowed."
        )
        volume_analysis = data_perspective.setdefault("volume_analysis", {})
        if not isinstance(volume_analysis, dict):
            volume_analysis = {}
            data_perspective["volume_analysis"] = volume_analysis
        volume_analysis.update(
            {
                "volume_ratio": "N/A",
                "volume_status": "Chưa xác nhận" if report_language == "vi" else "Unconfirmed",
                "volume_meaning": (
                    "Khối lượng chưa được xác nhận; không dùng để suy luận lực cầu, lực bán hoặc dòng tiền."
                    if report_language == "vi"
                    else "Volume is unconfirmed and is excluded from demand, selling-pressure, and flow inference."
                ),
            }
        )
        changes.append("volume_signal_suppressed")
    phase["data_limitations"] = list(dict.fromkeys(limitations))

    result.confidence_level = localize_confidence_level("低", report_language)
    changes.append("confidence_downgraded_data_quality")
    if not ohlc_usable:
        result.sentiment_score = 50
        result.decision_type = "hold"
        result.action = "watch"
        result.action_label = localize_action_label("watch", report_language)
        result.operation_advice = localize_operation_advice("观望", report_language)
        result.pattern_analysis = (
            "Không đủ dữ liệu OHLC hợp lệ để đánh giá mẫu nến."
            if report_language == "vi"
            else "No valid OHLC data is available for candle-pattern analysis."
        )
        trend_status = data_perspective.get("trend_status")
        if isinstance(trend_status, dict):
            trend_status["trend_score"] = "N/A"
        core = dashboard.setdefault("core_conclusion", {})
        if isinstance(core, dict):
            core["one_sentence"] = (
                "Theo dõi; chưa hành động cho đến khi OHLCV được xác nhận."
                if report_language == "vi"
                else "Watch only until OHLCV is independently confirmed."
            )
            core["signal_type"] = "⚠️ Dữ liệu chưa đủ" if report_language == "vi" else "⚠️ Insufficient data"
        changes.extend(["score_neutralized_invalid_ohlc", "action_downgraded_invalid_ohlc"])
    return changes
