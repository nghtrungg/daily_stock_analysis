from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.services.trading_plan_validator import (
    LongTradingPlan,
    TradingPlanValidator,
    apply_trading_plan_validation,
    format_risk_reward,
    format_stop_loss,
    format_target,
)


def test_long_plan_accepts_valid_geometry_and_exact_minimum_rr() -> None:
    plan = LongTradingPlan(
        ideal_buy=Decimal("100"),
        secondary_buy=Decimal("100"),
        stop_loss=Decimal("96"),
        take_profit=Decimal("106"),
    )

    assert plan.risk_reward_ratio == Decimal("1.5")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stop_loss", Decimal("100")),
        ("secondary_buy", Decimal("99")),
        ("take_profit", Decimal("100")),
    ],
)
def test_long_plan_rejects_invalid_price_geometry(field: str, value: Decimal) -> None:
    payload = {
        "ideal_buy": Decimal("100"),
        "secondary_buy": Decimal("100"),
        "stop_loss": Decimal("96"),
        "take_profit": Decimal("106"),
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        LongTradingPlan(**payload)


def test_validator_repairs_inverted_stop_loss_from_reported_regression() -> None:
    result = TradingPlanValidator.validate_and_fix(
        ideal_buy="21,500 VND",
        secondary_buy="22,000",
        stop_loss="22,500",
        take_profit="24,500",
    )

    assert result.quality_status == "auto_fixed"
    assert result.stop_loss == Decimal("20640.00")
    assert result.take_profit == Decimal("24500.00")
    assert result.is_valid is True
    assert "stop_loss_not_below_ideal" in result.warnings
    assert result.risk_reward_ratio == Decimal("3.49")


def test_validator_repairs_missing_secondary_and_invalid_target() -> None:
    result = TradingPlanValidator.validate_and_fix(
        ideal_buy=Decimal("21500"),
        secondary_buy="N/A",
        stop_loss=Decimal("20640"),
        take_profit=Decimal("21000"),
    )

    assert result.secondary_buy == Decimal("21500.00")
    assert result.take_profit == Decimal("23220.00")
    assert result.quality_status == "auto_fixed"
    assert result.is_valid is True
    assert set(result.warnings) == {
        "secondary_buy_missing_or_invalid",
        "target_not_above_secondary",
    }


def test_validator_raises_target_when_geometry_passes_but_rr_is_too_low() -> None:
    result = TradingPlanValidator.validate_and_fix(
        ideal_buy=Decimal("100"),
        secondary_buy=Decimal("100.50"),
        stop_loss=Decimal("99"),
        take_profit=Decimal("101.20"),
    )

    assert result.take_profit == Decimal("101.50")
    assert result.risk_reward_ratio == Decimal("1.50")
    assert result.warnings == ("risk_reward_below_minimum",)
    assert result.is_valid is True


def test_validator_does_not_invent_missing_ideal_buy() -> None:
    result = TradingPlanValidator.validate_and_fix(
        ideal_buy="Cần bổ sung",
        secondary_buy=Decimal("22000"),
        stop_loss=Decimal("21000"),
        take_profit=Decimal("24000"),
    )

    assert result.quality_status == "invalid"
    assert result.is_valid is False
    assert result.ideal_buy is None
    assert result.warnings == ("ideal_buy_missing_or_invalid",)


def test_display_helpers_keep_canonical_values_out_of_presentation_logic() -> None:
    assert format_stop_loss(Decimal("21000"), Decimal("21500")) == "21.000 VND (-2.3%)"
    assert format_target(Decimal("24500"), Decimal("21500")) == "24.500 VND (+14.0%)"
    assert format_risk_reward(Decimal("2.5")) == "R:R = 1 : 2.5"


def test_non_vietnam_compatibility_keeps_vnd_display_metadata_empty() -> None:
    result = SimpleNamespace(
        code="600519",
        decision_type="buy",
        operation_advice="买入",
        dashboard={
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": 100,
                    "secondary_buy": 101,
                    "stop_loss": 95,
                    "take_profit": 110,
                }
            }
        },
    )

    warnings = apply_trading_plan_validation(result)

    assert warnings == []
    validation = result.dashboard["battle_plan"]["trading_plan_validation"]
    assert validation["quality_status"] == "valid"
    assert validation["display"] == {}


def test_watch_decision_validates_rendered_long_plan() -> None:
    result = SimpleNamespace(
        code="MBB.VN",
        decision_type="hold",
        operation_advice="Đứng ngoài quan sát",
        dashboard={
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": 22500,
                    "secondary_buy": 22800,
                    "stop_loss": 21800,
                    "take_profit": 24000,
                }
            }
        },
    )

    warnings = apply_trading_plan_validation(result)

    assert warnings == []
    validation = result.dashboard["battle_plan"]["trading_plan_validation"]
    assert validation["quality_status"] == "valid"
    assert validation["display"]["stop_loss"] == "21.800 VND (-3.1%)"
    assert validation["display"]["take_profit"] == "24.000 VND (+6.7%)"
    assert validation["display"]["risk_reward"] == "R:R = 1 : 2.14"
