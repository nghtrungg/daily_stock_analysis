# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 分析历史存储单元测试
===================================

职责：
1. 验证分析历史保存逻辑
2. 验证上下文快照保存开关
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Keep this test runnable when optional LLM runtime deps are not installed.
try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.config import Config
from src.storage import (
    DatabaseManager,
    AnalysisHistory,
    BacktestResult,
    DecisionSignalFeedbackRecord,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
)
from src.analyzer import AnalysisResult
from src.daily_market_context_guardrail import apply_daily_market_context_guardrail
from src.services.history_service import HistoryService


def _analysis_context_pack_overview() -> dict:
    return {
        "pack_version": "1.0",
        "created_at": "2026-04-10T08:30:00+00:00",
        "subject": {
            "code": "600519",
            "stock_name": "贵州茅台",
            "market": "cn",
        },
        "blocks": [
            {
                "key": "quote",
                "label": "行情",
                "status": "available",
                "source": "mock",
                "warnings": [],
                "missing_reasons": [],
            }
        ],
        "counts": {
            "available": 1,
            "missing": 0,
            "not_supported": 0,
            "fallback": 0,
            "stale": 0,
            "estimated": 0,
            "partial": 0,
            "fetch_failed": 0,
        },
        "data_quality": {
            "overall_score": 100,
            "level": "good",
            "block_scores": {
                "quote": 100,
                "daily_bars": 100,
                "technical": 100,
                "news": 100,
                "fundamentals": 100,
                "chip": 100,
            },
            "limitations": [],
        },
        "warnings": [],
        "metadata": {
            "trigger_source": "api",
            "news_result_count": 2,
        },
    }


def _market_phase_summary() -> dict:
    return {
        "market": "cn",
        "phase": "intraday",
        "market_local_time": "2026-03-27T10:00:00+08:00",
        "session_date": "2026-03-27",
        "effective_daily_bar_date": "2026-03-26",
        "is_trading_day": True,
        "is_market_open_now": True,
        "is_partial_bar": True,
        "minutes_to_open": None,
        "minutes_to_close": 300,
        "trigger_source": "api",
        "analysis_intent": "auto",
        "warnings": ["partial_bar"],
    }


