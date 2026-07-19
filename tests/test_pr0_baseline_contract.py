from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.generate_pr0_schema_inventory import build_inventory
from src.core.pipeline import StockAnalysisPipeline


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "migration" / "pr0-schema-inventory.json"
OWNERSHIP_PATH = ROOT / "docs" / "migration" / "schema-ownership-register.json"
RUN_FIXTURES_PATH = ROOT / "tests" / "fixtures" / "pr0" / "representative_runs.json"


def test_generated_schema_inventory_matches_runtime_metadata():
    recorded = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    assert recorded == build_inventory()
    assert recorded["table_count"] == 32
    assert recorded["baseline"]["runtime_schema_version"] == (
        "2026-07-18-settlement-z-outcomes"
    )


def test_schema_ownership_register_covers_every_current_orm_table_once():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    register = json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))

    table_sets = [
        item
        for item in register["objects"]
        if item["object_type"] == "table_set"
        and item["names_from"] == "docs/migration/pr0-schema-inventory.json#tables"
    ]

    assert len(table_sets) == 1
    assert table_sets[0]["owner"] == "daily_stock_analysis"
    assert len(inventory["tables"]) == inventory["table_count"]
    assert register["review_gate"]["duplicate_owner_count"] == 0
    assert register["review_gate"]["unowned_current_object_count"] == 0


def test_representative_run_fixtures_are_complete_and_sanitized():
    fixtures = json.loads(RUN_FIXTURES_PATH.read_text(encoding="utf-8"))

    assert {item["scenario"] for item in fixtures} == {
        "single_stock",
        "batch",
        "failed_provider",
        "stale_quote",
        "partial_data",
        "no_news",
    }
    serialized = json.dumps(fixtures, ensure_ascii=False).lower()
    assert all(
        forbidden not in serialized
        for forbidden in (
            "api_key",
            "authorization",
            "cookie",
            "password",
            "prompt",
            "raw_payload",
            "token",
        )
    )
    for fixture in fixtures:
        assert fixture["symbols"]
        assert all(symbol == symbol.upper() and symbol.endswith(".VN") for symbol in fixture["symbols"])


def test_single_stock_stage_order_is_fetch_analyze_notify():
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    events: list[str] = []
    pipeline._resolve_resume_target_date = MagicMock(return_value=None)
    pipeline._emit_progress = MagicMock()
    pipeline.fetch_and_save_stock_data = MagicMock(
        side_effect=lambda *args, **kwargs: (events.append("fetch") or True, None)
    )
    result = SimpleNamespace(
        success=True,
        operation_advice="QUAN SÁT",
        sentiment_score=50,
    )
    pipeline.analyze_stock = MagicMock(
        side_effect=lambda *args, **kwargs: events.append("analyze") or result
    )
    pipeline._send_single_stock_notification = MagicMock(
        side_effect=lambda *args, **kwargs: events.append("notify")
    )

    actual = pipeline.process_single_stock(
        "VNM.VN",
        single_stock_notify=True,
        analysis_query_id="pr0-stage-order",
    )

    assert actual is result
    assert events == ["fetch", "analyze", "notify"]


def test_fetch_failure_remains_fail_open_for_analysis():
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._resolve_resume_target_date = MagicMock(return_value=None)
    pipeline._emit_progress = MagicMock()
    pipeline.fetch_and_save_stock_data = MagicMock(return_value=(False, "provider unavailable"))
    expected = SimpleNamespace(success=False, error_message="insufficient cached data")
    pipeline.analyze_stock = MagicMock(return_value=expected)

    actual = pipeline.process_single_stock(
        "VNM.VN",
        analysis_query_id="pr0-provider-fail-open",
    )

    assert actual is expected
    pipeline.analyze_stock.assert_called_once()
