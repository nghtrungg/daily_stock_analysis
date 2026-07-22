from src.analyzer import AnalysisResult
from src.services.report_renderer import render


def _result(action: str, advice: str) -> AnalysisResult:
    return AnalysisResult(
        code="MBB.VN",
        name="Ngân hàng TMCP Quân đội",
        sentiment_score=35,
        trend_prediction="Thận trọng",
        operation_advice=advice,
        decision_type="sell" if action in {"reduce", "sell"} else "hold",
        action=action,
        report_language="vi",
        dashboard={
            "core_conclusion": {
                "one_sentence": advice,
                "signal_type": advice,
                "time_sensitivity": "Không gấp",
            },
            "methodology_note": "Điểm số không phải xác suất.",
            "analysis_horizons": {
                "tactical": "1–5 phiên",
                "medium_term": "1–3 tháng",
                "fundamental": "6–12 tháng",
            },
        },
    )


def test_reduce_is_not_counted_as_sell_in_markdown_summary() -> None:
    output = render("markdown", [_result("reduce", "Giảm tỷ trọng")], summary_only=True)

    assert output is not None
    assert "🟠Giảm tỷ trọng:1" in output
    assert "🔴Bán:0" in output


def test_report_explains_horizons_and_score_methodology() -> None:
    output = render("markdown", [_result("watch", "Theo dõi")], summary_only=False)

    assert output is not None
    assert "Phương pháp" in output
    assert "Điểm số không phải xác suất" in output
    assert "Ngắn hạn 1–5 phiên" in output
    assert "Trung hạn 1–3 tháng" in output
    assert "Cơ bản 6–12 tháng" in output

