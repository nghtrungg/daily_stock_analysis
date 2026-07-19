# -*- coding: utf-8 -*-
"""Deterministic Vietnam settlement context and recommendation guardrails."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from src.schemas.decision_action import build_action_fields, normalize_decision_action


SETTLEMENT_SNAPSHOT_VERSION = "vn-settlement-v1"
_SALE_ACTIONS = {"sell", "reduce"}
_SNAPSHOT_FIELDS = (
    "snapshot_version",
    "scope",
    "position_lifecycle",
    "settlement_state",
    "total_quantity",
    "sellable_quantity",
    "unsettled_quantity",
    "next_sellable_at",
    "maximum_sell_quantity",
    "calendar_status",
    "warnings",
)


def build_settlement_snapshot(
    context: Optional[Mapping[str, Any]],
    *,
    scope: str = "selected_account",
) -> Dict[str, Any]:
    """Freeze the low-sensitivity, authoritative settlement fields for analysis."""

    raw = _mapping(context)
    nested = _mapping(raw.get("settlement_snapshot"))
    if nested:
        raw = nested

    total = _non_negative_number(raw.get("total_quantity", raw.get("quantity")))
    explicit_state = str(raw.get("settlement_state") or "").strip().lower()
    if total is None and explicit_state == "unknown":
        return {
            "snapshot_version": SETTLEMENT_SNAPSHOT_VERSION,
            "scope": scope,
            "position_lifecycle": "unknown",
            "settlement_state": "unknown",
            "total_quantity": None,
            "sellable_quantity": None,
            "unsettled_quantity": None,
            "next_sellable_at": None,
            "maximum_sell_quantity": None,
            "calendar_status": "unknown",
            "warnings": _string_list(raw.get("warnings")),
        }
    if total is None or total <= 0:
        return {
            "snapshot_version": SETTLEMENT_SNAPSHOT_VERSION,
            "scope": scope,
            "position_lifecycle": "no_position",
            "settlement_state": "not_applicable",
            "total_quantity": 0.0,
            "sellable_quantity": 0.0,
            "unsettled_quantity": 0.0,
            "next_sellable_at": None,
            "maximum_sell_quantity": 0.0,
            "calendar_status": "not_applicable",
            "warnings": [],
        }

    state = str(raw.get("settlement_state") or "unknown").strip().lower()
    if state not in {"unsettled", "partially_sellable", "sellable", "unknown"}:
        state = "unknown"
    sellable = _non_negative_number(raw.get("sellable_quantity"))
    unsettled = _non_negative_number(raw.get("unsettled_quantity"))
    calendar_status = str(
        raw.get("calendar_status")
        or raw.get("calculation_status")
        or raw.get("settlement_calculation_status")
        or "unknown"
    ).strip().lower()

    if state == "unknown" or calendar_status == "unknown":
        state = "unknown"
        maximum = None
    else:
        sellable = min(total, sellable or 0.0)
        unsettled = min(total, unsettled if unsettled is not None else total - sellable)
        maximum = sellable

    return {
        "snapshot_version": SETTLEMENT_SNAPSHOT_VERSION,
        "scope": scope,
        "position_lifecycle": "open",
        "settlement_state": state,
        "total_quantity": total,
        "sellable_quantity": sellable,
        "unsettled_quantity": unsettled,
        "next_sellable_at": _optional_text(raw.get("next_sellable_at")),
        "maximum_sell_quantity": maximum,
        "calendar_status": calendar_status or "unknown",
        "warnings": _string_list(raw.get("warnings")),
    }


def resolve_analysis_settlement_context(
    symbol: str,
    *,
    portfolio_context: Optional[Mapping[str, Any]] = None,
    as_of: Optional[date] = None,
    service_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Resolve selected-account or privacy-preserving active-account context.

    General and scheduled analysis aggregates quantities across active accounts and
    exposes only the account count, never account names, ids, costs, or P&L.
    """

    context = dict(portfolio_context or {})
    factory = service_factory
    if factory is None:
        from src.services.portfolio_service import PortfolioService

        factory = PortfolioService
    try:
        service = factory()
        account_id = context.get("account_id")
        if account_id is not None:
            settlement = service.get_position_settlement(
                symbol=symbol,
                account_id=int(account_id),
                as_of=as_of,
                cost_method="fifo",
            )
            snapshot = build_settlement_snapshot(
                settlement or context,
                scope="selected_account",
            )
        else:
            portfolio = service.get_portfolio_snapshot(
                account_id=None,
                as_of=as_of,
                cost_method="fifo",
                include_realtime=False,
            )
            snapshot = _aggregate_active_account_snapshot(
                symbol,
                portfolio,
            )
    except Exception:
        snapshot = build_settlement_snapshot(
            {
                "total_quantity": _non_negative_number(
                    context.get("total_quantity", context.get("quantity"))
                ),
                "settlement_state": "unknown",
                "calendar_status": "unknown",
                "warnings": ["settlement_context_resolution_failed"],
            },
            scope="selected_account" if context.get("account_id") is not None else "active_accounts_aggregate",
        )

    context.update(snapshot)
    context["settlement_snapshot"] = dict(snapshot)
    return context


