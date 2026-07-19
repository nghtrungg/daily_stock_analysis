"""Regression tests for API schema metadata under Pydantic v2."""

import json
from pathlib import Path
from typing import Any

from api.app import create_app
from api.v1.router import router as api_v1_router
from api.v1.endpoints.analysis import _ensure_report_action_fields
from api.v1.schemas.analysis import AnalyzeRequest, MarketReviewRequest
from api.v1.schemas.common import RootResponse
from api.v1.schemas.history import HistoryItem, ReportSummary
from api.v1.schemas.portfolio import PortfolioPositionItem
from api.v1.schemas.stocks import StockQuote


DECISION_SIGNAL_PATHS = (
    "/api/v1/decision-signals",
    "/api/v1/decision-signals/outcomes/run",
    "/api/v1/decision-signals/outcomes",
    "/api/v1/decision-signals/outcomes/stats",
    "/api/v1/decision-signals/latest/{stock_code}",
    "/api/v1/decision-signals/{signal_id}/outcomes",
    "/api/v1/decision-signals/{signal_id}/feedback",
    "/api/v1/decision-signals/{signal_id}",
    "/api/v1/decision-signals/{signal_id}/status",
)
DECISION_SIGNAL_SCHEMAS = (
    "DecisionSignalCreateRequest",
    "DecisionSignalFeedbackItem",
    "DecisionSignalFeedbackRequest",
    "DecisionSignalItem",
    "DecisionSignalListResponse",
    "DecisionSignalMutationResponse",
    "DecisionSignalOutcomeItem",
    "DecisionSignalOutcomeListResponse",
    "DecisionSignalOutcomeRunRequest",
    "DecisionSignalOutcomeRunResponse",
    "DecisionSignalOutcomeStatsBucket",
    "DecisionSignalOutcomeStatsResponse",
    "DecisionSignalStatusUpdateRequest",
)
P6_SIGNAL_LINKED_PATHS = (
    "/api/v1/alerts/triggers",
    "/api/v1/portfolio/risk",
)
P6_SIGNAL_LINKED_SCHEMAS = (
    "AlertTriggerItem",
    "AlertTriggerListResponse",
    "PortfolioDecisionSignalRiskBlock",
    "PortfolioDecisionSignalRiskItem",
    "PortfolioRiskResponse",
)
SETTLEMENT_PORTFOLIO_PATHS = (
    "/api/v1/portfolio/trades",
    "/api/v1/portfolio/snapshot",
    "/api/v1/portfolio/positions/{symbol}/settlement",
)
SETTLEMENT_PORTFOLIO_SCHEMAS = (
    "InsufficientSellableQuantityErrorResponse",
    "PortfolioPositionItem",
    "PortfolioPositionSettlementResponse",
    "PortfolioSettlementLotItem",
    "PortfolioTradeCreateRequest",
)


