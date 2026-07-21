# -*- coding: utf-8 -*-
"""
===================================
Report Engine - Report renderer tests
===================================

Tests for Jinja2 report rendering and fallback behavior.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.analyzer import AnalysisResult
from src.services.report_renderer import render


def _make_result(
    code: str = "600519",
    name: str = "贵州茅台",
    sentiment_score: int = 72,
    operation_advice: str = "持有",
    analysis_summary: str = "稳健",
    decision_type: str = "hold",
    dashboard: dict = None,
    report_language: str = "zh",
    model_used: str = None,
) -> AnalysisResult:
    if dashboard is None:
        dashboard = {
            "core_conclusion": {"one_sentence": "持有观望"},
            "intelligence": {"risk_alerts": []},
            "battle_plan": {"sniper_points": {"stop_loss": "110"}},
        }
    return AnalysisResult(
        code=code,
        name=name,
        trend_prediction="看多",
        sentiment_score=sentiment_score,
        operation_advice=operation_advice,
        analysis_summary=analysis_summary,
        decision_type=decision_type,
        dashboard=dashboard,
        report_language=report_language,
        model_used=model_used,
    )


def _make_renderer_config(show_llm_model: bool = True) -> MagicMock:
    config = MagicMock()
    config.report_templates_dir = "templates"
    config.report_language = "zh"
    config.report_show_llm_model = show_llm_model
    return config


def _with_decision_signal_summary(result: AnalysisResult) -> AnalysisResult:
    result.decision_signal_summary = {
        "action": "sell",
        "action_label": "卖出",
        "horizon": "1d",
        "reason": "技术面走弱",
    }
    return result


class TestReportRenderer(unittest.TestCase):
    """Report renderer tests."""

    def test_render_markdown_summary_only(self) -> None:
        """Markdown platform renders with summary_only."""
        r = _make_result()
        out = render("markdown", [r], summary_only=True)
        self.assertIsNotNone(out)
        self.assertIn("决策仪表盘", out)
        self.assertIn("贵州茅台", out)
        self.assertIn("持有", out)

    def test_vietnamese_market_forces_vietnamese_dashboard_labels(self) -> None:
        """VN tickers render markdown dashboard chrome in Vietnamese."""
        r = _make_result(
            code="FPT.VN",
            name="FPT",
            operation_advice="Mua",
            analysis_summary="Ưu tiên theo dõi sau giờ nghỉ trưa",
            dashboard={
                "core_conclusion": {"one_sentence": "Theo dõi điểm mở cửa lại lúc 13:00"},
                "intelligence": {"latest_news": "Tin mới từ Cafef"},
                "battle_plan": {
                    "sniper_points": {"stop_loss": "92"},
                    "action_checklist": ["Kiểm tra thanh khoản sau 13:00"],
                },
            },
            report_language="en",
        )

        out = render("markdown", [r], summary_only=False, extra_context={"report_language": "en"})

        self.assertIsNotNone(out)
        self.assertIn("Bảng điều khiển quyết định", out)
        self.assertIn("Tóm tắt", out)
        self.assertIn("Danh sách kiểm tra", out)
        self.assertNotIn("Decision Dashboard", out)

    def test_vietnamese_report_localizes_status_and_decision_signal_chrome(self) -> None:
        r = _with_decision_signal_summary(_make_result(
            code="VNM.VN",
            name="Vinamilk",
            operation_advice="Hold and watch",
            report_language="vi",
        ))
        r.market_phase_summary = {"market": "vn", "phase": "intraday"}

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("Trạng thái thị trường: Việt Nam · Trong phiên", out)
        self.assertIn("Tín hiệu quyết định AI", out)
        self.assertIn("Hành động: Bán", out)
        self.assertNotIn("AI 决策信号", out)
        self.assertNotIn("Hold and watch", out)

    def test_render_markdown_full(self) -> None:
        """Markdown platform renders full report."""
        r = _make_result()
        out = render("markdown", [r], summary_only=False)
        self.assertIsNotNone(out)
        self.assertIn("核心结论", out)
        self.assertIn("作战计划", out)
        self.assertNotIn("盘中决策护栏", out)

    def test_render_markdown_keeps_decision_signal_out_of_summary(self) -> None:
        """Markdown summary stays compact while full details keep DecisionSignal excerpts."""
        r = _with_decision_signal_summary(_make_result())

        summary_out = render("markdown", [r], summary_only=True)
        self.assertIsNotNone(summary_out)
        self.assertNotIn("AI 决策信号", summary_out)

        full_out = render("markdown", [r], summary_only=False)
        self.assertIsNotNone(full_out)
        summary_section, detail_section = full_out.split("---", 1)
        self.assertNotIn("AI 决策信号", summary_section)
        self.assertIn("AI 决策信号", detail_section)
        self.assertIn("动作: 卖出", detail_section)
        self.assertIn("周期: 1d", detail_section)
        self.assertIn("理由: 技术面走弱", detail_section)

    def test_render_markdown_phase_decision_section(self) -> None:
        """Markdown renders phase_decision when present."""
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "等待确认"},
                "intelligence": {"risk_alerts": []},
                "phase_decision": {
                    "action_window": "盘中跟踪",
                    "immediate_action": "等待确认",
                    "watch_conditions": ["放量突破"],
                    "next_check_time": "14:30",
                    "confidence_reason": "数据质量可用",
                    "data_limitations": ["quote: stale"],
                },
                "battle_plan": {"sniper_points": {"stop_loss": "110"}},
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("盘中决策护栏", out)
        self.assertIn("盘中跟踪", out)
        self.assertIn("放量突破", out)
        self.assertIn("quote: stale", out)

    def test_vietnamese_markdown_renders_sector_health_decision_scenarios_and_closing_summary(self) -> None:
        summary = (
            "Xu hướng ngắn hạn trung tính và dòng tiền chưa xác nhận. "
            "Ưu tiên chờ tín hiệu tại các mốc giá quyết định."
        )
        r = _make_result(
            code="MBB.VN",
            name="MBB",
            operation_advice="Theo dõi",
            analysis_summary=summary,
            report_language="vi",
            dashboard={
                "core_conclusion": {"one_sentence": "Chờ xác nhận tại vùng giá quyết định."},
                "data_perspective": {
                    "sector_health": {
                        "score": 68,
                        "label": "Tích cực",
                        "peer_symbols": ["VCB.VN", "BID.VN"],
                        "rationale": "Hai cổ phiếu dẫn dắt cùng ngành duy trì xu hướng tốt.",
                        "data_status": "available",
                    },
                    "chip_structure": {
                        "profit_ratio": "Không có dữ liệu",
                        "avg_cost": "Không có dữ liệu",
                        "concentration": "Không có dữ liệu",
                        "chip_health": "Không có dữ liệu",
                    },
                },
                "intelligence": {"risk_alerts": []},
                "phase_decision": {
                    "action_window": "Theo dõi trong phiên",
                    "immediate_action": "Chờ xác nhận",
                    "watch_conditions": ["Giữ trên 23.800"],
                    "decision_scenarios": [
                        {
                            "condition": "Giá vượt 24.300 với thanh khoản tăng",
                            "action": "Mua thăm dò",
                            "invalidation": "Quay xuống dưới 24.300",
                        },
                        {
                            "condition": "Giá thủng 23.800",
                            "action": "Giảm tỷ trọng",
                            "invalidation": "Lấy lại 23.800 cuối phiên",
                        },
                    ],
                    "next_check_time": "14:30",
                    "confidence_reason": "Dữ liệu đủ dùng.",
                    "data_limitations": [],
                },
                "battle_plan": {"sniper_points": {"stop_loss": "23.800"}},
            },
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("Sức khỏe nhóm ngành", out)
        self.assertIn("68/100", out)
        self.assertIn("VCB.VN, BID.VN", out)
        self.assertIn("Kịch bản quyết định", out)
        self.assertIn("Giá vượt 24.300 với thanh khoản tăng", out)
        self.assertIn("Tổng hợp cuối báo cáo", out)
        self.assertIn(summary, out)
        self.assertNotIn("Cơ cấu nắm giữ", out)

    def test_render_markdown_skips_context_only_phase_decision_shape(self) -> None:
        """Markdown skips mechanically shaped phase_decision without actionable content."""
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望"},
                "intelligence": {"risk_alerts": []},
                "phase_decision": {
                    "phase_context": {"phase": "intraday", "market": "cn"},
                    "action_window": None,
                    "immediate_action": None,
                    "watch_conditions": [],
                    "next_check_time": None,
                    "confidence_reason": None,
                    "data_limitations": [],
                },
                "battle_plan": {"sniper_points": {"stop_loss": "110"}},
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertNotIn("盘中决策护栏", out)

    def test_render_wechat(self) -> None:
        """Wechat platform renders."""
        r = _make_result()
        out = render("wechat", [r])
        self.assertIsNotNone(out)
        self.assertIn("贵州茅台", out)

    def test_render_wechat_keeps_decision_signal_out_of_summary(self) -> None:
        """Wechat summary-only stays compact while full details keep DecisionSignal excerpts."""
        r = _with_decision_signal_summary(_make_result())

        summary_out = render("wechat", [r], summary_only=True)
        self.assertIsNotNone(summary_out)
        self.assertNotIn("AI 决策信号", summary_out)

        full_out = render("wechat", [r], summary_only=False)
        self.assertIsNotNone(full_out)
        self.assertIn("AI 决策信号", full_out)
        self.assertIn("动作: 卖出", full_out)
        self.assertIn("周期: 1d", full_out)
        self.assertIn("理由: 技术面走弱", full_out)

    def test_render_brief(self) -> None:
        """Brief platform renders 3-5 sentence summary."""
        r = _make_result()
        out = render("brief", [r])
        self.assertIsNotNone(out)
        self.assertIn("决策简报", out)
        self.assertIn("贵州茅台", out)

    def test_render_brief_omits_decision_signal_excerpt(self) -> None:
        r = _with_decision_signal_summary(_make_result())

        out = render("brief", [r])

        self.assertIsNotNone(out)
        self.assertNotIn("AI 决策信号", out)

    def test_render_brief_respects_model_visibility_toggle(self) -> None:
        r = _make_result(model_used="gemini/gemini-2.5-flash")

        with patch("src.services.report_renderer.get_config", return_value=_make_renderer_config(True)):
            visible = render("brief", [r])
        with patch("src.services.report_renderer.get_config", return_value=_make_renderer_config(False)):
            hidden = render("brief", [r])

        self.assertIsNotNone(visible)
        self.assertIsNotNone(hidden)
        self.assertIn("分析模型: gemini/gemini-2.5-flash", visible)
        self.assertNotIn("分析模型", hidden)
        self.assertNotIn("gemini/gemini-2.5-flash", hidden)

    def test_render_templates_show_compact_market_status_only(self) -> None:
        r = _make_result()
        r.market_phase_summary = {
            "phase": "intraday",
            "market": "cn",
            "trigger_source": "api",
            "is_partial_bar": True,
        }
        r.analysis_context_pack_overview = {
            "data_quality": {
                "level": "limited",
                "limitations": ["quote: stale", "news: missing", "technical: fallback"],
            }
        }
        r.raw_response = "raw context pack should not appear"

        out = render("brief", [r])

        self.assertIsNotNone(out)
        self.assertIn("市场状态：A股 · 盘中", out)
        self.assertNotIn("阶段：intraday", out)
        self.assertNotIn("盘中数据提示", out)
        self.assertNotIn("数据质量: limited", out)
        self.assertNotIn("限制: quote: stale", out)
        self.assertNotIn("限制: news: missing", out)
        self.assertNotIn("technical: fallback", out)
        self.assertNotIn("raw context pack", out)

    def test_render_templates_skip_phase_pack_excerpt_when_summary_missing(self) -> None:
        r = _make_result()

        out = render("brief", [r])

        self.assertIsNotNone(out)
        self.assertNotIn("摘要来源", out)
        self.assertNotIn("evaluator snapshot", out)

    def test_render_market_status_preserves_input_order(self) -> None:
        cn = _make_result(
            code="600519",
            name="贵州茅台",
            sentiment_score=60,
        )
        cn.market_phase_summary = {"market": "cn", "phase": "postmarket"}
        us = _make_result(
            code="AAPL",
            name="Apple",
            sentiment_score=90,
        )
        us.market_phase_summary = {"market": "us", "phase": "premarket"}

        out = render("markdown", [cn, us], summary_only=True)

        self.assertIsNotNone(out)
        self.assertIn("市场状态：A股 · 盘后", out)
        self.assertNotIn("市场状态：美股 · 盘前", out)

    def test_render_markdown_footer_uses_consistent_separator(self) -> None:
        r = _make_result(model_used="gemini/gemini-2.5-flash")

        with patch("src.services.report_renderer.get_config", return_value=_make_renderer_config(True)):
            out = render("markdown", [r], summary_only=True)

        self.assertIsNotNone(out)
        self.assertIn("报告生成时间：", out)
        self.assertIn("分析模型：gemini/gemini-2.5-flash", out)
        self.assertNotIn("分析模型: gemini/gemini-2.5-flash", out)

    def test_render_markdown_in_english(self) -> None:
        """Markdown renderer switches headings and summary labels for English reports."""
        r = _make_result(
            name="Kweichow Moutai",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
        )
        out = render("markdown", [r], summary_only=True)
        self.assertIsNotNone(out)
        self.assertIn("Decision Dashboard", out)
        self.assertIn("Summary", out)
        self.assertIn("Buy", out)

    def test_render_markdown_market_snapshot_uses_template_context(self) -> None:
        """Market snapshot macro should render localized labels with template context."""
        r = _make_result(
            code="AAPL",
            name="Apple",
            operation_advice="Buy",
            report_language="en",
        )
        r.market_snapshot = {
            "close": "180.10",
            "prev_close": "178.25",
            "open": "179.00",
            "high": "181.20",
            "low": "177.80",
            "pct_chg": "+1.04%",
            "change_amount": "1.85",
            "amplitude": "1.91%",
            "volume": "1200000",
            "amount": "215000000",
            "price": "180.35",
            "volume_ratio": "1.2",
            "turnover_rate": "0.8%",
            "source": "polygon",
        }

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("Market Snapshot", out)
        self.assertIn("Volume Ratio", out)

    def test_render_markdown_collapses_unavailable_chip_structure(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望"},
                "data_perspective": {
                    "chip_structure": {
                        "profit_ratio": "数据缺失，无法判断",
                        "avg_cost": "数据缺失，无法判断",
                        "concentration": "数据缺失，无法判断",
                        "chip_health": "数据缺失，无法判断",
                    }
                },
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("**筹码**: 筹码分布未启用或数据源暂不可用，未纳入筹码判断。", out)
        self.assertEqual(out.count("数据缺失，无法判断"), 0)

    def test_render_unknown_platform_returns_none(self) -> None:
        """Unknown platform returns None (caller fallback)."""
        r = _make_result()
        out = render("unknown_platform", [r])
        self.assertIsNone(out)

    def test_render_empty_results_returns_content(self) -> None:
        """Empty results still produces header."""
        out = render("markdown", [], summary_only=True)
        self.assertIsNotNone(out)
        self.assertIn("0", out)
