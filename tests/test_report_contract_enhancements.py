# -*- coding: utf-8 -*-
"""Regression coverage for actionable reports and long-term trend context."""

from __future__ import annotations

import pandas as pd

from src.analyzer import (
    AnalysisResult,
    check_content_integrity,
    enforce_actionable_trade_plan,
    fill_money_flow_indicators_if_needed,
    fill_vietnam_order_flow_if_needed,
    normalize_report_output_data,
)
from src.stock_analyzer import StockTrendAnalyzer
from src.services.report_renderer import render


def _buy_result(*, ideal_buy="55.50", stop_loss="53.80") -> AnalysisResult:
    return AnalysisResult(
        code="VNM.VN",
        name="Vinamilk",
        report_language="vi",
        trend_prediction="Hồi phục kỹ thuật",
        sentiment_score=72,
        operation_advice="Mua",
        analysis_summary="Giá đóng cửa trên MA20.",
        decision_type="buy",
        confidence_level="Trung bình",
        dashboard={
            "core_conclusion": {
                "one_sentence": "Chiến lược phù hợp hiện tại là mua.",
                "signal_type": "🟢 Mua",
                "position_advice": {
                    "no_position": "Mua thăm dò.",
                    "has_position": "Tiếp tục nắm giữ.",
                },
            },
            "intelligence": {"risk_alerts": []},
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": ideal_buy,
                    "secondary_buy": "N/A",
                    "stop_loss": stop_loss,
                    "take_profit": "N/A",
                }
            },
        },
    )


def test_buy_integrity_requires_actionable_entry_and_stop_loss() -> None:
    result = _buy_result(ideal_buy="N/A", stop_loss="Cần bổ sung")

    ok, missing = check_content_integrity(result)

    assert ok is False
    assert "dashboard.battle_plan.sniper_points.ideal_buy" in missing
    assert "dashboard.battle_plan.sniper_points.stop_loss" in missing


def test_buy_integrity_rejects_labeled_placeholders_and_zero_prices() -> None:
    result = _buy_result(
        ideal_buy="Điểm mua lý tưởng: N/A",
        stop_loss="Cắt lỗ: 0",
    )

    ok, missing = check_content_integrity(result)

    assert ok is False
    assert "dashboard.battle_plan.sniper_points.ideal_buy" in missing
    assert "dashboard.battle_plan.sniper_points.stop_loss" in missing


def test_buy_without_core_trade_plan_is_downgraded_consistently_in_vietnamese() -> None:
    result = _buy_result(ideal_buy="N/A", stop_loss="Cần bổ sung")

    adjustments = enforce_actionable_trade_plan(result)

    assert adjustments == ["missing_entry", "missing_stop_loss"]
    assert result.decision_type == "hold"
    assert result.operation_advice == "Theo dõi"
    assert result.sentiment_score <= 59
    assert "Theo dõi" in result.dashboard["core_conclusion"]["one_sentence"]
    assert "Mua" not in result.dashboard["core_conclusion"]["signal_type"]
    assert result.dashboard["trade_plan_guardrail"]["applied"] is True


def test_buy_wording_is_guarded_even_when_model_decision_type_conflicts() -> None:
    result = _buy_result(ideal_buy="N/A", stop_loss="Cần bổ sung")
    result.decision_type = "hold"

    ok, missing = check_content_integrity(result)
    adjustments = enforce_actionable_trade_plan(result)

    assert ok is False
    assert "dashboard.battle_plan.sniper_points.ideal_buy" in missing
    assert adjustments == ["missing_entry", "missing_stop_loss"]
    assert result.operation_advice == "Theo dõi"


def test_actionable_buy_plan_is_preserved() -> None:
    result = _buy_result()

    adjustments = enforce_actionable_trade_plan(result)

    assert adjustments == []
    assert result.decision_type == "buy"
    assert result.operation_advice == "Mua"


def test_report_output_normalizes_price_precision_and_structured_news() -> None:
    result = _buy_result()
    result.dashboard["data_perspective"] = {
        "price_position": {
            "current_price": 56.6,
            "ma5": 55.67999999999999,
            "ma10": 56.223,
            "ma20": 56.223,
            "ma50": 57.6789,
            "ma200": 61.2345,
            "support_level": 54.999999999,
            "resistance_level": 58.126,
        }
    }
    result.dashboard["intelligence"]["latest_news"] = [
        {
            "date": "2026-07-10",
            "title": "ACBS cập nhật VNM",
            "summary": "Lợi nhuận tăng trưởng ổn định nhờ tối ưu chi phí.",
            "source": "ACBS",
        }
    ]

    normalize_report_output_data(result)

    prices = result.dashboard["data_perspective"]["price_position"]
    assert prices["ma5"] == 55.68
    assert prices["ma10"] == 56.22
    assert prices["ma20"] == 56.22
    assert prices["ma50"] == 57.68
    assert prices["ma200"] == 61.23
    news = result.dashboard["intelligence"]["latest_news"]
    assert news == (
        "2026-07-10 — ACBS cập nhật VNM (ACBS): "
        "Lợi nhuận tăng trưởng ổn định nhờ tối ưu chi phí."
    )
    assert "{'date'" not in news


