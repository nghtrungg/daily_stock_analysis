# -*- coding: utf-8 -*-
"""Attach deterministic settlement risk and block unsafe entry recommendations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from src.schemas.decision_action import build_action_fields, normalize_decision_action
from src.schemas.settlement_risk import SettlementRiskEstimate


_ENTRY_ACTIONS = {"buy", "add"}
_UNSAFE_REASON = "settlement_risk_unsafe_entry"


def apply_settlement_risk_guardrail(
    result: Any,
    estimate: Optional[Mapping[str, Any]],
) -> List[str]:
    """Attach an authoritative risk block and downgrade unsafe entry actions."""

    if not isinstance(estimate, Mapping):
        return []
    risk = SettlementRiskEstimate.model_validate(dict(estimate)).model_dump(
        mode="json"
    )
    result.settlement_risk = risk
    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard
    dashboard["settlement_risk"] = dict(risk)

    action = normalize_decision_action(getattr(result, "action", None))
    if not action:
        action = normalize_decision_action(getattr(result, "operation_advice", None))
    if action not in _ENTRY_ACTIONS or risk["survivability_status"] != "unsafe":
        return []

    reason_codes = [
        str(item)
        for item in (getattr(result, "reason_codes", None) or [])
        if str(item).strip()
    ]
    if _UNSAFE_REASON not in reason_codes:
        reason_codes.append(_UNSAFE_REASON)
    result.reason_codes = reason_codes
    result.operation_advice = _unsafe_message(getattr(result, "report_language", None))
    result.decision_type = "hold"
    fields = build_action_fields(
        operation_advice=result.operation_advice,
        explicit_action="watch",
        report_language=getattr(result, "report_language", None),
        align_with_score=False,
    )
    result.action = fields["action"]
    result.action_label = fields["action_label"]
    _replace_action_text(dashboard, result.operation_advice)
    return ["settlement_risk_entry_blocked"]


def _unsafe_message(language: Optional[str]) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "vi":
        return (
            "Rủi ro trong thời gian chờ thanh toán ở mức không an toàn; "
            "không mở vị thế mới và tiếp tục theo dõi."
        )
    if normalized == "zh":
        return "结算等待期风险处于不安全水平；暂不开新仓并继续观察。"
    return (
        "Settlement-window risk is unsafe; do not open a new position and "
        "continue monitoring."
    )


def _replace_action_text(dashboard: Dict[str, Any], message: str) -> None:
    core = dashboard.get("core_conclusion")
    if isinstance(core, dict):
        core["one_sentence"] = message
        advice = core.get("position_advice")
        if isinstance(advice, dict):
            advice["no_position"] = message
    phase = dashboard.get("phase_decision")
    if isinstance(phase, dict):
        phase["immediate_action"] = message
