# -*- coding: utf-8 -*-
"""
===================================
Report Engine - Jinja2 Report Renderer
===================================

Renders reports from Jinja2 templates. Falls back to caller's logic on template
missing or render error. Template path is relative to project root.
Any expensive data preparation should be injected by the caller via extra_context.
"""

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.analyzer import AnalysisResult, normalize_report_output_data
from src.config import get_config
from src.market_phase_summary import format_public_market_status_line, format_public_phase_pack_excerpt
from src.services.decision_signal_summary import format_decision_signal_excerpt
from src.report_language import (
    get_localized_stock_name,
    get_report_labels,
    get_signal_level,
    get_chip_unavailable_reason,
    is_chip_structure_unavailable,
    localize_chip_health,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.services.market_symbol_utils import is_vn_market_symbol
from src.utils.data_processing import (
    normalize_model_used,
    signal_attribution_has_content,
    signal_attribution_weight_items,
)
from src.utils.sniper_points import parse_sniper_value
from src.utils.vietnamese_numbers import format_vnd_amount

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    """Escape markdown special chars (*ST etc)."""
    if not text:
        return ""
    return text.replace("*", "\\*").replace("_", "\\_")


def _clean_sniper_value(val: Any, stock_code: str = "") -> str:
    """Format sniper point value for display (strip label prefixes)."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        return (
            format_vnd_amount(val)
            if is_vn_market_symbol(stock_code)
            else str(val)
        )
    s = str(val).strip() if val else ""
    if not s or s == "N/A":
        return s or "N/A"
    prefixes = [
        "理想买入点：", "次优买入点：", "止损位：", "目标位：",
        "理想买入点:", "次优买入点:", "止损位:", "目标位:",
        "Ideal Entry:", "Secondary Entry:", "Stop Loss:", "Target:",
    ]
    for prefix in prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    if is_vn_market_symbol(stock_code):
        parsed = parse_sniper_value(s)
        if parsed is not None:
            return format_vnd_amount(parsed)
    return s


def _format_ev_r(value: Any) -> str:
    """Format a finite expectancy value in R units with an explicit sign."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(number):
        return "N/A"
    rendered = f"{number:+.2f}".rstrip("0").rstrip(".")
    return f"{rendered}R"


def _localize_system_text(value: Any, language: str) -> Any:
    """Translate stable system tokens that can appear inside LLM list fields."""
    if language != "vi" or not isinstance(value, str):
        return value
    return {
        "technical: partial": "Kỹ thuật: một phần",
        "technical: fallback": "Kỹ thuật: dự phòng",
        "N/A": "Không có dữ liệu",
    }.get(value.strip(), value)


def _resolve_templates_dir() -> Path:
    """Resolve template directory relative to project root."""
    config = get_config()
    base = Path(__file__).resolve().parent.parent.parent
    templates_dir = Path(config.report_templates_dir)
    if not templates_dir.is_absolute():
        return base / templates_dir
    return templates_dir


def render(
    platform: str,
    results: List[AnalysisResult],
    report_date: Optional[str] = None,
    summary_only: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Render report using Jinja2 template.

    Args:
        platform: One of: markdown, wechat, brief
        results: List of AnalysisResult
        report_date: Report date string (default: today)
        summary_only: Whether to output summary only
        extra_context: Additional template context

    Returns:
        Rendered string, or None on error (caller should fallback).
    """
    from datetime import datetime

    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        logger.warning("jinja2 not installed, report renderer disabled")
        return None

    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    templates_dir = _resolve_templates_dir()
    template_name = f"report_{platform}.j2"
    template_path = templates_dir / template_name
    if not template_path.exists():
        logger.debug("Report template not found: %s", template_path)
        return None

    report_language = (
        "vi"
        if any(is_vn_market_symbol(getattr(result, "code", "")) for result in results)
        else normalize_report_language(
            (extra_context or {}).get("report_language")
            or next(
                (getattr(result, "report_language", None) for result in results if getattr(result, "report_language", None)),
                None,
            )
            or getattr(get_config(), "report_language", "zh")
        )
    )
    labels = get_report_labels(report_language)

    # Older persisted reports and direct renderer callers may still contain
    # raw floats or structured news arrays. Normalize at the final boundary as
    # well as in the pipeline so every delivery channel stays scannable.
    for result in results:
        normalize_report_output_data(result)

    # Build template context with pre-computed signal levels (sorted by score)
    sorted_results = sorted(results, key=lambda x: x.sentiment_score, reverse=True)
    sorted_enriched = []
    for r in sorted_results:
        st, se, _ = get_signal_level(r.operation_advice, r.sentiment_score, report_language)
        rn = get_localized_stock_name(r.name, r.code, report_language)
        sorted_enriched.append({
            "result": r,
            "signal_text": st,
            "signal_emoji": se,
            "stock_name": _escape_md(rn),
            "localized_operation_advice": localize_operation_advice(r.operation_advice, report_language),
            "localized_trend_prediction": localize_trend_prediction(r.trend_prediction, report_language),
        })

    def final_action(result: AnalysisResult) -> str:
        action = str(getattr(result, "action", "") or "").strip().lower()
        if action:
            return action
        return str(getattr(result, "decision_type", "") or "hold").strip().lower()

    buy_count = sum(1 for r in results if final_action(r) in ("buy", "add"))
    reduce_count = sum(1 for r in results if final_action(r) == "reduce")
    sell_count = sum(1 for r in results if final_action(r) == "sell")
    hold_count = sum(1 for r in results if final_action(r) in ("hold", "watch", "avoid", "alert"))
    show_llm_model = bool(getattr(get_config(), "report_show_llm_model", True))
    models_used: List[str] = []
    if show_llm_model:
        for result in results:
            model = normalize_model_used(getattr(result, "model_used", None))
            if model:
                models_used.append(model)
        models_used = list(dict.fromkeys(models_used))

    report_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def failed_checks(checklist: List[str]) -> List[str]:
        return [c for c in (checklist or []) if c.startswith("❌") or c.startswith("⚠️")]

    def phase_pack_excerpt(result: AnalysisResult) -> str:
        return format_public_phase_pack_excerpt(
            getattr(result, "market_phase_summary", None),
            getattr(result, "analysis_context_pack_overview", None),
            source=getattr(result, "analysis_visibility_source", None) or "evaluator_snapshot",
            report_language=report_language,
        )

    def decision_signal_excerpt(result: AnalysisResult) -> str:
        return format_decision_signal_excerpt(
            getattr(result, "decision_signal_summary", None),
            report_language=report_language,
        )

    def market_status_line() -> str:
        for source_results in (results or [], sorted_results):
            for result in source_results:
                line = format_public_market_status_line(
                    getattr(result, "market_phase_summary", None),
                    report_language=report_language,
                )
                if line:
                    return line
        return ""

    context: Dict[str, Any] = {
        "report_date": report_date,
        "report_timestamp": report_timestamp,
        "results": sorted_results,
        "enriched": sorted_enriched,  # Sorted by sentiment_score desc
        "summary_only": summary_only,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "reduce_count": reduce_count,
        "hold_count": hold_count,
        "labels": labels,
        "report_language": report_language,
        "models_used": models_used,
        "show_llm_model": show_llm_model,
        "market_status_line": market_status_line(),
        "escape_md": _escape_md,
        "clean_sniper": _clean_sniper_value,
        "format_ev_r": _format_ev_r,
        "failed_checks": failed_checks,
        "phase_pack_excerpt": phase_pack_excerpt,
        "decision_signal_excerpt": decision_signal_excerpt,
        "history_by_code": {},
        "get_chip_unavailable_reason": get_chip_unavailable_reason,
        "is_chip_structure_unavailable": is_chip_structure_unavailable,
        "localize_operation_advice": localize_operation_advice,
        "localize_trend_prediction": localize_trend_prediction,
        "localize_chip_health": localize_chip_health,
        "localize_system_text": lambda value: _localize_system_text(value, report_language),
        "signal_attribution_has_content": signal_attribution_has_content,
        "signal_attribution_weight_items": signal_attribution_weight_items,
    }
    if extra_context:
        safe_extra_context = dict(extra_context)
        safe_extra_context.pop("labels", None)
        safe_extra_context.pop("report_language", None)
        context.update(safe_extra_context)

    try:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(default=False),
        )
        template = env.get_template(template_name)
        return template.render(**context)
    except Exception as e:
        logger.warning("Report render failed for %s: %s", template_name, e)
        return None