def test_report_output_parses_python_repr_news_without_exposing_raw_array() -> None:
    result = _buy_result()
    result.dashboard["intelligence"]["latest_news"] = (
        "[{'date': '2026-07-10', 'title': 'Tin sạch', 'source': 'ACBS'}]"
    )

    normalize_report_output_data(result)

    news = result.dashboard["intelligence"]["latest_news"]
    assert news == "2026-07-10 — Tin sạch (ACBS)"
    assert "[{" not in news


def test_vietnamese_markdown_renders_normalized_prices_and_news() -> None:
    result = _buy_result()
    result.dashboard["data_perspective"] = {
        "price_position": {
            "current_price": 56.6,
            "ma5": 55.67999999999999,
            "ma10": 56.223,
            "ma20": 56.223,
            "ma50": 57.6789,
            "ma200": 61.2345,
            "bias_ma5": 0.67,
            "bias_status": "An toàn",
        }
    }
    result.dashboard["intelligence"]["latest_news"] = [
        {"date": "2026-07-10", "title": "Tin sạch", "source": "ACBS"}
    ]

    output = render("markdown", [result], summary_only=False)

    assert output is not None
    assert "55.68" in output
    assert "56.22" in output
    assert "| MA50 | 57.68 |" in output
    assert "| MA200 | 61.23 |" in output
    assert "55.67999999999999" not in output
    assert "2026-07-10 — Tin sạch (ACBS)" in output
    assert "{'date'" not in output


def test_vietnam_order_flow_is_exposed_separately_from_chip_data() -> None:
    result = _buy_result()
    context = {
        "capital_flow": {
            "status": "ok",
            "data": {
                "coverage": {
                    "active_order_flow": "ok",
                    "foreign_flow": "ok",
                    "proprietary_flow": "not_configured",
                },
                "stock_flow": {
                    "active_buy_volume": 700.0,
                    "active_sell_volume": 200.0,
                    "active_net_volume": 500.0,
                    "active_imbalance": 0.555556,
                    "foreign_net_value": 1_500_000.0,
                },
            },
        }
    }

    fill_vietnam_order_flow_if_needed(result, context)

    perspective = result.dashboard["data_perspective"]
    assert perspective["order_flow"]["active_buy_volume"] == 700.0
    assert perspective["order_flow"]["foreign_net_value"] == 1_500_000.0
    assert "chip_structure" not in perspective
    assert "không phải dữ liệu phân bổ chip" in perspective["order_flow"]["note"]


def test_vietnam_order_flow_discloses_stale_fallback_session() -> None:
    result = _buy_result()
    context = {
        "capital_flow": {
            "status": "partial",
            "data": {
                "fallback_as_of": "2026-07-17T15:10:00",
                "coverage": {"active_order_flow": "fallback"},
                "stock_flow": {
                    "active_buy_volume": 700.0,
                    "active_sell_volume": 200.0,
                },
            },
        }
    }

    fill_vietnam_order_flow_if_needed(result, context)

    order_flow = result.dashboard["data_perspective"]["order_flow"]
    assert order_flow["fallback_as_of"] == "2026-07-17T15:10:00"
    assert "2026-07-17T15:10:00" in order_flow["note"]
    assert "không phải dữ liệu realtime" in order_flow["note"]


def test_money_flow_indicators_do_not_depend_on_fundamental_context() -> None:
    result = _buy_result()

    fill_money_flow_indicators_if_needed(
        result,
        {"mfi_14": 61.25, "cmf_20": 0.1234},
    )

    money_flow = result.dashboard["data_perspective"]["money_flow_indicators"]
    assert money_flow["mfi_14"] == 61.25
    assert money_flow["cmf_20"] == 0.1234


def test_long_term_ma_context_detects_bear_market_rally() -> None:
    dates = pd.date_range("2025-09-01", periods=230, freq="B")
    closes = list(pd.Series(range(200), dtype=float).map(lambda i: 100.0 - i * 0.2))
    closes.extend([55.0 + i * 0.2 for i in range(30)])
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        }
    )

    result = StockTrendAnalyzer().analyze(frame, "VNM.VN")

    assert result.current_price > result.ma20
    assert result.current_price < result.ma200
    assert result.ma50 is not None
    assert result.ma200 is not None
    assert result.ma200_slope_pct is not None
    assert result.ma200_slope_pct < 0
    assert result.long_term_trend == "bear_market_rally"
    assert result.long_term_warning