def _collect_component_schema_refs(node: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            refs.add(ref.rsplit("/", 1)[-1])
        for value in node.values():
            refs.update(_collect_component_schema_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.update(_collect_component_schema_refs(value))
    return refs


def test_schema_examples_remain_in_openapi_schema() -> None:
    root_schema = RootResponse.model_json_schema()
    analyze_schema = AnalyzeRequest.model_json_schema()
    history_schema = HistoryItem.model_json_schema()
    quote_schema = StockQuote.model_json_schema()

    assert root_schema["properties"]["message"]["example"] == "Daily Stock Analysis API is running"
    assert root_schema["example"]["version"] == "1.0.0"
    assert analyze_schema["properties"]["stock_code"]["example"] == "VNM.VN"
    assert analyze_schema["properties"]["skills"]["example"] == ["bull_trend", "growth_quality"]
    assert analyze_schema["properties"]["analysis_phase"]["default"] == "auto"
    assert analyze_schema["properties"]["analysis_phase"]["enum"] == [
        "auto",
        "premarket",
        "intraday",
        "postmarket",
    ]
    assert history_schema["example"]["stock_code"] == "600519"
    assert quote_schema["example"]["stock_code"] == "VNM.VN"
    assert quote_schema["example"]["stock_name"] == "Vinamilk"


def test_analyze_request_supports_legacy_strategies_dict_input() -> None:
    request = AnalyzeRequest.model_validate({
        "stock_code": "600519",
        "strategies": ["bull_trend", "growth_quality"],
    })

    assert request.skills == ["bull_trend", "growth_quality"]


def test_request_models_accept_report_language_camel_case_alias() -> None:
    analyze_request = AnalyzeRequest.model_validate({
        "stock_code": "600519",
        "reportLanguage": "en",
    })
    assert analyze_request.report_language == "en"

    market_review_request = MarketReviewRequest.model_validate({
        "send_notification": False,
        "reportLanguage": "en",
    })
    assert market_review_request.report_language == "en"


def test_request_models_accept_korean_report_language() -> None:
    analyze_request = AnalyzeRequest.model_validate({
        "stock_code": "005930.KS",
        "report_language": "ko",
    })
    assert analyze_request.report_language == "ko"

    market_review_request = MarketReviewRequest.model_validate({
        "send_notification": False,
        "report_language": "ko",
    })
    assert market_review_request.report_language == "ko"


def test_request_models_accept_vietnamese_report_language() -> None:
    analyze_request = AnalyzeRequest.model_validate({
        "stock_code": "VNM.VN",
        "report_language": "vi",
    })
    assert analyze_request.report_language == "vi"

    market_review_request = MarketReviewRequest.model_validate({
        "send_notification": False,
        "reportLanguage": "vi",
    })
    assert market_review_request.report_language == "vi"


def test_analyze_request_analysis_phase_defaults_to_auto() -> None:
    request = AnalyzeRequest(stock_code="600519")

    assert request.analysis_phase == "auto"


def test_analyze_request_rejects_invalid_analysis_phase() -> None:
    try:
        AnalyzeRequest.model_validate({
            "stock_code": "600519",
            "analysis_phase": "lunch_break",
        })
    except Exception as exc:
        assert "analysis_phase" in str(exc)
    else:
        raise AssertionError("invalid analysis_phase should be rejected")


def test_portfolio_position_settlement_fields_are_additive_and_serialize_all_states() -> None:
    base = {
        "symbol": "VNM.VN",
        "market": "vn",
        "currency": "VND",
        "quantity": 200,
        "avg_cost": 70000,
        "total_cost": 14000000,
        "last_price": 71000,
        "market_value_base": 14200000,
        "unrealized_pnl_base": 200000,
        "valuation_currency": "VND",
    }

    legacy = PortfolioPositionItem.model_validate(base).model_dump()
    assert legacy["position_lifecycle"] is None
    assert legacy["settlement_state"] is None
    assert legacy["sellable_quantity"] is None
    assert legacy["unsettled_quantity"] is None
    assert legacy["next_sellable_at"] is None
    assert legacy["settlement_calculation_status"] is None
    assert legacy["settlement_warnings"] == []

    cases = (
        ("unsettled", 0.0, 200.0),
        ("partially_sellable", 100.0, 100.0),
        ("sellable", 200.0, 0.0),
        ("unknown", 200.0, 0.0),
    )
    for state, sellable, unsettled in cases:
        payload = PortfolioPositionItem.model_validate(
            {
                **base,
                "position_lifecycle": "open",
                "settlement_state": state,
                "sellable_quantity": sellable,
                "unsettled_quantity": unsettled,
                "settlement_calculation_status": (
                    "unknown" if state == "unknown" else "confirmed"
                ),
                "settlement_warnings": (
                    ["settlement_provenance_missing"]
                    if state == "unknown"
                    else []
                ),
            }
        ).model_dump()
        assert payload["settlement_state"] == state
        assert payload["sellable_quantity"] == sellable
        assert payload["unsettled_quantity"] == unsettled


def test_report_summary_settlement_risk_is_optional_and_additive() -> None:
    legacy = ReportSummary(operation_advice="Theo dõi").model_dump()
    assert legacy["settlement_risk"] is None

    risk = {
        "policy_version": "vn-settlement-risk-v1",
        "survivability_status": "caution",
        "survivability_score": 58.0,
        "data_quality": "limited",
    }
    payload = ReportSummary(
        operation_advice="Theo dõi",
        settlement_risk=risk,
    ).model_dump()
    assert payload["settlement_risk"] == risk


def test_api_projection_preserves_settlement_risk_guarded_watch_action() -> None:
    risk = {
        "policy_version": "vn-settlement-risk-v1",
        "survivability_status": "unsafe",
        "survivability_score": 25.0,
        "data_quality": "good",
    }
    report = _ensure_report_action_fields(
        {
            "meta": {"report_language": "vi", "report_type": "detailed"},
            "summary": {"sentiment_score": 85, "operation_advice": "Theo dõi"},
            "details": {
                "raw_result": {
                    "action": "watch",
                    "operation_advice": "Theo dõi",
                    "sentiment_score": 85,
                    "settlement_risk": risk,
                }
            },
        }
    )

    assert report["summary"]["action"] == "watch"
    assert report["summary"]["settlement_risk"] == risk


def test_decision_signal_static_api_spec_matches_runtime_paths() -> None:
    static_spec_path = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "api_spec.json"
    static_spec = json.loads(static_spec_path.read_text(encoding="utf-8"))
    runtime_spec = create_app().openapi()

    assert static_spec["openapi"] == runtime_spec["openapi"]
    assert static_spec["info"]["description"] == runtime_spec["info"]["description"]
    assert "暂无认证要求" not in static_spec["info"]["description"]
    assert "ADMIN_AUTH_ENABLED=true" in static_spec["info"]["description"]
    for path in DECISION_SIGNAL_PATHS:
        assert static_spec["paths"][path] == runtime_spec["paths"][path]
        for operation in static_spec["paths"][path].values():
            assert "401" in operation["responses"]
            assert operation["security"] == [{"AdminSessionCookie": []}]
    assert static_spec["components"]["securitySchemes"] == runtime_spec["components"]["securitySchemes"]
    for schema_name in DECISION_SIGNAL_SCHEMAS:
        assert static_spec["components"]["schemas"][schema_name] == runtime_spec["components"]["schemas"][schema_name]

    for path in P6_SIGNAL_LINKED_PATHS:
        assert static_spec["paths"][path] == runtime_spec["paths"][path]
    for schema_name in P6_SIGNAL_LINKED_SCHEMAS:
        assert static_spec["components"]["schemas"][schema_name] == runtime_spec["components"]["schemas"][schema_name]
    for path in SETTLEMENT_PORTFOLIO_PATHS:
        assert static_spec["paths"][path] == runtime_spec["paths"][path]
    for schema_name in SETTLEMENT_PORTFOLIO_SCHEMAS:
        assert static_spec["components"]["schemas"][schema_name] == runtime_spec["components"]["schemas"][schema_name]
    schema_refs = _collect_component_schema_refs(static_spec)
    missing_schema_refs = sorted(schema_refs - set(static_spec["components"]["schemas"]))
    assert missing_schema_refs == []

    status_schema = static_spec["components"]["schemas"]["DecisionSignalStatusUpdateRequest"]["properties"]["status"]
    assert status_schema["enum"] == ["active", "expired", "invalidated", "closed", "archived"]


def test_v1_prefix_is_applied_at_app_mount_level() -> None:
    assert api_v1_router.prefix == ""

    runtime_paths = create_app().openapi()["paths"]
    assert "/api/v1/history" in runtime_paths
    assert "/api/v1/decision-signals" in runtime_paths
    assert "/api/v1/history/" not in runtime_paths
    assert "/api/v1/decision-signals/" not in runtime_paths