class AnalysisHistoryTestCase(unittest.TestCase):
    """分析历史存储测试"""

    def setUp(self) -> None:
        """为每个用例初始化独立数据库"""
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_analysis_history.db")
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "ENV_FILE",
                "DATABASE_PATH",
            )
        }
        self._env_path = os.path.join(self._temp_dir.name, ".env")
        with open(self._env_path, "w", encoding="utf-8") as env_file:
            env_file.write("STOCK_LIST=600519,000001\n")

        os.environ["ENV_FILE"] = self._env_path
        os.environ["DATABASE_PATH"] = self._db_path

        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        """清理资源"""
        Config._instance = None
        DatabaseManager.reset_instance()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._temp_dir.cleanup()

    def _build_result(self) -> AnalysisResult:
        """构造分析结果"""
        return AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=78,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="基本面稳健，短期震荡",
        )

    def _save_history(self, query_id: str) -> int:
        """保存一条测试历史记录并返回主键 ID。"""
        result = self._build_result()
        saved = self.db.save_analysis_history(
            result=result,
            query_id=query_id,
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            return row.id

    def test_save_analysis_history_with_snapshot(self) -> None:
        """保存历史记录并写入上下文快照"""
        result = self._build_result()
        result.dashboard = {
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "理想买入点：125.5元",
                    "secondary_buy": "120",
                    "stop_loss": "止损位：110元",
                    "take_profit": "目标位：150.0元",
                }
            }
        }
        context_snapshot = {"enhanced_context": {"code": "600519"}}

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_001",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True
        )

        self.assertGreater(saved, 0)

        history = self.db.get_analysis_history(code="600519", days=7, limit=10)
        self.assertEqual(len(history), 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            self.assertEqual(row.query_id, "query_001")
            self.assertIsNotNone(row.context_snapshot)
            self.assertEqual(row.ideal_buy, 125.5)
            self.assertEqual(row.secondary_buy, 120.0)
            self.assertEqual(row.stop_loss, 110.0)
            self.assertEqual(row.take_profit, 150.0)

    def test_history_display_resolves_bare_jp_kr_code_from_stock_pool(self) -> None:
        result = self._build_result()
        result.code = "005930"
        result.name = "Samsung Electronics"
        persisted_phase_summary = {
            **_market_phase_summary(),
            "phase": "postmarket",
            "market_local_time": "2025-01-02T16:10:00+09:00",
            "session_date": "2025-01-02",
            "effective_daily_bar_date": "2025-01-02",
            "is_market_open_now": False,
            "is_partial_bar": False,
            "minutes_to_open": 900,
            "minutes_to_close": None,
            "trigger_source": "scheduled_job",
            "analysis_intent": "postmarket",
            "warnings": ["legacy_snapshot"],
        }
        expected_phase_summary = {**persisted_phase_summary, "market": "kr"}
        expected_phase_summary["minutes_to_open"] = None

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_kr_bare",
            report_type="simple",
            news_content="news",
            context_snapshot={"market_phase_summary": persisted_phase_summary},
            save_snapshot=True,
        )
        self.assertGreater(saved, 0)

        service = HistoryService(self.db)
        with patch("src.services.history_service.resolve_index_stock_code", return_value="005930.KS"):
            listing = service.get_history_list(page=1, limit=5)
            detail = service.resolve_and_get_detail("query_kr_bare")

        self.assertEqual(listing["items"][0]["stock_code"], "005930.KS")
        self.assertEqual(listing["items"][0]["market_phase_summary"], expected_phase_summary)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["stock_code"], "005930.KS")
        self.assertEqual(detail["market_phase_summary"], expected_phase_summary)

    def test_history_display_rebuilds_market_phase_summary_for_legacy_cn_snapshot(self) -> None:
        result = self._build_result()
        result.code = "005930"
        result.name = "Samsung Electronics"
        persisted_phase_summary = {
            **_market_phase_summary(),
            "phase": "postmarket",
            "market_local_time": "2026-01-01T10:00:00+08:00",
            "session_date": "2026-01-01",
            "effective_daily_bar_date": "2025-12-31",
            "is_market_open_now": False,
            "is_partial_bar": False,
            "minutes_to_open": 900,
            "minutes_to_close": None,
            "trigger_source": "scheduled_job",
            "analysis_intent": "postmarket",
            "warnings": ["legacy_snapshot"],
        }

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_kr_legacy_snapshot",
            report_type="simple",
            news_content="news",
            context_snapshot={"market_phase_summary": persisted_phase_summary},
            save_snapshot=True,
        )
        self.assertGreater(saved, 0)

        service = HistoryService(self.db)
        with patch("src.services.history_service.resolve_index_stock_code", return_value="005930.KS"):
            items = service.get_history_list(page=1, limit=5)["items"]

        self.assertEqual(items[0]["stock_code"], "005930.KS")
        rebuilt = items[0]["market_phase_summary"]
        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt["market"], "kr")
        self.assertEqual(rebuilt["market_local_time"], "2026-01-01T11:00:00+09:00")
        self.assertEqual(rebuilt["effective_daily_bar_date"], "2025-12-30")
        self.assertIsNone(rebuilt["minutes_to_open"])

    def test_save_analysis_history_persists_sniper_columns_via_shared_parser(self) -> None:
        """迁出 sniper parser 后历史狙击点位列仍按原规则保存。"""
        result = self._build_result()
        result.dashboard = {
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "理想买入点：125.5元",
                    "secondary_buy": "1.52-1.53 (回踩MA5/10附近)",
                    "stop_loss": "—",
                    "take_profit": "目标位：150.0元",
                }
            }
        }

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_shared_sniper_parser",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot=None,
            save_snapshot=False,
        )

        self.assertGreater(saved, 0)
        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_shared_sniper_parser"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            self.assertEqual(row.ideal_buy, 125.5)
            self.assertEqual(row.secondary_buy, 1.53)
            self.assertIsNone(row.stop_loss)
            self.assertEqual(row.take_profit, 150.0)

    def test_get_latest_analysis_history_id_filters_by_report_type_and_latest_record(self) -> None:
        """按 query/code/report_type 返回最新真实历史主键。"""
        for report_type in ("simple", "full", "simple"):
            saved = self.db.save_analysis_history(
                result=self._build_result(),
                query_id="query_latest_id",
                report_type=report_type,
                news_content="新闻摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertGreater(saved, 0)

        simple_id = self.db.get_latest_analysis_history_id(
            query_id="query_latest_id",
            code="600519",
            report_type="simple",
        )
        full_id = self.db.get_latest_analysis_history_id(
            query_id="query_latest_id",
            code="600519",
            report_type="full",
        )

        self.assertIsNotNone(simple_id)
        self.assertIsNotNone(full_id)
        self.assertGreater(simple_id, full_id)

    def test_get_latest_analysis_history_id_requires_report_type(self) -> None:
        """report_type 是必传参数，避免误取同 query/code 的其他报告。"""
        with self.assertRaises(TypeError):
            self.db.get_latest_analysis_history_id(query_id="query", code="600519")

    def test_save_analysis_history_without_snapshot(self) -> None:
        """关闭快照保存时不写入 context_snapshot"""
        result = self._build_result()

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_002",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot={"foo": "bar"},
            save_snapshot=False
        )

        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            self.assertIsNone(row.context_snapshot)

    def test_save_analysis_history_persists_model_used(self) -> None:
        """model_used should be persisted in raw_result for history detail."""
        result = self._build_result()
        result.model_used = "gemini/gemini-2.0-flash"

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_003",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_003").first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            payload = json.loads(row.raw_result or "{}")
            self.assertEqual(payload.get("model_used"), "gemini/gemini-2.0-flash")

    def test_update_analysis_history_diagnostics_preserves_snapshot_fields(self) -> None:
        """通知发送后补写 diagnostics 时，不应覆盖已有上下文字段。"""
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id="query_diag_patch",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot={
                "enhanced_context": {"code": "600519"},
                "diagnostics": {
                    "trace_id": "trace-1",
                    "query_id": "query_diag_patch",
                    "stock_code": "600519",
                    "notification_runs": [],
                },
            },
            save_snapshot=True,
        )
        self.assertGreater(saved, 0)

        updated = self.db.update_analysis_history_diagnostics(
            query_id="query_diag_patch",
            code="600519",
            notification_runs=[
                {
                    "channel": "report",
                    "status": "success",
                    "success": True,
                }
            ],
        )

        self.assertEqual(updated, 1)
        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_diag_patch"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            snapshot = json.loads(row.context_snapshot or "{}")
            self.assertEqual(snapshot["enhanced_context"]["code"], "600519")
            notification_run = snapshot["diagnostics"]["notification_runs"][-1]
            self.assertEqual(notification_run["status"], "success")
            self.assertEqual(notification_run["trace_id"], "trace-1")

    def test_history_list_includes_timeline_summary_fields(self) -> None:
        """History list items expose the fields needed by the same-stock timeline drawer."""
        result = self._build_result()
        result.model_used = "gemini/gemini-2.5-pro"
        context_snapshot = {
            "enhanced_context": {
                "realtime": {
                    "price": "51.5",
                    "change_pct": "-4.61%",
                    "volume_ratio": "1.17",
                    "turnover_rate": "11.46",
                },
            },
            "market_phase_summary": _market_phase_summary(),
        }

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_timeline_summary",
            report_type="detailed",
            news_content="新闻摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertGreater(saved, 0)

        service = HistoryService(self.db)
        payload = service.get_history_list(stock_code="600519.SH", page=1, limit=5)

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["stock_code"], "600519")
        self.assertEqual(item["trend_prediction"], "看多")
        self.assertEqual(item["analysis_summary"], "基本面稳健，短期震荡")
        self.assertEqual(item["operation_advice"], "持有")
        self.assertEqual(item["action"], "buy")
        self.assertEqual(item["action_label"], "买入")
        self.assertEqual(item["model_used"], "gemini/gemini-2.5-pro")
        self.assertEqual(item["current_price"], 51.5)
        self.assertEqual(item["change_pct"], -4.61)
        self.assertEqual(item["volume_ratio"], 1.17)
        self.assertEqual(item["turnover_rate"], 11.46)
        self.assertEqual(item["market_phase_summary"]["phase"], "intraday")
        self.assertEqual(item["market_phase_summary"]["minutes_to_close"], 300)

    def test_history_persistence_keeps_softened_operation_advice_from_guardrail(self) -> None:
        """Conservative-market guardrail short operation_advice is persisted and exposed to history list."""
        result = self._build_result()
        result.decision_type = "buy"
        result.operation_advice = "立即买入并积极加仓"

        apply_daily_market_context_guardrail(
            result,
            daily_market_context={
                "region": "cn",
                "trade_date": "2026-06-06",
                "summary": "大盘退潮，高风险，建议观望，仓位上限30%。",
                "risk_tags": ["high_risk", "low_position_cap"],
            },
            report_language="zh",
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_softened_operation_advice",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertGreater(saved, 0)

        service = HistoryService(self.db)
        payload = service.get_history_list(stock_code="600519", page=1, limit=10)

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["operation_advice"], "观望")
        self.assertLessEqual(len(payload["items"][0]["operation_advice"]), 20)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_softened_operation_advice"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            self.assertEqual(row.operation_advice, "观望")

    def test_market_review_history_can_be_filtered_without_stock_records(self) -> None:
        """Market review records should be queryable as a dedicated history collection."""
        stock_result = self._build_result()
        market_result = AnalysisResult(
            code="MARKET",
            name="大盘复盘",
            sentiment_score=50,
            trend_prediction="大盘复盘",
            operation_advice="查看复盘",
            analysis_summary="大盘复盘摘要",
        )

        self.assertGreater(
            self.db.save_analysis_history(
                result=stock_result,
                query_id="query_stock_history",
                report_type="detailed",
                news_content="个股正文",
                context_snapshot=None,
                save_snapshot=False,
            ),
            0,
        )
        self.assertGreater(
            self.db.save_analysis_history(
                result=market_result,
                query_id="query_market_review_history",
                report_type="market_review",
                news_content="大盘复盘正文",
                context_snapshot={
                    "report_kind": "market_review",
                    "market_review_payload": {
                        "kind": "market_review",
                        "sections": [{"title": "复盘", "markdown": "结构化正文"}],
                    },
                },
                save_snapshot=True,
            ),
            0,
        )

        service = HistoryService(self.db)
        payload = service.get_history_list(
            stock_code="MARKET",
            report_type="market_review",
            page=1,
            limit=10,
        )

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["stock_code"], "MARKET")
        self.assertEqual(payload["items"][0]["report_type"], "market_review")
        self.assertIsNone(payload["items"][0]["action"])
        self.assertIsNone(payload["items"][0]["action_label"])

    def test_distinct_stock_bar_excludes_market_review_records_by_default(self) -> None:
        """The stock bar aggregation should not mix MARKET into ordinary stock entries."""
        stock_result = self._build_result()
        market_result = AnalysisResult(
            code="MARKET",
            name="大盘复盘",
            sentiment_score=50,
            trend_prediction="大盘复盘",
            operation_advice="查看复盘",
            analysis_summary="大盘复盘摘要",
        )

        self.assertGreater(
            self.db.save_analysis_history(
                result=stock_result,
                query_id="query_stock_bar_stock",
                report_type="detailed",
                news_content="个股正文",
                context_snapshot=None,
                save_snapshot=False,
            ),
            0,
        )
        self.assertGreater(
            self.db.save_analysis_history(
                result=market_result,
                query_id="query_stock_bar_market",
                report_type="market_review",
                news_content="大盘复盘正文",
                context_snapshot=None,
                save_snapshot=False,
            ),
            0,
        )

        records = self.db.get_distinct_stocks_from_history(limit=10)

        self.assertEqual([record.code for record in records], ["600519"])

    def test_history_list_matches_equivalent_suffixed_stock_codes(self) -> None:
        """Same-stock history should include rows saved with supported suffixed codes."""

        def save_record(code: str, query_id: str) -> None:
            result = self._build_result()
            result.code = code
            if "HK" in code:
                result.name = "腾讯控股"
            saved = self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type="simple",
                news_content="新闻摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertGreater(saved, 0)

        save_record("600519.SH", "query_cn_suffix")
        save_record("600519", "query_cn_plain")
        save_record("00700.HK", "query_hk_suffix")
        save_record("HK00700", "query_hk_prefix")

        service = HistoryService(self.db)

        cn_from_suffix = service.get_history_list(stock_code="600519.SH", page=1, limit=10)
        self.assertEqual(cn_from_suffix["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in cn_from_suffix["items"]},
            {"600519.SH", "600519"},
        )

        cn_from_plain = service.get_history_list(stock_code="600519", page=1, limit=10)
        self.assertEqual(cn_from_plain["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in cn_from_plain["items"]},
            {"600519.SH", "600519"},
        )

        hk_from_suffix = service.get_history_list(stock_code="00700.HK", page=1, limit=10)
        self.assertEqual(hk_from_suffix["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in hk_from_suffix["items"]},
            {"00700.HK", "HK00700"},
        )

        hk_from_prefix = service.get_history_list(stock_code="HK00700", page=1, limit=10)
        self.assertEqual(hk_from_prefix["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in hk_from_prefix["items"]},
            {"00700.HK", "HK00700"},
        )

    def test_history_list_matches_unpadded_hk_suffix_variants(self) -> None:
        """HK short suffix forms (e.g. 1810.HK) should match 5-digit canonical suffix/prefix forms."""

        def save_record(code: str, query_id: str) -> None:
            result = self._build_result()
            result.code = code
            if "HK" in code:
                result.name = "腾讯控股"
            saved = self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type="simple",
                news_content="新闻摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertGreater(saved, 0)

        save_record("1810.HK", "query_hk_unpadded")
        save_record("01810.HK", "query_hk_padded")
        save_record("HK01810", "query_hk_prefix")

        service = HistoryService(self.db)

        hk_from_suffix = service.get_history_list(stock_code="01810.HK", page=1, limit=10)
        self.assertEqual(hk_from_suffix["total"], 3)
        self.assertEqual(
            {item["stock_code"] for item in hk_from_suffix["items"]},
            {"1810.HK", "01810.HK", "HK01810"},
        )

        hk_from_prefix = service.get_history_list(stock_code="HK01810", page=1, limit=10)
        self.assertEqual(hk_from_prefix["total"], 3)
        self.assertEqual(
            {item["stock_code"] for item in hk_from_prefix["items"]},
            {"1810.HK", "01810.HK", "HK01810"},
        )

    def test_history_list_matches_sh_and_ss_suffixed_variants(self) -> None:
        """SH suffix and legacy `.SS` variants should be treated as the same A-share stock."""

        def save_record(code: str, query_id: str) -> None:
            result = self._build_result()
            result.code = code
            saved = self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type="simple",
                news_content="新闻摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertGreater(saved, 0)

        save_record("600519.SH", "query_cn_sh")
        save_record("600519.SS", "query_cn_ss")
        save_record("600519", "query_cn_plain")

        service = HistoryService(self.db)
        expected = {"600519.SH", "600519.SS", "600519"}

        from_sh = service.get_history_list(stock_code="600519.SH", page=1, limit=10)
        self.assertEqual(from_sh["total"], 3)
        self.assertEqual({item["stock_code"] for item in from_sh["items"]}, expected)

        from_ss = service.get_history_list(stock_code="600519.SS", page=1, limit=10)
        self.assertEqual(from_ss["total"], 3)
        self.assertEqual({item["stock_code"] for item in from_ss["items"]}, expected)

        from_plain = service.get_history_list(stock_code="600519", page=1, limit=10)
        self.assertEqual(from_plain["total"], 3)
        self.assertEqual({item["stock_code"] for item in from_plain["items"]}, expected)

    def test_history_detail_accepts_dict_raw_result(self) -> None:
        """_record_to_detail_dict should handle dict raw_result without json.loads errors."""
        result = self._build_result()
        result.model_used = "gemini/gemini-2.0-flash"
        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_005",
            report_type="simple",
            news_content="新闻摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_005").first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            row.raw_result = {"model_used": "unknown", "extra": "v"}

            service = HistoryService(self.db)
            detail = service._record_to_detail_dict(row)

        self.assertIsNotNone(detail)
        self.assertIsInstance(detail.get("raw_result"), dict)
        self.assertIsNone(detail.get("model_used"))

    def test_history_markdown_localizes_english_report_and_placeholder_name(self) -> None:
        """History markdown should preserve report_language for English reports."""
        result = AnalysisResult(
            code="AAPL",
            name="股票AAPL",
            sentiment_score=78,
            trend_prediction="Bullish",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
            dashboard={
                "core_conclusion": {
                    "one_sentence": "Favor buying on pullbacks.",
                    "position_advice": {
                        "no_position": "Open a starter position.",
                        "has_position": "Hold and trail the stop.",
                    },
                },
                "intelligence": {
                    "risk_alerts": [],
                },
                "battle_plan": {
                    "sniper_points": {
                        "ideal_buy": "180-182",
                        "stop_loss": "172",
                        "take_profit": "195",
                    }
                },
            },
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_english_markdown_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_english_markdown_001"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertIsNotNone(markdown)
        self.assertIn("Stock Analysis Report", markdown)
        self.assertIn("Core Conclusion", markdown)
        self.assertIn("Unnamed Stock (AAPL)", markdown)
        self.assertNotIn("核心结论", markdown)

    def test_history_markdown_returns_persisted_market_review_report(self) -> None:
        """Market review history should return the saved Markdown without rebuilding a stock report."""
        result = AnalysisResult(
            code="MARKET",
            name="大盘复盘",
            sentiment_score=50,
            trend_prediction="大盘复盘",
            operation_advice="查看复盘",
            analysis_summary="今日大盘复盘",
            raw_response="# 🎯 大盘复盘\n\n## 今日大盘\n\n复盘正文",
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="market_review_query_001",
            report_type="market_review",
            news_content="## 今日大盘\n\n复盘正文",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "market_review_query_001"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertEqual(markdown, "# 🎯 大盘复盘\n\n## 今日大盘\n\n复盘正文")

    def test_history_markdown_collapses_unavailable_chip_structure(self) -> None:
        result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=72,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="稳健",
            dashboard={
                "data_perspective": {
                    "chip_structure": {
                        "profit_ratio": "数据缺失，无法判断",
                        "avg_cost": "数据缺失，无法判断",
                        "concentration": "数据缺失，无法判断",
                        "chip_health": "数据缺失，无法判断",
                    }
                }
            },
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_chip_unavailable_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_chip_unavailable_001"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertIsNotNone(markdown)
        self.assertIn("**筹码**: 筹码分布未启用或数据源暂不可用，未纳入筹码判断。", markdown)
        self.assertEqual(markdown.count("数据缺失，无法判断"), 0)

    def test_history_markdown_uses_safe_bias_emoji_for_english_status(self) -> None:
        """English bias status should keep the correct non-risk emoji in markdown."""
        result = AnalysisResult(
            code="AAPL",
            name="股票AAPL",
            sentiment_score=80,
            trend_prediction="Bullish",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
            dashboard={
                "data_perspective": {
                    "price_position": {
                        "current_price": 190.5,
                        "ma5": 188.0,
                        "ma10": 184.5,
                        "ma20": 179.2,
                        "bias_ma5": 1.33,
                        "bias_status": "Safe",
                        "support_level": 184.5,
                        "resistance_level": 195.0,
                    }
                }
            },
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_english_markdown_bias_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertGreater(saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_english_markdown_bias_001"
            ).first()
            if row is None:
                self.fail("未找到保存的历史记录")
            self.assertEqual(row.id, saved)
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertIsNotNone(markdown)
        self.assertIn("✅Safe", markdown)
        self.assertNotIn("🚨Safe", markdown)

    def test_delete_analysis_history_records_also_cleans_backtests_and_decision_signals(self) -> None:
        """删除历史记录时应一并清理关联回测结果和决策信号。"""
        record_id = self._save_history("query_delete_001")
        linked_signal_id = None

        with self.db.session_scope() as session:
            session.add(BacktestResult(
                analysis_history_id=record_id,
                code="600519",
                analysis_date=None,
                eval_window_days=10,
                engine_version="v1",
                eval_status="pending",
            ))
            linked_signal = DecisionSignalRecord(
                stock_code="600519",
                stock_name="贵州茅台",
                market="cn",
                source_type="analysis",
                source_report_id=record_id,
                trace_id="trace-delete-linked",
                market_phase="intraday",
                trigger_source="api",
                action="buy",
                action_label="买入",
                reason="linked",
                plan_quality="minimal",
                status="active",
            )
            session.add(linked_signal)
            session.flush()
            linked_signal_id = linked_signal.id
            session.add(DecisionSignalOutcomeRecord(
                signal_id=linked_signal_id,
                horizon="3d",
                engine_version="decision-signal-v1",
                eval_status="completed",
                outcome="hit",
                action="buy",
                market="cn",
                source_type="analysis",
                plan_quality="minimal",
                holding_state="holding",
            ))
            session.add(DecisionSignalFeedbackRecord(
                signal_id=linked_signal_id,
                feedback_value="useful",
                source="api",
            ))
            session.add(DecisionSignalRecord(
                stock_code="000001",
                stock_name="平安银行",
                market="cn",
                source_type="analysis",
                source_report_id=record_id + 999,
                trace_id="trace-delete-unrelated",
                market_phase="intraday",
                trigger_source="api",
                action="watch",
                action_label="观望",
                reason="unrelated",
                plan_quality="minimal",
                status="active",
            ))

        deleted = self.db.delete_analysis_history_records([record_id])
        self.assertEqual(deleted, 1)

        with self.db.get_session() as session:
            self.assertIsNone(session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first())
            self.assertEqual(
                session.query(BacktestResult).filter(BacktestResult.analysis_history_id == record_id).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(DecisionSignalRecord.source_report_id == record_id).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalOutcomeRecord).filter(
                    DecisionSignalOutcomeRecord.signal_id == linked_signal_id
                ).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalFeedbackRecord).filter(
                    DecisionSignalFeedbackRecord.signal_id == linked_signal_id
                ).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(DecisionSignalRecord.trace_id == "trace-delete-unrelated").count(),
                1,
            )

    def test_delete_analysis_history_records_keeps_signals_for_nonexistent_history_id(self) -> None:
        """不存在的历史 ID 不应触发弱关联 DecisionSignal 清理。"""
        missing_id = 987654321

        with self.db.session_scope() as session:
            session.add(DecisionSignalRecord(
                stock_code="600519",
                stock_name="贵州茅台",
                market="cn",
                source_type="manual",
                source_report_id=missing_id,
                trace_id="trace-delete-missing-history",
                market_phase="intraday",
                trigger_source="api",
                action="watch",
                action_label="观望",
                reason="manual signal with unverified report id",
                plan_quality="minimal",
                status="active",
            ))

        deleted = self.db.delete_analysis_history_records([missing_id])
        self.assertEqual(deleted, 0)

        with self.db.get_session() as session:
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(
                    DecisionSignalRecord.trace_id == "trace-delete-missing-history"
                ).count(),
                1,
            )

    def test_delete_analysis_history_records_keeps_manual_signal_with_same_report_id(self) -> None:
        """source_report_id 是弱引用，真实 history 删除不应误删 manual/pre-report 信号。"""
        record_id = self._save_history("query_delete_manual_collision")

        with self.db.session_scope() as session:
            session.add(DecisionSignalRecord(
                stock_code="600519",
                stock_name="贵州茅台",
                market="cn",
                source_type="analysis",
                source_report_id=record_id,
                trace_id="trace-delete-analysis-bound",
                market_phase="intraday",
                trigger_source="api",
                action="buy",
                action_label="买入",
                reason="history-bound signal",
                plan_quality="minimal",
                status="active",
            ))
            session.add(DecisionSignalRecord(
                stock_code="600519",
                stock_name="贵州茅台",
                market="cn",
                source_type="manual",
                source_report_id=record_id,
                trace_id="trace-delete-manual-weak-ref",
                market_phase="intraday",
                trigger_source="api",
                action="watch",
                action_label="观望",
                reason="manual signal with caller-supplied report id",
                plan_quality="minimal",
                status="active",
            ))

        deleted = self.db.delete_analysis_history_records([record_id])
        self.assertEqual(deleted, 1)

        with self.db.get_session() as session:
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(
                    DecisionSignalRecord.trace_id == "trace-delete-analysis-bound"
                ).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(
                    DecisionSignalRecord.trace_id == "trace-delete-manual-weak-ref"
                ).count(),
                1,
            )

    def test_delete_analysis_history_records_cleans_only_existing_ids_in_mixed_batch(self) -> None:
        """混合存在/不存在 ID 时，只清理实际存在历史记录的关联数据。"""
        record_id = self._save_history("query_delete_mixed")
        missing_id = record_id + 987654

        with self.db.session_scope() as session:
            session.add(BacktestResult(
                analysis_history_id=record_id,
                code="600519",
                analysis_date=None,
                eval_window_days=10,
                engine_version="v1",
                eval_status="pending",
            ))
            session.add(DecisionSignalRecord(
                stock_code="600519",
                stock_name="贵州茅台",
                market="cn",
                source_type="analysis",
                source_report_id=record_id,
                trace_id="trace-delete-mixed-linked",
                market_phase="intraday",
                trigger_source="api",
                action="buy",
                action_label="买入",
                reason="linked",
                plan_quality="minimal",
                status="active",
            ))
            session.add(DecisionSignalRecord(
                stock_code="000001",
                stock_name="平安银行",
                market="cn",
                source_type="manual",
                source_report_id=missing_id,
                trace_id="trace-delete-mixed-missing",
                market_phase="intraday",
                trigger_source="api",
                action="watch",
                action_label="观望",
                reason="weak report id collision",
                plan_quality="minimal",
                status="active",
            ))

        deleted = self.db.delete_analysis_history_records([record_id, missing_id])
        self.assertEqual(deleted, 1)

        with self.db.get_session() as session:
            self.assertIsNone(session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first())
            self.assertEqual(
                session.query(BacktestResult).filter(BacktestResult.analysis_history_id == record_id).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(
                    DecisionSignalRecord.trace_id == "trace-delete-mixed-linked"
                ).count(),
                0,
            )
            self.assertEqual(
                session.query(DecisionSignalRecord).filter(
                    DecisionSignalRecord.trace_id == "trace-delete-mixed-missing"
                ).count(),
                1,
            )

