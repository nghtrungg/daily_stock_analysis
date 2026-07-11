# -*- coding: utf-8 -*-
"""Tests for Korean (ko) output-language directives in analysis prompts (#1614)."""

import unittest

from src.agent.agents.decision_agent import DecisionAgent
from src.agent.agents.intel_agent import IntelAgent
from src.agent.agents.risk_agent import RiskAgent
from src.agent.agents.technical_agent import TechnicalAgent
from src.agent.executor import _build_language_section
from src.agent.protocols import AgentContext
from src.analysis_context_pack_prompt import normalize_analysis_context_pack_language
from src.market_phase_prompt import format_market_phase_prompt_section


def _phase_ctx():
    return {
        "market": "us",
        "phase": "premarket",
        "market_local_time": "2026-06-29T08:00:00-04:00",
        "effective_daily_bar_date": "2026-06-27",
        "minutes_to_open": 90,
        "warnings": [],
    }


class DecisionAgentLanguageDirectiveTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DecisionAgent(tool_registry=None, llm_adapter=None)

    def _system_prompt(self, language: str, *, chat: bool = False) -> str:
        meta = {"report_language": language}
        if chat:
            meta["response_mode"] = "chat"
        ctx = AgentContext(stock_code="005930.KS", stock_name="삼성전자", meta=meta)
        return self.agent.system_prompt(ctx)

    def test_korean_dashboard_directive(self) -> None:
        prompt = self._system_prompt("ko")
        self.assertIn("Write all human-readable JSON values in Korean (한국어).", prompt)
        self.assertIn("`decision_type` must remain `buy|hold|sell`.", prompt)

    def test_korean_chat_directive(self) -> None:
        prompt = self._system_prompt("ko", chat=True)
        self.assertIn("항상 한국어로 답변하세요.", prompt)

    def test_english_directive_unchanged(self) -> None:
        prompt = self._system_prompt("en")
        self.assertIn("Write all human-readable JSON values in English.", prompt)

    def test_chinese_directive_unchanged(self) -> None:
        prompt = self._system_prompt("zh")
        self.assertIn("所有面向用户的人类可读文本值必须使用中文。", prompt)


class VietnamAgentLanguageDirectiveTestCase(unittest.TestCase):
    def test_decision_agent_vietnamese_market_marker_overrides_report_language(self) -> None:
        agent = DecisionAgent(tool_registry=None, llm_adapter=None)
        ctx = AgentContext(stock_code="FPT.VN", stock_name="FPT", meta={"report_language": "en"})

        prompt = agent.system_prompt(ctx)

        self.assertIn("`.VN` market marker", prompt)
        self.assertIn("100% of all human-readable JSON values in Vietnamese", prompt)
        self.assertIn("technical analysis text, risk evaluations, positive catalysts", prompt)

    def test_decision_agent_vietnamese_chat_directive_overrides_report_language(self) -> None:
        agent = DecisionAgent(tool_registry=None, llm_adapter=None)
        ctx = AgentContext(
            stock_code="VNM.VN",
            stock_name="Vinamilk",
            meta={"report_language": "zh", "response_mode": "chat"},
        )

        prompt = agent.system_prompt(ctx)

        self.assertIn("Always answer in Vietnamese.", prompt)

    def test_stage_agents_receive_vietnamese_output_rule(self) -> None:
        ctx = AgentContext(stock_code="FPT.VN", stock_name="FPT", meta={"report_language": "en"})

        self.assertIn(
            "human-readable technical analysis value in Vietnamese",
            TechnicalAgent(tool_registry=None, llm_adapter=None).system_prompt(ctx),
        )
        self.assertIn(
            "human-readable risk evaluation value in Vietnamese",
            RiskAgent(tool_registry=None, llm_adapter=None).system_prompt(ctx),
        )
        self.assertIn(
            "risk alert, and positive catalyst in Vietnamese",
            IntelAgent(tool_registry=None, llm_adapter=None).system_prompt(ctx),
        )

    def test_executor_language_section_overrides_vietnamese_market(self) -> None:
        section = _build_language_section("en", stock_code="HPG.VN")
        self.assertIn("`.VN` market marker", section)
        self.assertIn("100% in Vietnamese", section)

        chat_section = _build_language_section("zh", chat_mode=True, stock_code="HPG.VN")
        self.assertIn("reply in Vietnamese", chat_section)


class StructuralLanguageRoutingTestCase(unittest.TestCase):
    def test_context_pack_korean_reuses_english_scaffolding(self) -> None:
        self.assertEqual(normalize_analysis_context_pack_language("ko"), "en")
        self.assertEqual(normalize_analysis_context_pack_language("en"), "en")
        self.assertEqual(normalize_analysis_context_pack_language("zh"), "zh")

    def test_market_phase_korean_matches_english_structure(self) -> None:
        ko_section = format_market_phase_prompt_section(_phase_ctx(), report_language="ko")
        en_section = format_market_phase_prompt_section(_phase_ctx(), report_language="en")
        self.assertEqual(ko_section, en_section)
        self.assertIn("## Market Phase Context", ko_section)

    def test_vietnam_lunch_break_phase_adds_midday_reopening_rule(self) -> None:
        section = format_market_phase_prompt_section(
            {
                "market": "vn",
                "phase": "lunch_break",
                "market_local_time": "2026-07-09T11:45:00+07:00",
                "is_partial_bar": True,
                "warnings": [],
            },
            report_language="vi",
        )

        self.assertIn("This is a midday analysis of the morning session", section)
        self.assertIn("Action Checklist for the 13:00 reopening", section)


if __name__ == "__main__":
    unittest.main()
