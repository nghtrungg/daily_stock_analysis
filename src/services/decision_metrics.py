# -*- coding: utf-8 -*-
"""Deterministic explainability metrics for completed stock reports.

The LLM may propose rationales and scenarios, but this module owns score
reconciliation, evidence confidence, probability normalization, and EV math.
It runs after the existing action, evidence, and market-data guardrails.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, Optional

from src.report_language import normalize_report_language
from src.schemas.decision_scale import score_band_metadata


SCORE_COMPONENT_MAXIMA: Dict[str, int] = {
    "trend": 30,
    "momentum": 20,
    "volume": 15,
    "market": 15,
    "fundamental": 20,
}

CONFIDENCE_FACTOR_WEIGHTS: Dict[str, int] = {
    "ohlc": 25,
    "trend": 25,
    "volume": 15,
    "market": 15,
    "news": 10,
    "fundamental": 10,
}

_SCENARIO_KEYS = ("downside", "sideways", "upside")

DECISION_METRICS_PROMPT = """## Explainable decision metrics

Include an optional `dashboard.decision_metrics` proposal with this exact shape:

```json
{
  "score_breakdown": {
    "components": {
      "trend": {"score": 0, "reason": "evidence-based rationale"},
      "momentum": {"score": 0, "reason": "evidence-based rationale"},
      "volume": {"score": 0, "reason": "evidence-based rationale"},
      "market": {"score": 0, "reason": "evidence-based rationale"},
      "fundamental": {"score": 0, "reason": "evidence-based rationale"}
    }
  },
  "scenario_outlook": {
    "horizon": "1-5 sessions",
    "probability_source": "model_estimate",
    "calibration_status": "uncalibrated",
    "scenarios": [
      {"key": "downside", "label": "localized label", "probability_pct": 0, "condition": "trigger", "target_price": 0, "invalidation": "condition", "recommended_action": "action", "rationale": "reason"},
      {"key": "sideways", "label": "localized label", "probability_pct": 0, "condition": "trigger", "target_price": 0, "invalidation": "condition", "recommended_action": "action", "rationale": "reason"},
      {"key": "upside", "label": "localized label", "probability_pct": 0, "condition": "trigger", "target_price": 0, "invalidation": "condition", "recommended_action": "action", "rationale": "reason"}
    ]
  }
}
```

Score maxima are trend 30, momentum 20, volume 15, market 15, and fundamental 20.
The five proposed scores should explain `sentiment_score`; never treat the score as a probability.
The three scenario probabilities must be mutually exclusive and sum to 100. Use only supplied support,
resistance, target, market, and volume evidence. Never invent a market-index level or confirmed-volume
trigger. Do not calculate evidence confidence, R:R, win probability, or EV; deterministic code owns them.
"""


def apply_decision_metrics(
    result: Any,
    *,
    analysis_context_pack_overview: Optional[Mapping[str, Any]] = None,
    market_data_quality: Optional[Mapping[str, Any]] = None,
    daily_market_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build and attach normalized decision metrics to an AnalysisResult-like object."""

    if result is None:
        return {}
    dashboard = _mapping(getattr(result, "dashboard", None))
    result.dashboard = dashboard
    proposed = _mapping(dashboard.get("decision_metrics"))
    language = normalize_report_language(getattr(result, "report_language", None) or "vi")
    score = _bounded_int(getattr(result, "sentiment_score", 50), 0, 100, default=50)

    score_breakdown = _build_score_breakdown(
        score,
        proposed=_mapping(proposed.get("score_breakdown")),
        language=language,
        volume_usable=_mapping(market_data_quality).get("volume_usable"),
    )
    evidence_confidence = _build_evidence_confidence(
        result,
        overview=analysis_context_pack_overview,
        market_data_quality=market_data_quality,
        daily_market_context=daily_market_context,
        language=language,
    )
    scenario_outlook = _build_scenario_outlook(
        result,
        proposed=_mapping(proposed.get("scenario_outlook")),
        score=score,
        language=language,
    )
    trade_expectancy = _build_trade_expectancy(result, scenario_outlook, language=language)
    _apply_expectancy_entry_gate(result, trade_expectancy, language=language)
    dashboard = _mapping(getattr(result, "dashboard", None))

    metrics = {
        "score_breakdown": score_breakdown,
        "evidence_confidence": evidence_confidence,
        "scenario_outlook": scenario_outlook,
        "trade_expectancy": trade_expectancy,
    }
    dashboard["decision_metrics"] = metrics
    result.dashboard = dashboard
    return metrics


