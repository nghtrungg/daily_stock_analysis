# -*- coding: utf-8 -*-
"""Behavior tests for explainable decision metrics."""

from __future__ import annotations

from src.analyzer import AnalysisResult
from src.services.decision_metrics import apply_decision_metrics
from src.services.report_renderer import render


def _result(*, score: int = 35, with_plan: bool = True) -> AnalysisResult:
    battle_plan = {
        "sniper_points": {
            "ideal_buy": 22000,
            "secondary_buy": 22200,
            "stop_loss": 21500,
            "take_profit": 24000,
        }
    }
    if with_plan:
        battle_plan["trading_plan_validation"] = {
            "quality_status": "valid",
            "warnings": [],
            "risk_reward_ratio": 4.0,
            "display": {"risk_reward": "R:R = 1 : 4"},
        }
    return AnalysisResult(
        code="KLB.VN",
        name="KienlongBank",
        sentiment_score=score,
        trend_prediction="Xu hướng giảm",
        operation_advice="Giảm tỷ trọng",
        decision_type="sell",
        confidence_level="Trung bình",
        report_language="vi",
        analysis_summary="Xu hướng ngắn hạn còn yếu.",
        dashboard={
            "core_conclusion": {"one_sentence": "Ưu tiên kiểm soát rủi ro."},
            "data_perspective": {
                "price_position": {
                    "current_price": 22500,
                    "support_level": 22000,
                    "resistance_level": 23500,
                },
                "trend_status": {"trend_score": 30},
            },
            "intelligence": {"risk_alerts": []},
            "battle_plan": battle_plan,
        },
    )


def _overview() -> dict:
    return {
        "data_quality": {
            "overall_score": 76,
            "level": "usable",
            "block_scores": {
                "quote": 100,
                "daily_bars": 100,
                "technical": 75,
                "news": 100,
                "fundamentals": 35,
                "chip": 70,
            },
            "limitations": ["fundamentals: missing"],
        }
    }


def test_finalizer_builds_reconciled_score_confidence_scenarios_and_ev() -> None:
    result = _result()

    metrics = apply_decision_metrics(
        result,
        analysis_context_pack_overview=_overview(),
        market_data_quality={"ohlc_usable": True, "volume_usable": False},
        daily_market_context={"summary": "Thị trường thận trọng", "source": "history"},
    )

    score = metrics["score_breakdown"]
    assert score["total_score"] == 35
    assert score["max_score"] == 100
    assert score["band"] == "20-39"
    assert score["distance_to_next_band"] == 5
    assert sum(item["score"] for item in score["components"].values()) == 35
    assert {key: item["max_score"] for key, item in score["components"].items()} == {
        "trend": 30,
        "momentum": 20,
        "volume": 15,
        "market": 15,
        "fundamental": 20,
    }

    confidence = metrics["evidence_confidence"]
    assert 0 <= confidence["score_pct"] <= 100
    assert confidence["factors"]["ohlc"]["status"] == "available"
    assert confidence["factors"]["volume"]["status"] == "missing"
    assert confidence["factors"]["fundamental"]["status"] == "missing"

    scenarios = metrics["scenario_outlook"]["scenarios"]
    assert [item["key"] for item in scenarios] == ["downside", "sideways", "upside"]
    assert sum(item["probability_pct"] for item in scenarios) == 100
    assert scenarios[0]["probability_pct"] == 60
    assert scenarios[2]["probability_pct"] == 15

    expectancy = metrics["trade_expectancy"]
    assert expectancy["risk_reward_ratio"] == 4.0
    assert expectancy["win_probability_pct"] == 15
    assert expectancy["expected_value_r"] == -0.25
    assert expectancy["probability_source"] == "scenario_estimate"


def test_model_component_scores_and_probabilities_are_normalized() -> None:
    result = _result(score=45)
    result.dashboard["decision_metrics"] = {
        "score_breakdown": {
            "components": {
                "trend": {"score": 25, "reason": "Xu hướng cải thiện"},
                "momentum": {"score": 18},
                "volume": {"score": 13},
                "market": {"score": 12},
                "fundamental": {"score": 17},
            }
        },
        "scenario_outlook": {
            "scenarios": [
                {"key": "downside", "probability_pct": 8, "condition": "Mất hỗ trợ"},
                {"key": "sideways", "probability_pct": 12, "condition": "Giữ nền"},
                {"key": "upside", "probability_pct": 20, "condition": "Vượt kháng cự"},
            ]
        },
    }

    metrics = apply_decision_metrics(result, analysis_context_pack_overview=_overview())

    components = metrics["score_breakdown"]["components"]
    assert sum(item["score"] for item in components.values()) == 45
    assert all(item["score"] <= item["max_score"] for item in components.values())
    probabilities = [
        item["probability_pct"]
        for item in metrics["scenario_outlook"]["scenarios"]
    ]
    assert probabilities == [20, 30, 50]


def test_invalid_plan_omits_trade_probability_and_ev() -> None:
    result = _result(with_plan=False)

    metrics = apply_decision_metrics(result, analysis_context_pack_overview=_overview())

    expectancy = metrics["trade_expectancy"]
    assert expectancy["status"] == "unavailable"
    assert expectancy["win_probability_pct"] is None
    assert expectancy["expected_value_r"] is None


def test_markdown_renders_explainable_metrics_and_risk_matrix() -> None:
    result = _result()
    apply_decision_metrics(
        result,
        analysis_context_pack_overview=_overview(),
        market_data_quality={"ohlc_usable": True, "volume_usable": False},
        daily_market_context={"summary": "Thị trường thận trọng", "source": "history"},
    )

    output = render("markdown", [result], summary_only=False)

    assert output is not None
    assert "Điểm tổng: **35/100**" in output
    assert "Xu hướng" in output and "11/30" in output
    assert "Độ tin cậy dữ liệu" in output
    assert "Xác suất kịch bản" in output
    assert "Tiếp tục giảm" in output and "60%" in output
    assert "Expected Value" in output and "-0.25R" in output
    assert "Ma trận rủi ro" in output


def test_brief_and_wechat_keep_metrics_compact() -> None:
    result = _result()
    apply_decision_metrics(result, analysis_context_pack_overview=_overview())

    brief = render("brief", [result], summary_only=False)
    wechat = render("wechat", [result], summary_only=False)

    assert brief is not None and "35/100" in brief and "60%" in brief
    assert wechat is not None and "35/100" in wechat and "-0.25R" in wechat