def apply_settlement_decision_guardrail(
    result: Any,
    settlement_snapshot: Optional[Mapping[str, Any]],
) -> List[str]:
    """Attach authoritative fields and prevent non-executable sale instructions."""

    snapshot = {
        key: value
        for key, value in build_settlement_snapshot(settlement_snapshot).items()
        if key in _SNAPSHOT_FIELDS
    }
    action = normalize_decision_action(getattr(result, "action", None))
    if not action:
        action = normalize_decision_action(getattr(result, "operation_advice", None))

    state = snapshot["settlement_state"]
    reason_codes: List[str] = []
    adjustments: List[str] = []
    final_action = action
    if action in _SALE_ACTIONS:
        if snapshot["position_lifecycle"] == "no_position":
            final_action = "alert"
            reason_codes.append("settlement_no_position_to_sell")
            adjustments.append("settlement_sale_blocked")
        elif state == "unsettled":
            final_action = "hold"
            reason_codes.append("settlement_unsettled_sale_blocked")
            adjustments.append("settlement_sale_blocked")
        elif state == "partially_sellable":
            final_action = "reduce"
            reason_codes.append("settlement_sale_quantity_capped")
            adjustments.append("settlement_sale_capped")
        elif state == "unknown":
            final_action = "alert"
            reason_codes.append("settlement_calendar_unknown")
            adjustments.append("settlement_sale_unknown")

    result.settlement_constraint = state
    result.maximum_sell_quantity = snapshot["maximum_sell_quantity"]
    result.reason_codes = reason_codes
    result.settlement_snapshot = dict(snapshot)

    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard
    dashboard["settlement_constraint"] = dict(snapshot)

    if action in _SALE_ACTIONS and (
        final_action != action or state in {"partially_sellable", "sellable"}
    ):
        message = _guardrail_message(
            state=state,
            lifecycle=snapshot["position_lifecycle"],
            maximum=snapshot["maximum_sell_quantity"],
            next_sellable_at=snapshot["next_sellable_at"],
            language=getattr(result, "report_language", None),
        )
        result.operation_advice = message
        result.decision_type = "sell" if final_action == "reduce" else "hold"
        _replace_action_text(dashboard, message)

    if final_action:
        fields = build_action_fields(
            operation_advice=getattr(result, "operation_advice", None),
            explicit_action=final_action,
            report_language=getattr(result, "report_language", None),
            align_with_score=False,
        )
        result.action = fields["action"]
        result.action_label = fields["action_label"]
    validate_settlement_guarded_report(result)
    return adjustments


def validate_settlement_guarded_report(result: Any) -> None:
    """Validate the final additive report contract after deterministic mutation."""

    from src.schemas.report_schema import AnalysisReportSchema

    payload = result.to_dict() if callable(getattr(result, "to_dict", None)) else {}
    AnalysisReportSchema.model_validate(payload)
    action = normalize_decision_action(payload.get("action"))
    maximum = payload.get("maximum_sell_quantity")
    state = payload.get("settlement_constraint")
    if action in _SALE_ACTIONS and state in {"unsettled", "unknown"}:
        raise ValueError("guarded report contains a non-executable settlement sale")
    if action in _SALE_ACTIONS and maximum is None:
        raise ValueError("guarded report sale is missing maximum_sell_quantity")