def _build_score_breakdown(
    score: int,
    *,
    proposed: Dict[str, Any],
    language: str,
    volume_usable: Any = None,
) -> Dict[str, Any]:
    proposed_components = _mapping(proposed.get("components"))
    raw_scores: Dict[str, float] = {}
    reasons: Dict[str, str] = {}
    has_model_components = False
    for key, maximum in SCORE_COMPONENT_MAXIMA.items():
        item = _mapping(proposed_components.get(key))
        value = _finite_number(item.get("score"))
        if value is not None:
            raw_scores[key] = min(float(maximum), max(0.0, value))
            has_model_components = True
        else:
            raw_scores[key] = float(maximum)
        reason = str(item.get("reason") or "").strip()
        if reason:
            reasons[key] = reason

    # A partial or unconfirmed session volume must not be silently converted
    # into a score contribution. Keep the final composite score reconciled by
    # allocating its remaining evidence across the other components instead.
    if volume_usable is False:
        raw_scores["volume"] = 0.0
        reasons["volume"] = (
            "Khối lượng chưa được xác nhận; không dùng làm căn cứ chấm điểm hoặc ra lệnh."
            if language == "vi"
            else "Volume is unconfirmed and is excluded from scoring and trade decisions."
        )

    allocated = _allocate_integer_total(score, raw_scores, SCORE_COMPONENT_MAXIMA)
    fallback_reason = (
        "Phân bổ từ điểm tổng cuối cùng sau các lớp kiểm soát; không phải xác suất."
        if language == "vi"
        else "Allocated from the final guarded composite score; this is not a probability."
    )
    components = {
        key: {
            "score": allocated[key],
            "max_score": maximum,
            "status": (
                "unavailable" if key == "volume" and volume_usable is False
                else "available" if key in reasons else "estimated"
            ),
            "reason": reasons.get(key) or fallback_reason,
        }
        for key, maximum in SCORE_COMPONENT_MAXIMA.items()
    }
    band = score_band_metadata(score)
    next_threshold = next((value for value in (20, 40, 60, 80) if value > score), None)
    return {
        "total_score": score,
        "max_score": 100,
        "band": band.get("score_band"),
        "band_label": _band_label(score, language),
        "distance_to_next_band": next_threshold - score if next_threshold is not None else 0,
        "source": "model_reconciled" if has_model_components else "final_score_allocation",
        "components": components,
    }


def _allocate_integer_total(
    total: int,
    raw_scores: Mapping[str, float],
    maxima: Mapping[str, int],
) -> Dict[str, int]:
    weights = {key: max(0.0, float(raw_scores.get(key, 0.0))) for key in maxima}
    if sum(weights.values()) <= 0:
        weights = {key: float(value) for key, value in maxima.items()}
    weight_sum = sum(weights.values())
    exact = {
        key: min(float(maxima[key]), total * weights[key] / weight_sum)
        for key in maxima
    }
    allocated = {key: int(math.floor(value)) for key, value in exact.items()}
    remaining = total - sum(allocated.values())
    while remaining > 0:
        candidates = [key for key in maxima if allocated[key] < maxima[key]]
        if not candidates:
            break
        candidates.sort(key=lambda key: (exact[key] - allocated[key], maxima[key]), reverse=True)
        allocated[candidates[0]] += 1
        remaining -= 1
    return allocated


