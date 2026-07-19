# -*- coding: utf-8 -*-
"""Behavior tests for the deterministic settlement-risk MVP."""

from __future__ import annotations

import math
from datetime import date, timedelta

from src.services.settlement_risk_service import (
    SettlementRiskPolicy,
    SettlementRiskService,
)
from src.analyzer import AnalysisResult
from src.settlement_risk_guardrail import apply_settlement_risk_guardrail


def _bars(
    count: int = 120,
    *,
    daily_return: float = 0.001,
    spread_pct: float = 0.01,
    volume: float | None = 1_000_000,
) -> list[dict]:
    rows = []
    price = 100.0
    start = date(2026, 1, 1)
    for index in range(count):
        open_price = price
        close = price * (1.0 + daily_return)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": open_price,
                "high": max(open_price, close) * (1.0 + spread_pct),
                "low": min(open_price, close) * (1.0 - spread_pct),
                "close": close,
                "volume": volume,
            }
        )
        price = close
    return rows


def test_complete_history_is_deterministic_and_versioned() -> None:
    service = SettlementRiskService()
    rows = _bars()

    first = service.assess(rows, support_level=108.0).model_dump()
    second = service.assess(rows, support_level=108.0).model_dump()

    assert first == second
    assert first["policy_version"] == "vn-settlement-risk-v1"
    assert first["sample_count"] == 118
    assert first["two_session_return_quantiles"] is not None
    assert first["three_session_return_quantiles"] is not None
    assert first["data_quality"] == "good"
    assert math.isclose(sum(first["component_weights"].values()), 1.0, abs_tol=1e-5)


def test_insufficient_history_degrades_without_fabricated_confidence() -> None:
    estimate = SettlementRiskService().assess(_bars(8), support_level=99.0)

    assert estimate.data_quality == "insufficient"
    assert estimate.survivability_status == "insufficient_history"
    assert "low_sample_confidence" in estimate.warnings
    assert estimate.sample_count == 6


def test_missing_volume_renormalizes_available_weights() -> None:
    estimate = SettlementRiskService().assess(
        _bars(volume=None),
        support_level=108.0,
    )

    assert estimate.liquidity_quality is None
    assert "volume_history_missing" in estimate.warnings
    assert "liquidity" not in estimate.component_weights
    assert math.isclose(sum(estimate.component_weights.values()), 1.0, abs_tol=1e-5)


def test_zero_volume_and_possible_suspension_are_explicit() -> None:
    rows = _bars()
    for row in rows[:30]:
        row["volume"] = 0
        row["open"] = row["high"] = row["low"] = row["close"]

    estimate = SettlementRiskService().assess(rows, support_level=105.0)

    assert estimate.liquidity_quality == "poor"
    assert "possible_suspension_sessions" in estimate.warnings


def test_high_volatility_and_large_gaps_score_worse_than_low_volatility() -> None:
    calm = _bars(daily_return=0.001, spread_pct=0.003)
    volatile = _bars(daily_return=0.012, spread_pct=0.06)
    for index in range(1, len(volatile), 4):
        volatile[index]["open"] = volatile[index - 1]["close"] * 0.90
        volatile[index]["low"] = min(
            volatile[index]["low"],
            volatile[index]["open"] * 0.95,
        )

    calm_estimate = SettlementRiskService().assess(calm, support_level=108.0)
    volatile_estimate = SettlementRiskService().assess(
        volatile,
        support_level=150.0,
    )

    assert volatile_estimate.atr_pct > calm_estimate.atr_pct
    assert volatile_estimate.gap_down_frequency > calm_estimate.gap_down_frequency
    assert volatile_estimate.survivability_score < calm_estimate.survivability_score


def test_missing_support_omits_support_components_instead_of_using_neutral_values() -> None:
    estimate = SettlementRiskService().assess(_bars(), support_level=None)

    assert estimate.support_buffer_pct is None
    assert estimate.invalidation_buffer_pct is None
    assert estimate.historical_invalidation_touch_frequency is None
    assert "deterministic_support_unavailable" in estimate.warnings
    assert "support_coverage" not in estimate.component_weights
    assert "historical_invalidation_survival" not in estimate.component_weights


def test_invalid_and_abnormal_bars_are_rejected_explicitly() -> None:
    rows = _bars()
    rows.extend(
        [
            {"date": "2027-01-01", "open": math.nan, "high": 2, "low": 1, "close": 1.5},
            {"date": "2027-01-02", "open": 1, "high": math.inf, "low": 1, "close": 1},
            {"date": "2027-01-03", "open": 0, "high": 1, "low": 0.5, "close": 0.8},
            {"date": "2027-01-04", "open": 10, "high": 9, "low": 8, "close": 10},
        ]
    )

    estimate = SettlementRiskService().assess(rows, support_level=108.0)

    assert "invalid_ohlc_bar_rejected" in estimate.warnings
    assert "abnormal_ohlc_bar_rejected" in estimate.warnings
    assert estimate.lookback_sessions == 120


def test_duplicate_sessions_are_rejected_before_rolling_windows() -> None:
    rows = _bars()
    rows.append(dict(rows[-1]))

    estimate = SettlementRiskService().assess(rows, support_level=108.0)

    assert "duplicate_session_rejected" in estimate.warnings
    assert estimate.lookback_sessions == 120
    assert estimate.sample_count == 118


def test_policy_weight_renormalization_is_reproducible() -> None:
    policy = SettlementRiskPolicy(
        component_weights={
            "expected_adverse_move": 0.8,
            "liquidity": 0.2,
        }
    )
    estimate = SettlementRiskService(policy).assess(_bars(volume=None))

    assert estimate.component_weights == {"expected_adverse_move": 1.0}


def test_unsafe_settlement_risk_downgrades_positive_entry_and_keeps_reason_codes() -> None:
    result = AnalysisResult(
        code="VNM.VN",
        name="Vinamilk",
        sentiment_score=80,
        trend_prediction="Tăng",
        operation_advice="Mua",
        decision_type="buy",
        report_language="vi",
        action="buy",
        reason_codes=["existing_reason"],
        dashboard={
            "core_conclusion": {
                "one_sentence": "Mua",
                "position_advice": {"no_position": "Mua"},
            }
        },
    )
    unsafe = SettlementRiskService(
        SettlementRiskPolicy(
            min_samples=1,
            good_quality_samples=1,
            unsafe_score=101.0,
        )
    ).assess(_bars(), support_level=108.0)

    adjustments = apply_settlement_risk_guardrail(result, unsafe.model_dump())

    assert adjustments == ["settlement_risk_entry_blocked"]
    assert result.action == "watch"
    assert result.decision_type == "hold"
    assert result.reason_codes == ["existing_reason", "settlement_risk_unsafe_entry"]
    assert result.settlement_risk["policy_version"] == "vn-settlement-risk-v1"
    assert result.dashboard["settlement_risk"] == result.settlement_risk


def test_old_report_without_settlement_risk_remains_unchanged() -> None:
    result = AnalysisResult(
        code="VNM.VN",
        name="Vinamilk",
        sentiment_score=50,
        trend_prediction="Đi ngang",
        operation_advice="Theo dõi",
        action="watch",
    )

    assert apply_settlement_risk_guardrail(result, None) == []
    assert result.action == "watch"
