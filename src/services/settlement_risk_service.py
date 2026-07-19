# -*- coding: utf-8 -*-
"""Deterministic settlement-window risk estimates for Vietnam equities."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from src.schemas.settlement_risk import ReturnQuantiles, SettlementRiskEstimate


@dataclass(frozen=True)
class SettlementRiskPolicy:
    """One versioned policy object for all score constants and thresholds."""

    version: str = "vn-settlement-risk-v1"
    lookback_sessions: int = 120
    settlement_sessions: int = 2
    min_samples: int = 30
    good_quality_samples: int = 80
    atr_period: int = 14
    invalidation_atr_multiple: float = 0.5
    caution_score: float = 70.0
    unsafe_score: float = 40.0
    adverse_scale_pct: float = 8.0
    excursion_scale_pct: float = 12.0
    component_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "expected_adverse_move": 0.30,
            "maximum_adverse_excursion": 0.20,
            "historical_invalidation_survival": 0.25,
            "support_coverage": 0.15,
            "liquidity": 0.10,
        }
    )


@dataclass(frozen=True)
class _Bar:
    session: Any
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]


class SettlementRiskService:
    """Calculate reproducible historical settlement-window risk heuristics."""

    def __init__(self, policy: Optional[SettlementRiskPolicy] = None) -> None:
        self.policy = policy or SettlementRiskPolicy()

    def assess(
        self,
        ohlcv: Any,
        *,
        support_level: Optional[float] = None,
        settlement_sessions: Optional[int] = None,
    ) -> SettlementRiskEstimate:
        sessions = (
            self.policy.settlement_sessions
            if settlement_sessions is None
            else int(settlement_sessions)
        )
        if sessions < 1:
            raise ValueError("settlement_sessions must be positive")

        bars, warnings = self._normalize_bars(ohlcv)
        bars = bars[-self.policy.lookback_sessions :]
        if not bars:
            return self._insufficient(sessions, 0, warnings + ["ohlcv_history_missing"])

        two_returns = _window_returns(bars, 2)
        three_returns = _window_returns(bars, 3)
        settlement_returns = _window_returns(bars, sessions)
        sample_count = len(settlement_returns)
        atr_pct = _atr_pct(bars, self.policy.atr_period)
        adverse_excursions = _adverse_excursions(bars, sessions)

        support = _positive_finite(support_level)
        current_close = bars[-1].close
        support_buffer = None
        invalidation_buffer = None
        touch_frequency = None
        if support is None or support >= current_close:
            warnings.append("deterministic_support_unavailable")
        else:
            support_buffer = max(0.0, (current_close - support) / current_close * 100.0)
            if atr_pct is not None:
                invalidation_buffer = (
                    support_buffer
                    + atr_pct * self.policy.invalidation_atr_multiple
                )
                touch_frequency = _invalidation_touch_frequency(
                    bars,
                    sessions,
                    invalidation_buffer,
                )
            else:
                warnings.append("invalidation_buffer_unavailable")

        liquidity_quality = _liquidity_quality(bars, warnings)
        expected_adverse = (
            max(0.0, -_quantile(settlement_returns, 0.05))
            if settlement_returns
            else None
        )
        expected_favorable = (
            max(0.0, _quantile(settlement_returns, 0.95))
            if settlement_returns
            else None
        )
        maximum_adverse = max(adverse_excursions) if adverse_excursions else None

        components: Dict[str, float] = {}
        if expected_adverse is not None:
            components["expected_adverse_move"] = _inverse_scaled_score(
                expected_adverse,
                self.policy.adverse_scale_pct,
            )
        if maximum_adverse is not None:
            components["maximum_adverse_excursion"] = _inverse_scaled_score(
                maximum_adverse,
                self.policy.excursion_scale_pct,
            )
        if touch_frequency is not None:
            components["historical_invalidation_survival"] = (
                1.0 - touch_frequency
            ) * 100.0
        if invalidation_buffer is not None and expected_adverse is not None:
            components["support_coverage"] = _coverage_score(
                invalidation_buffer,
                expected_adverse,
            )
        if liquidity_quality is not None:
            components["liquidity"] = {
                "good": 100.0,
                "limited": 55.0,
                "poor": 20.0,
            }[liquidity_quality]

        score, normalized_weights = self._weighted_score(components)
        data_quality = (
            "good"
            if sample_count >= self.policy.good_quality_samples
            else "limited"
            if sample_count >= self.policy.min_samples
            else "insufficient"
        )
        if data_quality == "insufficient":
            warnings.append("low_sample_confidence")
            status = "insufficient_history"
        elif score is None:
            status = "insufficient_history"
            warnings.append("score_components_unavailable")
        elif score < self.policy.unsafe_score:
            status = "unsafe"
        elif score < self.policy.caution_score:
            status = "caution"
        else:
            status = "survivable"

        risk_level = None
        if score is not None:
            risk_level = (
                "high"
                if score < self.policy.unsafe_score
                else "medium"
                if score < self.policy.caution_score
                else "low"
            )

        return SettlementRiskEstimate(
            lookback_sessions=len(bars),
            settlement_sessions=sessions,
            two_session_return_quantiles=_quantile_summary(two_returns),
            three_session_return_quantiles=_quantile_summary(three_returns),
            atr_pct=_round_optional(atr_pct),
            expected_adverse_move_pct=_round_optional(expected_adverse),
            expected_favorable_move_pct=_round_optional(expected_favorable),
            maximum_adverse_excursion_pct=_round_optional(maximum_adverse),
            gap_down_frequency=_round_optional(_gap_down_frequency(bars), 6),
            support_buffer_pct=_round_optional(support_buffer),
            invalidation_buffer_pct=_round_optional(invalidation_buffer),
            historical_invalidation_touch_frequency=_round_optional(
                touch_frequency,
                6,
            ),
            liquidity_quality=liquidity_quality,
            survivability_score=_round_optional(score, 2),
            risk_level=risk_level,
            survivability_status=status,
            sample_count=sample_count,
            data_quality=data_quality,
            warnings=_dedupe(warnings),
            policy_version=self.policy.version,
            component_weights=normalized_weights,
        )

    def _normalize_bars(self, raw: Any) -> tuple[List[_Bar], List[str]]:
        records = _records(raw)
        warnings: List[str] = []
        normalized: List[_Bar] = []
        for index, record in enumerate(records):
            lowered = {str(key).strip().lower(): value for key, value in record.items()}
            open_price = _positive_finite(_first(lowered, "open", "open_price"))
            high = _positive_finite(_first(lowered, "high", "high_price"))
            low = _positive_finite(_first(lowered, "low", "low_price"))
            close = _positive_finite(_first(lowered, "close", "close_price"))
            if None in (open_price, high, low, close):
                warnings.append("invalid_ohlc_bar_rejected")
                continue
            assert open_price is not None and high is not None
            assert low is not None and close is not None
            if high < max(open_price, close, low) or low > min(open_price, close, high):
                warnings.append("abnormal_ohlc_bar_rejected")
                continue
            raw_volume = _first(lowered, "volume", "vol")
            volume = _non_negative_finite(raw_volume)
            if raw_volume is not None and volume is None:
                warnings.append("invalid_volume_treated_as_missing")
            session = _first(lowered, "date", "trade_date", "datetime", "timestamp")
            normalized.append(
                _Bar(
                    session=_sortable_session(session, index),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )
        normalized.sort(key=lambda bar: bar.session)
        deduplicated: List[_Bar] = []
        seen_sessions = set()
        for bar in normalized:
            if bar.session[0] == 0 and bar.session in seen_sessions:
                warnings.append("duplicate_session_rejected")
                continue
            seen_sessions.add(bar.session)
            deduplicated.append(bar)
        return deduplicated, warnings

    def _weighted_score(
        self,
        components: Mapping[str, float],
    ) -> tuple[Optional[float], Dict[str, float]]:
        available = {
            key: self.policy.component_weights[key]
            for key in components
            if key in self.policy.component_weights
        }
        total_weight = sum(available.values())
        if total_weight <= 0:
            return None, {}
        normalized = {
            key: round(weight / total_weight, 6)
            for key, weight in available.items()
        }
        score = sum(components[key] * weight for key, weight in normalized.items())
        return max(0.0, min(100.0, score)), normalized

    def _insufficient(
        self,
        sessions: int,
        sample_count: int,
        warnings: Sequence[str],
    ) -> SettlementRiskEstimate:
        return SettlementRiskEstimate(
            lookback_sessions=0,
            settlement_sessions=sessions,
            survivability_status="insufficient_history",
            sample_count=sample_count,
            data_quality="insufficient",
            warnings=_dedupe(list(warnings) + ["low_sample_confidence"]),
            policy_version=self.policy.version,
        )


def _records(raw: Any) -> List[Mapping[str, Any]]:
    if raw is None:
        return []
    to_dict = getattr(raw, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict(orient="records")
            if isinstance(records, list):
                return [item for item in records if isinstance(item, Mapping)]
        except TypeError:
            pass
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        return [item for item in raw if isinstance(item, Mapping)]
    return []


def _window_returns(bars: Sequence[_Bar], sessions: int) -> List[float]:
    return [
        (bars[index + sessions].close / bars[index].close - 1.0) * 100.0
        for index in range(max(0, len(bars) - sessions))
    ]


def _adverse_excursions(bars: Sequence[_Bar], sessions: int) -> List[float]:
    values: List[float] = []
    for index in range(max(0, len(bars) - sessions)):
        entry = bars[index].close
        future_low = min(
            bar.low for bar in bars[index + 1 : index + sessions + 1]
        )
        values.append(max(0.0, (entry - future_low) / entry * 100.0))
    return values


def _atr_pct(bars: Sequence[_Bar], period: int) -> Optional[float]:
    if len(bars) < 2:
        return None
    true_ranges = []
    for previous, current in zip(bars, bars[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    selected = true_ranges[-period:]
    if not selected or bars[-1].close <= 0:
        return None
    return sum(selected) / len(selected) / bars[-1].close * 100.0


def _invalidation_touch_frequency(
    bars: Sequence[_Bar],
    sessions: int,
    invalidation_buffer_pct: float,
) -> Optional[float]:
    observations = max(0, len(bars) - sessions)
    if observations == 0:
        return None
    touched = 0
    for index in range(observations):
        threshold = bars[index].close * (1.0 - invalidation_buffer_pct / 100.0)
        if min(bar.low for bar in bars[index + 1 : index + sessions + 1]) <= threshold:
            touched += 1
    return touched / observations


def _gap_down_frequency(bars: Sequence[_Bar]) -> Optional[float]:
    if len(bars) < 2:
        return None
    return sum(current.open < previous.close for previous, current in zip(bars, bars[1:])) / (
        len(bars) - 1
    )


def _liquidity_quality(bars: Sequence[_Bar], warnings: List[str]) -> Optional[str]:
    volumes = [bar.volume for bar in bars if bar.volume is not None]
    if not volumes:
        warnings.append("volume_history_missing")
        return None
    if len(volumes) < len(bars):
        warnings.append("volume_history_partial")
    zero_count = sum(volume == 0 for volume in volumes)
    flat_zero_count = sum(
        bar.volume == 0 and bar.open == bar.high == bar.low == bar.close
        for bar in bars
        if bar.volume is not None
    )
    if flat_zero_count:
        warnings.append("possible_suspension_sessions")
    zero_frequency = zero_count / len(volumes)
    if zero_frequency >= 0.20:
        return "poor"
    if zero_frequency > 0 or len(volumes) < len(bars):
        return "limited"
    return "good"


def _quantile_summary(values: Sequence[float]) -> Optional[ReturnQuantiles]:
    if not values:
        return None
    return ReturnQuantiles(
        p05=round(_quantile(values, 0.05), 4),
        p25=round(_quantile(values, 0.25), 4),
        p50=round(_quantile(values, 0.50), 4),
        p75=round(_quantile(values, 0.75), 4),
        p95=round(_quantile(values, 0.95), 4),
    )


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _inverse_scaled_score(value: float, scale: float) -> float:
    return max(0.0, min(100.0, 100.0 * (1.0 - value / scale)))


def _coverage_score(buffer_pct: float, adverse_pct: float) -> float:
    if adverse_pct <= 0:
        return 100.0
    return max(0.0, min(100.0, buffer_pct / adverse_pct * 100.0))


def _positive_finite(value: Any) -> Optional[float]:
    number = _finite_number(value)
    return number if number is not None and number > 0 else None


def _non_negative_finite(value: Any) -> Optional[float]:
    number = _finite_number(value)
    return number if number is not None and number >= 0 else None


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(values: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in values:
            return values[key]
    return None


def _sortable_session(value: Any, fallback: int) -> tuple[int, Any]:
    if isinstance(value, datetime):
        return (0, value.isoformat())
    if isinstance(value, date):
        return (0, value.isoformat())
    text = str(value or "").strip()
    return (0, text) if text else (1, fallback)


def _round_optional(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def _dedupe(values: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))