def _build_evidence_confidence(
    result: Any,
    *,
    overview: Optional[Mapping[str, Any]],
    market_data_quality: Optional[Mapping[str, Any]],
    daily_market_context: Optional[Mapping[str, Any]],
    language: str,
) -> Dict[str, Any]:
    overview_data = _mapping(overview)
    quality = _mapping(overview_data.get("data_quality"))
    block_scores = _mapping(quality.get("block_scores"))
    quote = _quality_score(block_scores.get("quote"))
    daily = _quality_score(block_scores.get("daily_bars"))
    technical = _quality_score(block_scores.get("technical"))
    news = _quality_score(block_scores.get("news"))
    fundamental = _quality_score(block_scores.get("fundamentals"))
    market_quality = _mapping(market_data_quality)

    ohlc = int(round((quote + daily) / 2))
    if market_quality.get("ohlc_usable") is False:
        ohlc = min(ohlc, 25)
    elif market_quality.get("ohlc_usable") is True:
        ohlc = max(ohlc, 85)

    if market_quality.get("volume_usable") is False:
        volume = 35
    elif market_quality.get("volume_usable") is True:
        volume = max(technical, 85)
    else:
        volume = technical

    market_context = _mapping(daily_market_context)
    market = 85 if str(market_context.get("summary") or "").strip() else 35
    factor_scores = {
        "ohlc": ohlc,
        "trend": technical,
        "volume": volume,
        "market": market,
        "news": news,
        "fundamental": fundamental,
    }
    score = int(round(sum(factor_scores[key] * weight for key, weight in CONFIDENCE_FACTOR_WEIGHTS.items()) / 100))
    confidence_text = str(getattr(result, "confidence_level", "") or "").strip().lower()
    if confidence_text in {"low", "thấp", "低", "낮음"}:
        score = min(score, 49)
    elif confidence_text in {"medium", "trung bình", "中", "보통"}:
        score = min(score, 79)

    factors = {
        key: {
            "score_pct": value,
            "status": _confidence_status(value),
            "reason": _factor_reason(key, value, language),
        }
        for key, value in factor_scores.items()
    }
    return {
        "score_pct": score,
        "level": "high" if score >= 80 else "medium" if score >= 60 else "low",
        "methodology": (
            "Độ tin cậy của dữ liệu đầu vào, không phải xác suất giá tăng."
            if language == "vi"
            else "Confidence in input evidence, not a probability of price appreciation."
        ),
        "factors": factors,
    }


def _build_scenario_outlook(
    result: Any,
    *,
    proposed: Dict[str, Any],
    score: int,
    language: str,
) -> Dict[str, Any]:
    proposed_items = proposed.get("scenarios")
    proposed_by_key: Dict[str, Dict[str, Any]] = {}
    if isinstance(proposed_items, list):
        for item in proposed_items:
            candidate = _mapping(item)
            key = str(candidate.get("key") or "").strip().lower()
            if key in _SCENARIO_KEYS and key not in proposed_by_key:
                proposed_by_key[key] = candidate

    if proposed_by_key:
        raw_probabilities = {
            key: max(0.0, _finite_number(proposed_by_key.get(key, {}).get("probability_pct")) or 0.0)
            for key in _SCENARIO_KEYS
        }
        probabilities = _allocate_integer_total(
            100,
            raw_probabilities,
            {key: 100 for key in _SCENARIO_KEYS},
        )
        source = str(proposed.get("probability_source") or "model_estimate")
    else:
        downside = max(10, min(75, 95 - score))
        upside = max(10, min(70, score - 20))
        sideways = max(10, 100 - downside - upside)
        probabilities = _allocate_integer_total(
            100,
            {"downside": downside, "sideways": sideways, "upside": upside},
            {key: 100 for key in _SCENARIO_KEYS},
        )
        source = "score_derived_estimate"

    dashboard = _mapping(getattr(result, "dashboard", None))
    data = _mapping(dashboard.get("data_perspective"))
    price = _mapping(data.get("price_position"))
    battle = _mapping(dashboard.get("battle_plan"))
    sniper = _mapping(battle.get("sniper_points"))
    targets = {
        "downside": _first_value(price.get("support_level"), sniper.get("stop_loss")),
        "sideways": price.get("current_price"),
        "upside": _first_value(price.get("resistance_level"), sniper.get("take_profit")),
    }
    defaults = _scenario_defaults(language)
    scenarios = []
    for key in _SCENARIO_KEYS:
        item = proposed_by_key.get(key, {})
        default = defaults[key]
        scenarios.append({
            "key": key,
            "label": str(item.get("label") or default["label"]),
            "probability_pct": probabilities[key],
            "condition": str(item.get("condition") or default["condition"]),
            "target_price": _first_value(item.get("target_price"), targets[key]),
            "invalidation": str(item.get("invalidation") or default["invalidation"]),
            "recommended_action": str(item.get("recommended_action") or default["recommended_action"]),
            "rationale": str(item.get("rationale") or default["rationale"]),
        })
    return {
        "horizon": str(proposed.get("horizon") or ("1-5 phiên" if language == "vi" else "1-5 sessions")),
        "probability_source": source,
        "calibration_status": str(proposed.get("calibration_status") or "uncalibrated"),
        "scenarios": scenarios,
    }


