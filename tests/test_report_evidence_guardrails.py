from src.analyzer import AnalysisResult
from src.services.report_evidence_guardrails import (
    apply_report_evidence_guardrails,
)


def test_stale_news_is_removed_from_latest_news_for_short_horizon() -> None:
    result = AnalysisResult(
        code="MBB.VN",
        name="MB Bank",
        sentiment_score=50,
        trend_prediction="Đi ngang",
        operation_advice="Theo dõi",
        decision_type="hold",
        dashboard={
            "intelligence": {
                "latest_news": "2025-10-20 — Lợi nhuận 9 tháng năm 2025 đạt 23.139 tỷ đồng",
                "positive_catalysts": [
                    "2025-10-20 — Kết quả 9 tháng",
                    "2026-07-20 — Công bố thông tin mới",
                ],
                "risk_alerts": ["Tin không có ngày"],
            },
            "phase_decision": {"data_limitations": []},
        },
    )

    changes = apply_report_evidence_guardrails(
        result,
        analysis_date="2026-07-21",
        news_window_days=3,
        report_language="vi",
    )

    intelligence = result.dashboard["intelligence"]
    assert "Không có tin" in intelligence["latest_news"]
    assert intelligence["positive_catalysts"] == ["2026-07-20 — Công bố thông tin mới"]
    assert intelligence["risk_alerts"] == []
    assert "stale_latest_news_removed" in changes


def test_long_plan_gets_explicit_confirmation_conditions() -> None:
    result = AnalysisResult(
        code="MBB.VN",
        name="MB Bank",
        sentiment_score=55,
        trend_prediction="Yếu",
        operation_advice="Theo dõi",
        decision_type="hold",
        action="watch",
        dashboard={
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": 21800,
                    "secondary_buy": 22000,
                    "stop_loss": 21000,
                    "take_profit": 23500,
                }
            }
        },
    )

    apply_report_evidence_guardrails(
        result,
        analysis_date="2026-07-21",
        news_window_days=3,
        report_language="vi",
    )

    conditions = result.dashboard["battle_plan"]["entry_conditions"]
    assert len(conditions) == 4
    assert any("nến đảo chiều" in item for item in conditions)
    assert any("khối lượng" in item for item in conditions)

