from __future__ import annotations

import pytest

from src.analyzer import AnalysisResult
from src.settlement_decision_guardrail import (
    SETTLEMENT_SNAPSHOT_VERSION,
    apply_settlement_decision_guardrail,
    build_settlement_snapshot,
    resolve_analysis_settlement_context,
)


def _result(action: str, *, language: str = "vi") -> AnalysisResult:
    return AnalysisResult(
        code="VNM.VN",
        name="Vinamilk",
        sentiment_score=25,
        trend_prediction="Tiêu cực",
        operation_advice="Bán 500 cổ phiếu ngay",
        decision_type="sell",
        confidence_level="Trung bình",
        report_language=language,
        action=action,
        dashboard={
            "core_conclusion": {"one_sentence": "Bán 500 cổ phiếu ngay"},
            "phase_decision": {"immediate_action": "Bán 500 cổ phiếu ngay"},
            "settlement_constraint": {
                "maximum_sell_quantity": 999999,
                "settlement_state": "sellable",
            },
        },
    )


@pytest.mark.parametrize(
    ("context", "expected_lifecycle", "expected_state", "expected_maximum"),
    (
        ({}, "no_position", "not_applicable", 0.0),
        (
            {
                "quantity": 100,
                "settlement_state": "unsettled",
                "sellable_quantity": 0,
                "unsettled_quantity": 100,
                "next_sellable_at": "2026-07-20T13:00:00+07:00",
                "calculation_status": "confirmed",
            },
            "open",
            "unsettled",
            0.0,
        ),
        (
            {
                "quantity": 100,
                "settlement_state": "partially_sellable",
                "sellable_quantity": 40,
                "unsettled_quantity": 60,
                "calculation_status": "confirmed",
            },
            "open",
            "partially_sellable",
            40.0,
        ),
        (
            {
                "quantity": 100,
                "settlement_state": "sellable",
                "sellable_quantity": 100,
                "unsettled_quantity": 0,
                "calculation_status": "confirmed",
            },
            "open",
            "sellable",
            100.0,
        ),
        (
            {
                "quantity": 100,
                "settlement_state": "unknown",
                "sellable_quantity": 25,
                "unsettled_quantity": 75,
                "calculation_status": "unknown",
            },
            "open",
            "unknown",
            None,
        ),
    ),
)
def test_build_settlement_snapshot_states(
    context: dict,
    expected_lifecycle: str,
    expected_state: str,
    expected_maximum: float | None,
) -> None:
    snapshot = build_settlement_snapshot(context)

    assert snapshot["snapshot_version"] == SETTLEMENT_SNAPSHOT_VERSION
    assert snapshot["position_lifecycle"] == expected_lifecycle
    assert snapshot["settlement_state"] == expected_state
    assert snapshot["maximum_sell_quantity"] == expected_maximum
    assert "account_name" not in snapshot
    assert "total_cost" not in snapshot


@pytest.mark.parametrize("action", ("sell", "reduce"))
def test_unsettled_position_downgrades_impossible_sale(action: str) -> None:
    result = _result(action)
    snapshot = build_settlement_snapshot(
        {
            "quantity": 100,
            "settlement_state": "unsettled",
            "sellable_quantity": 0,
            "unsettled_quantity": 100,
            "next_sellable_at": "2026-07-20T13:00:00+07:00",
            "calculation_status": "confirmed",
        }
    )

    adjustments = apply_settlement_decision_guardrail(result, snapshot)

    assert "settlement_sale_blocked" in adjustments
    assert result.action == "hold"
    assert result.decision_type == "hold"
    assert result.maximum_sell_quantity == 0.0
    assert result.reason_codes == ["settlement_unsettled_sale_blocked"]
    assert "500" not in result.operation_advice
    assert result.dashboard["settlement_constraint"] == result.settlement_snapshot


def test_partial_position_caps_model_quantity_and_sell_becomes_reduce() -> None:
    result = _result("sell")
    snapshot = build_settlement_snapshot(
        {
            "quantity": 100,
            "settlement_state": "partially_sellable",
            "sellable_quantity": 40,
            "unsettled_quantity": 60,
            "calculation_status": "confirmed",
        }
    )

    adjustments = apply_settlement_decision_guardrail(result, snapshot)

    assert "settlement_sale_capped" in adjustments
    assert result.action == "reduce"
    assert result.decision_type == "sell"
    assert result.maximum_sell_quantity == 40.0
    assert "40" in result.operation_advice
    assert "500" not in result.operation_advice
    assert result.dashboard["settlement_constraint"]["maximum_sell_quantity"] == 40.0