def _build_trade_expectancy(result: Any, outlook: Dict[str, Any], *, language: str) -> Dict[str, Any]:
    dashboard = _mapping(getattr(result, "dashboard", None))
    battle = _mapping(dashboard.get("battle_plan"))
    validation = _mapping(battle.get("trading_plan_validation"))
    ratio = _finite_number(validation.get("risk_reward_ratio"))
    valid = validation.get("quality_status") in {"valid", "auto_fixed"} and ratio is not None and ratio > 0
    if not valid:
        return {
            "status": "unavailable",
            "risk_reward_ratio": None,
            "win_probability_pct": None,
            "expected_value_r": None,
            "probability_source": None,
            "calibration_status": "unavailable",
            "sample_size": None,
            "methodology": (
                "Không đủ kế hoạch Entry/SL/TP hợp lệ để tính kỳ vọng giao dịch."
                if language == "vi"
                else "A valid Entry/SL/TP plan is required to calculate trade expectancy."
            ),
        }
    upside = next(
        (item for item in outlook.get("scenarios", []) if item.get("key") == "upside"),
        None,
    )
    probability = _bounded_int(_mapping(upside).get("probability_pct"), 0, 100, default=0)
    p_win = probability / 100.0
    ev = round(p_win * float(ratio) - (1.0 - p_win), 2)
    return {
        "status": "available",
        "risk_reward_ratio": round(float(ratio), 2),
        "win_probability_pct": probability,
        "expected_value_r": ev,
        "probability_source": "scenario_estimate",
        "calibration_status": "uncalibrated",
        "sample_size": None,
        "methodology": (
            "EV trước chi phí = P(thắng) × Reward/Risk − P(thua) × 1R; xác suất hiện là ước tính kịch bản, chưa hiệu chỉnh bằng backtest."
            if language == "vi"
            else "Before-cost EV = P(win) × Reward/Risk − P(loss) × 1R; probability is an uncalibrated scenario estimate."
        ),
    }


def _apply_expectancy_entry_gate(result: Any, expectancy: Mapping[str, Any], *, language: str) -> None:
    """Prevent a negative-expectancy setup from being rendered as an active buy.

    Price levels remain visible as an observation zone, but no position size or
    buy instruction may be inferred until a new setup produces non-negative EV
    and the existing confirmation conditions are satisfied.
    """

    expected_value = _finite_number(expectancy.get("expected_value_r"))
    if expected_value is None or expected_value >= 0:
        return
    dashboard = _mapping(getattr(result, "dashboard", None))
    battle = _mapping(dashboard.get("battle_plan"))
    if not battle or not _mapping(battle.get("sniper_points")):
        return
    battle["entry_status"] = "observation_only"
    battle["entry_status_message"] = (
        "Vùng quan sát tiềm năng; trạng thái lệnh mua: chưa kích hoạt vì EV hiện tại âm."
        if language == "vi"
        else "Potential observation zone; buy order is not activated because current EV is negative."
    )
    dashboard["battle_plan"] = battle
    result.dashboard = dashboard


