from types import SimpleNamespace

from src.analyzer import AnalysisResult
from src.services.market_data_quality import (
    apply_market_data_quality_guardrail,
    reconcile_daily_bar,
)


def test_reconcile_does_not_build_impossible_ohlc_from_previous_close() -> None:
    bar, quality = reconcile_daily_bar(
        historical_bar={"date": "2026-07-20", "close": 22800, "volume": 20_670_000},
        realtime_bar={
            "date": "2026-07-21",
            "open": None,
            "high": 22700,
            "low": 22700,
            "close": 22700,
            "volume": 966_000,
        },
        market_date="2026-07-21",
        previous_volume=20_670_000,
        is_partial_bar=False,
    )

    assert bar["close"] == 22700
    assert "open" not in bar
    assert "high" not in bar
    assert "low" not in bar
    assert quality["ohlc_usable"] is False
    assert quality["volume_usable"] is False
    assert "realtime_ohlc_incomplete" in quality["issues"]
    assert "volume_unconfirmed_outlier" in quality["issues"]


def test_reconcile_prefers_valid_same_day_daily_bar_over_invalid_realtime_bar() -> None:
    bar, quality = reconcile_daily_bar(
        historical_bar={
            "date": "2026-07-21",
            "open": 22800,
            "high": 23050,
            "low": 22600,
            "close": 22700,
            "volume": 20_000_000,
            "data_source": "daily-provider",
        },
        realtime_bar={
            "date": "2026-07-21",
            "open": 22800,
            "high": 22700,
            "low": 22700,
            "close": 22700,
            "volume": 966_000,
            "data_source": "realtime-provider",
        },
        market_date="2026-07-21",
        previous_volume=20_670_000,
        is_partial_bar=False,
    )

    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (
        22800,
        23050,
        22600,
        22700,
    )
    assert bar["volume"] == 20_000_000
    assert quality["ohlc_usable"] is True
    assert quality["ohlc_source"] == "historical_daily"
    assert quality["volume_usable"] is False
    assert "volume_source_conflict" in quality["issues"]


def test_partial_volume_is_not_promoted_to_daily_volume_signal() -> None:
    bar, quality = reconcile_daily_bar(
        historical_bar={"date": "2026-07-20", "close": 22800, "volume": 20_670_000},
        realtime_bar={
            "date": "2026-07-21",
            "open": 22800,
            "high": 23050,
            "low": 22600,
            "close": 22700,
            "volume": 966_000,
        },
        market_date="2026-07-21",
        previous_volume=20_670_000,
        is_partial_bar=True,
    )

    assert bar["volume"] == 966_000
    assert quality["volume_usable"] is False
    assert quality["volume_confirmation"] == "partial_session"
    assert "partial_session_volume" in quality["issues"]


def test_completed_session_prefers_daily_ohlc_when_valid_sources_disagree() -> None:
    bar, quality = reconcile_daily_bar(
        historical_bar={
            "date": "2026-07-21",
            "open": 22800,
            "high": 23050,
            "low": 22600,
            "close": 22700,
            "volume": 20_000_000,
        },
        realtime_bar={
            "date": "2026-07-21",
            "open": 22700,
            "high": 22700,
            "low": 22700,
            "close": 22700,
            "volume": 20_000_000,
        },
        market_date="2026-07-21",
        previous_volume=20_670_000,
        is_partial_bar=False,
    )

    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (
        22800,
        23050,
        22600,
        22700,
    )
    assert quality["ohlc_source"] == "historical_daily"
    assert "ohlc_source_conflict" in quality["issues"]


def test_invalid_ohlc_downgrades_action_and_suppresses_volume_claim() -> None:
    result = AnalysisResult(
        code="MBB.VN",
        name="MB Bank",
        sentiment_score=35,
        trend_prediction="Giảm",
        operation_advice="Bán",
        decision_type="sell",
        action="sell",
        confidence_level="Cao",
        dashboard={
            "core_conclusion": {"one_sentence": "Bán ngay", "signal_type": "Bán"},
            "data_perspective": {
                "volume_analysis": {
                    "volume_ratio": 0.05,
                    "volume_status": "Cạn kiệt",
                    "volume_meaning": "Thanh khoản mất hút",
                }
            },
            "phase_decision": {"data_limitations": []},
        },
    )

    changes = apply_market_data_quality_guardrail(
        result,
        {
            "status": "blocked",
            "ohlc_usable": False,
            "volume_usable": False,
            "issues": ["realtime_ohlc_invalid", "volume_unconfirmed_outlier"],
        },
        report_language="vi",
    )

    assert result.decision_type == "hold"
    assert result.action == "watch"
    assert result.operation_advice == "Theo dõi"
    assert result.confidence_level == "Thấp"
    volume = result.dashboard["data_perspective"]["volume_analysis"]
    assert volume["volume_ratio"] == "N/A"
    assert "chưa được xác nhận" in volume["volume_meaning"]
    assert "action_downgraded_invalid_ohlc" in changes


def test_unconfirmed_volume_keeps_order_flow_as_observation_not_a_signal() -> None:
    result = AnalysisResult(
        code="MBB.VN", name="MB Bank", report_language="vi", sentiment_score=35,
        trend_prediction="Giảm", operation_advice="Giảm tỷ trọng", decision_type="sell", action="reduce",
        dashboard={"core_conclusion": {"one_sentence": "Bán do Sell Down áp đảo."},
                   "data_perspective": {"price_position": {"current_price": 21750, "support_level": 21500},
                                        "order_flow": {"active_buy_volume": 26600, "active_sell_volume": 108800,
                                                       "active_imbalance": -0.61}},
                   "phase_decision": {"data_limitations": []}},
    )

    changes = apply_market_data_quality_guardrail(
        result,
        {"status": "warning", "ohlc_usable": True, "volume_usable": False,
         "issues": ["partial_session_volume"]}, report_language="vi",
    )

    flow = result.dashboard["data_perspective"]["order_flow"]
    assert "volume_signal_suppressed" in changes
    assert flow["inference_status"] == "observation_only"
    assert "không sử dụng riêng" in flow["note"]
    assert result.decision_type == "hold"
    assert result.action == "watch"
