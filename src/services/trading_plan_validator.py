# -*- coding: utf-8 -*-
"""Deterministic validation and repair for long trading plans."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.report_language import infer_decision_type_from_advice
from src.services.market_symbol_utils import is_vn_market_symbol
from src.utils.sniper_points import parse_sniper_value
from src.utils.vietnamese_numbers import format_vnd_amount


logger = logging.getLogger(__name__)

MIN_RISK_REWARD_RATIO = Decimal("1.5")
DEFAULT_STOP_LOSS_FACTOR = Decimal("0.96")
DEFAULT_TARGET_FACTOR = Decimal("1.08")
PRICE_QUANTUM = Decimal("0.01")

TRADING_PLAN_CONSTRAINTS_PROMPT = """## Trading plan constraints

```json
"trading_plan_constraints": {
  "rule": "For a Long position, values MUST strictly satisfy: stop_loss < ideal_buy <= secondary_buy < take_profit",
  "math_check": "Ensure (take_profit - ideal_buy) / (ideal_buy - stop_loss) >= 1.5",
  "numeric_output": "Return all four price levels as positive JSON numbers without labels, currency suffixes, ranges, or explanatory text",
  "failure_behavior": "If a defensible ideal_buy cannot be produced from supplied evidence, downgrade to hold/watch instead of inventing a price"
}
```
"""

# Agent prompt templates are formatted with ``str.format`` and therefore need
# literal JSON braces escaped until the final prompt is built.
TRADING_PLAN_CONSTRAINTS_PROMPT_FORMAT = TRADING_PLAN_CONSTRAINTS_PROMPT.replace(
    "{", "{{"
).replace("}", "}}")


class LongTradingPlan(BaseModel):
    """Strict numeric contract for an actionable long trading plan."""

    model_config = ConfigDict(frozen=True)

    ideal_buy: Decimal = Field(gt=0)
    secondary_buy: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    take_profit: Decimal = Field(gt=0)

    @property
    def risk_reward_ratio(self) -> Decimal:
        risk = self.ideal_buy - self.stop_loss
        reward = self.take_profit - self.ideal_buy
        return reward / risk

    @model_validator(mode="after")
    def validate_long_geometry(self) -> "LongTradingPlan":
        if self.stop_loss >= self.ideal_buy:
            raise ValueError("stop_loss must be below ideal_buy")
        if self.ideal_buy > self.secondary_buy:
            raise ValueError("ideal_buy must be at or below secondary_buy")
        if self.secondary_buy >= self.take_profit:
            raise ValueError("secondary_buy must be below take_profit")
        if self.risk_reward_ratio < MIN_RISK_REWARD_RATIO:
            raise ValueError("risk/reward ratio must be at least 1.5")
        return self


@dataclass(frozen=True)
class TradingPlanValidationResult:
    ideal_buy: Optional[Decimal]
    secondary_buy: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    quality_status: str
    warnings: tuple[str, ...]
    risk_reward_ratio: Optional[Decimal]
    is_valid: bool

    def metadata(self, *, include_vnd_display: bool = True) -> dict[str, Any]:
        display: dict[str, str] = {}
        if include_vnd_display and self.is_valid and self.ideal_buy is not None:
            if self.stop_loss is not None:
                display["stop_loss"] = format_stop_loss(self.stop_loss, self.ideal_buy)
            if self.take_profit is not None:
                display["take_profit"] = format_target(self.take_profit, self.ideal_buy)
            if self.risk_reward_ratio is not None:
                display["risk_reward"] = format_risk_reward(self.risk_reward_ratio)
        return {
            "quality_status": self.quality_status,
            "warnings": list(self.warnings),
            "risk_reward_ratio": (
                float(self.risk_reward_ratio) if self.risk_reward_ratio is not None else None
            ),
            "display": display,
        }


class TradingPlanValidator:
    """Validate LLM price levels and deterministically repair safe violations."""

    @classmethod
    def validate(
        cls,
        *,
        ideal_buy: Any,
        secondary_buy: Any,
        stop_loss: Any,
        take_profit: Any,
    ) -> LongTradingPlan:
        return LongTradingPlan(
            ideal_buy=cls._required_price(ideal_buy, "ideal_buy"),
            secondary_buy=cls._required_price(secondary_buy, "secondary_buy"),
            stop_loss=cls._required_price(stop_loss, "stop_loss"),
            take_profit=cls._required_price(take_profit, "take_profit"),
        )

    @classmethod
    def validate_and_fix(
        cls,
        *,
        ideal_buy: Any,
        secondary_buy: Any,
        stop_loss: Any,
        take_profit: Any,
    ) -> TradingPlanValidationResult:
        warnings: list[str] = []
        ideal = cls._price(ideal_buy)
        secondary = cls._price(secondary_buy)
        stop = cls._price(stop_loss)
        target = cls._price(take_profit)

        if ideal is None:
            return TradingPlanValidationResult(
                ideal_buy=None,
                secondary_buy=secondary,
                stop_loss=stop,
                take_profit=target,
                quality_status="invalid",
                warnings=("ideal_buy_missing_or_invalid",),
                risk_reward_ratio=None,
                is_valid=False,
            )

        ideal = cls._round_price(ideal)
        secondary = cls._round_price(secondary) if secondary is not None else None
        stop = cls._round_price(stop) if stop is not None else None
        target = cls._round_price(target) if target is not None else None

        if secondary is None:
            secondary = ideal
            warnings.append("secondary_buy_missing_or_invalid")
        elif secondary < ideal:
            secondary = ideal
            warnings.append("secondary_buy_below_ideal")

        if stop is None:
            stop = cls._round_price(ideal * DEFAULT_STOP_LOSS_FACTOR)
            warnings.append("stop_loss_missing_or_invalid")
        elif stop >= ideal:
            stop = cls._round_price(ideal * DEFAULT_STOP_LOSS_FACTOR)
            warnings.append("stop_loss_not_below_ideal")

        if stop <= 0 or stop >= ideal:
            return cls._invalid_result(
                ideal=ideal,
                secondary=secondary,
                stop=stop,
                target=target,
                warnings=warnings + ["unable_to_auto_fix_stop_loss"],
            )

        if target is None:
            target = cls._round_price(ideal * DEFAULT_TARGET_FACTOR)
            warnings.append("target_missing_or_invalid")
        elif target <= secondary:
            target = cls._round_price(ideal * DEFAULT_TARGET_FACTOR)
            warnings.append("target_not_above_secondary")

        if target <= secondary:
            target = secondary + PRICE_QUANTUM

        risk = ideal - stop
        reward = target - ideal
        if reward / risk < MIN_RISK_REWARD_RATIO:
            minimum_target = ideal + (MIN_RISK_REWARD_RATIO * risk)
            target = cls._round_price_up(max(target, minimum_target))
            warnings.append("risk_reward_below_minimum")

        if target <= secondary:
            target = secondary + PRICE_QUANTUM
            if "risk_reward_below_minimum" not in warnings:
                warnings.append("risk_reward_below_minimum")

        try:
            plan = LongTradingPlan(
                ideal_buy=ideal,
                secondary_buy=secondary,
                stop_loss=stop,
                take_profit=target,
            )
        except ValidationError:
            return cls._invalid_result(
                ideal=ideal,
                secondary=secondary,
                stop=stop,
                target=target,
                warnings=warnings + ["post_fix_validation_failed"],
            )

        ratio = plan.risk_reward_ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return TradingPlanValidationResult(
            ideal_buy=plan.ideal_buy,
            secondary_buy=plan.secondary_buy,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            quality_status="auto_fixed" if warnings else "valid",
            warnings=tuple(dict.fromkeys(warnings)),
            risk_reward_ratio=ratio,
            is_valid=True,
        )

    @staticmethod
    def _price(value: Any) -> Optional[Decimal]:
        if isinstance(value, bool):
            return None
        if isinstance(value, Decimal):
            parsed = value
        else:
            numeric = parse_sniper_value(value)
            if numeric is None:
                return None
            try:
                parsed = Decimal(str(numeric))
            except (InvalidOperation, ValueError):
                return None
        if not parsed.is_finite() or parsed <= 0:
            return None
        return parsed

    @classmethod
    def _required_price(cls, value: Any, field_name: str) -> Decimal:
        parsed = cls._price(value)
        if parsed is None:
            raise ValueError(f"{field_name} must be a positive finite price")
        return cls._round_price(parsed)

    @staticmethod
    def _round_price(value: Decimal) -> Decimal:
        return value.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _round_price_up(value: Decimal) -> Decimal:
        return value.quantize(PRICE_QUANTUM, rounding=ROUND_CEILING)

    @staticmethod
    def _invalid_result(
        *,
        ideal: Optional[Decimal],
        secondary: Optional[Decimal],
        stop: Optional[Decimal],
        target: Optional[Decimal],
        warnings: list[str],
    ) -> TradingPlanValidationResult:
        return TradingPlanValidationResult(
            ideal_buy=ideal,
            secondary_buy=secondary,
            stop_loss=stop,
            take_profit=target,
            quality_status="invalid",
            warnings=tuple(dict.fromkeys(warnings)),
            risk_reward_ratio=None,
            is_valid=False,
        )


def apply_trading_plan_validation(result: Any) -> list[str]:
    """Apply the long-plan gateway to an AnalysisResult-like object in place."""

    if result is None:
        return []
    dashboard = result.dashboard if isinstance(getattr(result, "dashboard", None), dict) else {}
    result.dashboard = dashboard
    battle_plan = dashboard.get("battle_plan")
    if not isinstance(battle_plan, dict):
        battle_plan = {}
        dashboard["battle_plan"] = battle_plan
    sniper_points = battle_plan.get("sniper_points")
    if not isinstance(sniper_points, dict):
        sniper_points = {}
        battle_plan["sniper_points"] = sniper_points

    inferred = infer_decision_type_from_advice(
        getattr(result, "operation_advice", ""),
        default=getattr(result, "decision_type", "hold") or "hold",
    )
    has_long_plan = any(
        parse_sniper_value(sniper_points.get(field)) is not None
        for field in ("ideal_buy", "secondary_buy", "stop_loss", "take_profit")
    )
    if getattr(result, "decision_type", "") != "buy" and inferred != "buy" and not has_long_plan:
        return []

    validation = TradingPlanValidator.validate_and_fix(
        ideal_buy=sniper_points.get("ideal_buy"),
        secondary_buy=sniper_points.get("secondary_buy"),
        stop_loss=sniper_points.get("stop_loss"),
        take_profit=sniper_points.get("take_profit"),
    )
    battle_plan["trading_plan_validation"] = validation.metadata(
        include_vnd_display=is_vn_market_symbol(str(getattr(result, "code", "")))
    )

    if validation.is_valid:
        sniper_points.update(
            {
                "ideal_buy": _decimal_to_number(validation.ideal_buy),
                "secondary_buy": _decimal_to_number(validation.secondary_buy),
                "stop_loss": _decimal_to_number(validation.stop_loss),
                "take_profit": _decimal_to_number(validation.take_profit),
            }
        )
    if validation.quality_status == "auto_fixed":
        logger.warning(
            "[trading_plan_validator] Auto-fixed long plan for %s: %s",
            getattr(result, "code", "unknown"),
            list(validation.warnings),
        )
    elif validation.quality_status == "invalid":
        logger.warning(
            "[trading_plan_validator] Long plan remains invalid for %s: %s",
            getattr(result, "code", "unknown"),
            list(validation.warnings),
        )
    return list(validation.warnings)


def get_trading_plan_display(battle_plan: Any) -> dict[str, str]:
    """Return trusted derived display values from validation metadata."""

    if not isinstance(battle_plan, dict):
        return {}
    validation = battle_plan.get("trading_plan_validation")
    if not isinstance(validation, dict) or validation.get("quality_status") == "invalid":
        return {}
    display = validation.get("display")
    if not isinstance(display, dict):
        return {}
    return {
        key: str(value)
        for key, value in display.items()
        if key in {"stop_loss", "take_profit", "risk_reward"} and value
    }


def _decimal_to_number(value: Optional[Decimal]) -> Optional[int | float]:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _format_vnd_price(value: Decimal) -> str:
    return format_vnd_amount(value)


def format_stop_loss(stop_loss: Decimal, ideal_buy: Decimal) -> str:
    delta = ((stop_loss - ideal_buy) / ideal_buy) * Decimal("100")
    return f"{_format_vnd_price(stop_loss)} ({delta:.1f}%)"


def format_target(take_profit: Decimal, ideal_buy: Decimal) -> str:
    delta = ((take_profit - ideal_buy) / ideal_buy) * Decimal("100")
    return f"{_format_vnd_price(take_profit)} ({delta:+.1f}%)"


def format_risk_reward(ratio: Decimal) -> str:
    rendered = f"{ratio:.2f}".rstrip("0").rstrip(".")
    return f"R:R = 1 : {rendered}"