def _scenario_defaults(language: str) -> Dict[str, Dict[str, str]]:
    if language == "vi":
        return {
            "downside": {
                "label": "Tiếp tục giảm",
                "condition": "Giá mất vùng hỗ trợ gần nhất hoặc áp lực bán gia tăng.",
                "invalidation": "Giá lấy lại kháng cự với thanh khoản được xác nhận.",
                "recommended_action": "Giảm tỷ trọng và tuân thủ điểm vô hiệu.",
                "rationale": "Kịch bản rủi ro dựa trên điểm tổng và cấu trúc xu hướng hiện tại.",
            },
            "sideways": {
                "label": "Đi ngang",
                "condition": "Giá giữ hỗ trợ nhưng chưa vượt được kháng cự.",
                "invalidation": "Giá phá vỡ rõ ràng một trong hai biên.",
                "recommended_action": "Theo dõi, không tăng tỷ trọng sớm.",
                "rationale": "Cung cầu chưa tạo được xác nhận theo một hướng.",
            },
            "upside": {
                "label": "Hồi kỹ thuật",
                "condition": "Giá vượt kháng cự và thanh khoản được xác nhận.",
                "invalidation": "Nhịp hồi thất bại và giá quay lại dưới hỗ trợ.",
                "recommended_action": "Chỉ đánh giá điểm vào sau tín hiệu xác nhận.",
                "rationale": "Kịch bản tích cực cần thêm xác nhận, không suy ra chỉ từ R:R.",
            },
        }
    return {
        "downside": {"label": "Further downside", "condition": "Price loses nearby support or selling pressure rises.", "invalidation": "Price reclaims resistance on confirmed volume.", "recommended_action": "Reduce exposure and respect invalidation.", "rationale": "Risk case derived from the final score and trend structure."},
        "sideways": {"label": "Sideways", "condition": "Price holds support but cannot clear resistance.", "invalidation": "Price breaks either range boundary decisively.", "recommended_action": "Watch without adding exposure early.", "rationale": "Supply and demand lack directional confirmation."},
        "upside": {"label": "Technical rebound", "condition": "Price clears resistance with confirmed volume.", "invalidation": "The rebound fails and price returns below support.", "recommended_action": "Reassess entry only after confirmation.", "rationale": "The positive case needs confirmation and is not implied by R:R alone."},
    }


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bounded_int(value: Any, minimum: int, maximum: int, *, default: int) -> int:
    number = _finite_number(value)
    if number is None:
        return default
    return max(minimum, min(maximum, int(round(number))))


def _quality_score(value: Any) -> int:
    return _bounded_int(value, 0, 100, default=35)


def _confidence_status(score: int) -> str:
    if score >= 80:
        return "available"
    if score >= 55:
        return "limited"
    return "missing"


def _factor_reason(key: str, score: int, language: str) -> str:
    label_vi = {
        "ohlc": "OHLC",
        "trend": "xu hướng",
        "volume": "khối lượng",
        "market": "thị trường",
        "news": "tin tức",
        "fundamental": "cơ bản",
    }[key]
    status_vi = "đầy đủ" if score >= 80 else "hạn chế" if score >= 55 else "thiếu hoặc chưa xác nhận"
    if language == "vi":
        return f"Dữ liệu {label_vi} {status_vi}."
    return f"{key.replace('_', ' ').title()} evidence is {_confidence_status(score)}."


def _band_label(score: int, language: str) -> str:
    if score >= 80:
        return "Mua mạnh" if language == "vi" else "Strong buy"
    if score >= 60:
        return "Mua" if language == "vi" else "Buy"
    if score >= 40:
        return "Theo dõi" if language == "vi" else "Watch"
    if score >= 20:
        return "Giảm tỷ trọng" if language == "vi" else "Reduce"
    return "Bán" if language == "vi" else "Sell"


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "N/A"):
            return value
    return None