def test_sellable_position_preserves_action_but_overrides_model_snapshot() -> None:
    result = _result("sell")
    snapshot = build_settlement_snapshot(
        {
            "quantity": 100,
            "settlement_state": "sellable",
            "sellable_quantity": 100,
            "unsettled_quantity": 0,
            "calculation_status": "confirmed",
        }
    )

    adjustments = apply_settlement_decision_guardrail(result, snapshot)

    assert adjustments == []
    assert result.action == "sell"
    assert result.maximum_sell_quantity == 100.0
    assert "100" in result.operation_advice
    assert "500" not in result.operation_advice
    assert result.dashboard["settlement_constraint"]["maximum_sell_quantity"] == 100.0


def test_unknown_calendar_never_claims_executable_sale_quantity() -> None:
    result = _result("reduce")
    snapshot = build_settlement_snapshot(
        {
            "quantity": 100,
            "settlement_state": "unknown",
            "sellable_quantity": 25,
            "unsettled_quantity": 75,
            "calculation_status": "unknown",
        }
    )

    adjustments = apply_settlement_decision_guardrail(result, snapshot)

    assert "settlement_sale_unknown" in adjustments
    assert result.action == "alert"
    assert result.decision_type == "hold"
    assert result.maximum_sell_quantity is None
    assert result.reason_codes == ["settlement_calendar_unknown"]
    assert "500" not in result.operation_advice


def test_old_report_without_settlement_fields_remains_constructible() -> None:
    result = AnalysisResult(
        code="VNM.VN",
        name="Vinamilk",
        sentiment_score=50,
        trend_prediction="Trung lập",
        operation_advice="Theo dõi",
    )

    assert result.settlement_constraint is None
    assert result.maximum_sell_quantity is None
    assert result.reason_codes == []


def test_general_analysis_aggregates_active_accounts_without_financial_details() -> None:
    class Service:
        def get_portfolio_snapshot(self, **kwargs):
            return {
                "accounts": [
                    {
                        "account_id": 1,
                        "account_name": "First",
                        "positions": [
                            {
                                "symbol": "VNM.VN",
                                "quantity": 60,
                                "sellable_quantity": 20,
                                "unsettled_quantity": 40,
                                "settlement_state": "partially_sellable",
                                "settlement_calculation_status": "confirmed",
                                "total_cost": 1_000_000,
                            }
                        ],
                    },
                    {
                        "account_id": 2,
                        "account_name": "Second",
                        "positions": [
                            {
                                "symbol": "VNM.VN",
                                "quantity": 40,
                                "sellable_quantity": 20,
                                "unsettled_quantity": 20,
                                "settlement_state": "partially_sellable",
                                "settlement_calculation_status": "confirmed",
                                "total_cost": 2_000_000,
                            }
                        ],
                    },
                ]
            }

    context = resolve_analysis_settlement_context(
        "VNM.VN",
        service_factory=Service,
    )

    snapshot = context["settlement_snapshot"]
    assert snapshot["scope"] == "active_accounts_aggregate"
    assert snapshot["account_count"] == 2
    assert snapshot["total_quantity"] == 100
    assert snapshot["maximum_sell_quantity"] == 40
    assert "account_id" not in snapshot
    assert "account_name" not in snapshot
    assert "total_cost" not in snapshot


def test_selected_account_uses_on_demand_settlement_projection() -> None:
    class Service:
        def get_position_settlement(self, **kwargs):
            assert kwargs["account_id"] == 7
            return {
                "total_quantity": 100,
                "sellable_quantity": 0,
                "unsettled_quantity": 100,
                "settlement_state": "unsettled",
                "calculation_status": "confirmed",
            }

    context = resolve_analysis_settlement_context(
        "VNM.VN",
        portfolio_context={
            "account_id": 7,
            "account_name": "Private",
            "total_cost": 99_000_000,
        },
        service_factory=Service,
    )

    assert context["account_id"] == 7
    assert context["settlement_snapshot"]["scope"] == "selected_account"
    assert context["settlement_snapshot"]["maximum_sell_quantity"] == 0
    assert "account_id" not in context["settlement_snapshot"]
    assert "total_cost" not in context["settlement_snapshot"]


def test_resolution_failure_is_unknown_not_no_position() -> None:
    class BrokenService:
        def get_portfolio_snapshot(self, **kwargs):
            raise RuntimeError("database unavailable")

    context = resolve_analysis_settlement_context(
        "VNM.VN",
        service_factory=BrokenService,
    )

    snapshot = context["settlement_snapshot"]
    assert snapshot["position_lifecycle"] == "unknown"
    assert snapshot["settlement_state"] == "unknown"
    assert snapshot["maximum_sell_quantity"] is None
    assert snapshot["warnings"] == ["settlement_context_resolution_failed"]