def _aggregate_active_account_snapshot(
    symbol: str,
    portfolio: Mapping[str, Any],
) -> Dict[str, Any]:
    target = str(symbol or "").strip().upper()
    matches: List[Mapping[str, Any]] = []
    for account in portfolio.get("accounts") or []:
        if not isinstance(account, Mapping):
            continue
        for position in account.get("positions") or []:
            if not isinstance(position, Mapping):
                continue
            candidate = str(position.get("symbol") or "").strip().upper()
            if candidate == target:
                matches.append(position)

    if not matches:
        snapshot = build_settlement_snapshot({}, scope="active_accounts_aggregate")
        snapshot["account_count"] = 0
        return snapshot

    total = sum(_non_negative_number(item.get("quantity")) or 0.0 for item in matches)
    sellable = sum(_non_negative_number(item.get("sellable_quantity")) or 0.0 for item in matches)
    unsettled = sum(_non_negative_number(item.get("unsettled_quantity")) or 0.0 for item in matches)
    statuses = {
        str(
            item.get("settlement_calculation_status")
            or item.get("calculation_status")
            or "unknown"
        ).lower()
        for item in matches
    }
    states = {str(item.get("settlement_state") or "unknown").lower() for item in matches}
    calendar_status = (
        "unknown" if "unknown" in statuses else ("degraded" if "degraded" in statuses else "confirmed")
    )
    if "unknown" in states or calendar_status == "unknown":
        state = "unknown"
    elif unsettled <= 0:
        state = "sellable"
    elif sellable <= 0:
        state = "unsettled"
    else:
        state = "partially_sellable"
    upcoming = sorted(
        text
        for text in (_optional_text(item.get("next_sellable_at")) for item in matches)
        if text
    )
    warnings = sorted(
        {
            str(warning)
            for item in matches
            for warning in (item.get("settlement_warnings") or item.get("warnings") or [])
            if str(warning).strip()
        }
    )
    snapshot = build_settlement_snapshot(
        {
            "total_quantity": total,
            "sellable_quantity": sellable,
            "unsettled_quantity": unsettled,
            "settlement_state": state,
            "next_sellable_at": upcoming[0] if upcoming else None,
            "calendar_status": calendar_status,
            "warnings": warnings,
        },
        scope="active_accounts_aggregate",
    )
    snapshot["account_count"] = len(matches)
    return snapshot


def _guardrail_message(
    *,
    state: str,
    lifecycle: str,
    maximum: Optional[float],
    next_sellable_at: Optional[str],
    language: Optional[str],
) -> str:
    lang = str(language or "").lower()
    if lang == "vi":
        if lifecycle == "no_position":
            return "Không có vị thế để bán; chỉ phát cảnh báo và tiếp tục theo dõi."
        if state == "partially_sellable":
            return f"Chỉ có thể bán tối đa {_format_quantity(maximum)} cổ phiếu đã về tài khoản; phần còn lại chưa thể bán."
        if state == "unknown":
            return "Chưa xác định được trạng thái thanh toán; không công bố khối lượng bán có thể thực hiện."
        if state == "sellable":
            return f"Có thể bán tối đa {_format_quantity(maximum)} cổ phiếu đã về tài khoản."
        suffix = f" Thời điểm dự kiến có thể bán: {next_sellable_at}." if next_sellable_at else ""
        return "Cổ phiếu chưa về tài khoản nên chưa thể bán; tiếp tục nắm giữ." + suffix
    if lang == "zh":
        if state == "partially_sellable":
            return f"仅可卖出最多 {_format_quantity(maximum)} 股已结算持仓；未结算部分不得卖出。"
        if state == "unknown":
            return "结算状态未知，不声明可执行卖出数量。"
        if state == "sellable":
            return f"最多可卖出 {_format_quantity(maximum)} 股已结算持仓。"
        return "持仓尚未结算，当前不得卖出。"
    if state == "partially_sellable":
        return f"Sell at most {_format_quantity(maximum)} settled shares; the unsettled quantity is not executable."
    if state == "unknown":
        return "Settlement status is unknown; no executable sale quantity is claimed."
    if state == "sellable":
        return f"Sell at most {_format_quantity(maximum)} settled shares."
    if lifecycle == "no_position":
        return "There is no position to sell; emit an alert and continue monitoring."
    return "The position is unsettled and cannot be sold yet."


def _replace_action_text(dashboard: Dict[str, Any], message: str) -> None:
    core = dashboard.get("core_conclusion")
    if isinstance(core, dict):
        core["one_sentence"] = message
        advice = core.get("position_advice")
        if isinstance(advice, dict):
            advice["has_position"] = message
    phase = dashboard.get("phase_decision")
    if isinstance(phase, dict):
        phase["immediate_action"] = message


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _non_negative_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, number)


def _optional_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))[:10]


def _format_quantity(value: Optional[float]) -> str:
    if value is None:
        return "0"
    return str(int(value)) if float(value).is_integer() else f"{value:.8f}".rstrip("0").rstrip(".")
