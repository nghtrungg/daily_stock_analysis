# -*- coding: utf-8 -*-
"""Freshness, horizon, and conditional-entry guardrails for final reports."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional


_ISO_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])(?!\d)")


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _dated_within_window(value: Any, cutoff: date, analysis_date: date) -> bool:
    text = str(value or "")
    matches = _ISO_DATE_RE.findall(text)
    for year, month, day in matches:
        try:
            published = date(int(year), int(month), int(day))
        except ValueError:
            continue
        if cutoff <= published <= analysis_date:
            return True
    return False


def apply_report_evidence_guardrails(
    result: Any,
    *,
    analysis_date: Any,
    news_window_days: int,
    report_language: str = "vi",
) -> list[str]:
    """Remove stale short-horizon news and make entry prices conditional."""

    parsed_analysis_date = _parse_date(analysis_date)
    if result is None or parsed_analysis_date is None:
        return []
    try:
        window_days = max(1, int(news_window_days))
    except (TypeError, ValueError):
        window_days = 3
    cutoff = parsed_analysis_date - timedelta(days=window_days)
    changes: list[str] = []

    dashboard = result.dashboard if isinstance(getattr(result, "dashboard", None), dict) else {}
    result.dashboard = dashboard
    intelligence = dashboard.get("intelligence")
    stale_evidence_removed = False
    if isinstance(intelligence, dict):
        latest_news = intelligence.get("latest_news")
        if latest_news and not _dated_within_window(latest_news, cutoff, parsed_analysis_date):
            intelligence["latest_news"] = (
                f"Không có tin doanh nghiệp có ngày công bố trong {window_days} ngày gần nhất; tin cũ không được dùng làm chất xúc tác ngắn hạn."
                if report_language == "vi"
                else f"No company news with a verified publication date falls within the latest {window_days}-day window; older items are excluded from short-term catalysts."
            )
            changes.append("stale_latest_news_removed")
            stale_evidence_removed = True
        for field in ("risk_alerts", "positive_catalysts"):
            items = intelligence.get(field)
            if not isinstance(items, list):
                continue
            filtered = [
                item for item in items
                if _dated_within_window(item, cutoff, parsed_analysis_date)
            ]
            if filtered != items:
                intelligence[field] = filtered
                changes.append(f"stale_or_undated_{field}_removed")
                stale_evidence_removed = True

    if stale_evidence_removed:
        phase = dashboard.setdefault("phase_decision", {})
        if isinstance(phase, dict):
            limitations = phase.get("data_limitations")
            if not isinstance(limitations, list):
                limitations = []
            limitations.append(
                "Tin cũ hoặc không xác định được ngày công bố đã bị loại khỏi tín hiệu 1–5 phiên."
                if report_language == "vi"
                else "Stale or undated evidence was excluded from the 1–5-session signal."
            )
            phase["data_limitations"] = list(dict.fromkeys(limitations))

    battle_plan = dashboard.get("battle_plan")
    if isinstance(battle_plan, dict) and isinstance(battle_plan.get("sniper_points"), dict):
        if report_language == "vi":
            conditions = [
                "Giá giữ được vùng vào lệnh, không chỉ chạm mức giá trong phiên.",
                "Xuất hiện nến đảo chiều hoặc cấu trúc giá xác nhận.",
                "Khối lượng phục hồi và đã được xác nhận là khối lượng cả phiên.",
                "VN-Index ngừng tạo đáy thấp hơn trong cùng khung 1–5 phiên.",
            ]
        else:
            conditions = [
                "Price must hold the entry zone rather than merely touch it intraday.",
                "A reversal candle or confirming price structure must appear.",
                "Volume must recover and be confirmed as completed-session volume.",
                "The market index must stop making lower lows over the same 1–5-session horizon.",
            ]
        battle_plan["entry_conditions"] = conditions
        changes.append("conditional_entry_requirements_added")

    dashboard["analysis_horizons"] = {
        "tactical": "1–5 phiên" if report_language == "vi" else "1–5 sessions",
        "medium_term": "1–3 tháng" if report_language == "vi" else "1–3 months",
        "fundamental": "6–12 tháng" if report_language == "vi" else "6–12 months",
    }
    dashboard["methodology_note"] = (
        "Điểm số và R:R là chỉ báo tổng hợp/giá trị suy ra, không phải xác suất đã được kiểm định; độ tin cậy phụ thuộc chất lượng và độ mới của dữ liệu đầu vào."
        if report_language == "vi"
        else "Scores and R:R are composite/derived indicators, not backtested probabilities; confidence depends on input quality and freshness."
    )
    return changes

