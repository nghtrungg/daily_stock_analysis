"""Regression coverage for the GitHub Actions to Supabase quote callback."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sqlite3
from pathlib import Path
from urllib.error import URLError

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "callback_analysis_run.py"
WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "00-daily-analysis.yml"
SPEC = importlib.util.spec_from_file_location("callback_analysis_run", SCRIPT_PATH)
assert SPEC and SPEC.loader
callback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(callback)

RUN_ID = "a59a1476-2ea4-4c86-9a3c-d0df438e8102"


def create_history_database(path: Path, rows: list[tuple[str, dict[str, object], str]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """create table analysis_history (
                id integer primary key, code text not null, name text, report_type text,
                sentiment_score integer, operation_advice text, trend_prediction text,
                analysis_summary text, raw_result text, created_at text
            )"""
        )
        connection.executemany(
            """insert into analysis_history (
                code, name, report_type, sentiment_score, operation_advice,
                trend_prediction, analysis_summary, raw_result, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                symbol, "Vinamilk", "simple", 72, "Nắm giữ", "Tích cực",
                "Xu hướng vẫn tích cực.", json.dumps(raw), created_at
            ) for symbol, raw, created_at in rows],
        )


def test_success_callback_uses_a_signed_minimal_quote_payload() -> None:
    quote = {"currentPriceVnd": 68400, "asOf": "2026-07-16T15:10:00+07:00", "source": "realtime:tencent"}
    report = {
        "code": "VNM.VN", "name": "Vinamilk", "reportType": "simple", "sentimentScore": 72,
        "operationAdvice": "Nắm giữ", "trendPrediction": "Tích cực", "dashboard": None,
    }
    body = callback.encode_callback_payload(
        RUN_ID, "succeeded", quote, analysis_date="2026-07-16T15:10:00+07:00", report=report
    )

    assert json.loads(body) == {
        "runId": RUN_ID,
        "status": "succeeded",
        "summary": "Phân tích đã hoàn tất và đã lưu giá tại thời điểm phân tích.",
        "analysisDate": "2026-07-16T15:10:00+07:00",
        "report": report,
        "quote": quote,
    }
    assert callback.sign_payload("callback-secret", body) == hmac.new(
        b"callback-secret", body.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def test_extract_current_run_quote_requires_one_matching_fresh_record(tmp_path: Path) -> None:
    database = tmp_path / "analysis.db"
    create_history_database(database, [
        ("VNM.VN", {"current_price": 68_400.4, "data_sources": "realtime:tencent"}, "2026-07-16 15:10:00"),
        ("FPT.VN", {"current_price": 110_000, "data_sources": "realtime:tencent"}, "2026-07-16 15:11:00"),
        ("VNM.VN", {"current_price": 67_000, "data_sources": "realtime:tencent"}, "2026-07-16 08:00:00"),
    ])

    assert callback.extract_current_run_quote(str(database), "vnm.vn", "2026-07-16T08:00:00Z") == {
        "currentPriceVnd": 68400,
        "asOf": "2026-07-16T15:10:00+07:00",
        "source": "realtime:tencent",
    }


def test_extract_current_run_analysis_projects_only_dashboard_report_fields(tmp_path: Path) -> None:
    database = tmp_path / "analysis.db"
    create_history_database(database, [(
        "VNM.VN",
        {
            "current_price": 68_400,
            "data_sources": "realtime:tencent",
            "dashboard": {"core_conclusion": {"one_sentence": "Xu hướng vẫn tích cực."}},
            "raw_response": "must-not-leave-sqlite",
            "model_used": "must-not-leave-sqlite",
        },
        "2026-07-16 15:10:00",
    )])

    projected = callback.extract_current_run_analysis(str(database), "VNM.VN", "2026-07-16T08:00:00Z")

    assert projected["analysisDate"] == "2026-07-16T15:10:00+07:00"
    assert projected["report"] == {
        "code": "VNM.VN",
        "name": "Vinamilk",
        "reportType": "simple",
        "sentimentScore": 72,
        "operationAdvice": "Nắm giữ",
        "trendPrediction": "Tích cực",
        "dashboard": {"core_conclusion": {"one_sentence": "Xu hướng vẫn tích cực."}},
    }
    assert "raw_response" not in json.dumps(projected)
    assert "model_used" not in json.dumps(projected)


@pytest.mark.parametrize("raw", [
    {"current_price": 0, "data_sources": "realtime:tencent"},
    {"current_price": float("nan"), "data_sources": "realtime:tencent"},
    {"current_price": 68_400, "data_sources": ""},
])
def test_extract_current_run_quote_rejects_invalid_quote_fields(tmp_path: Path, raw: dict[str, object]) -> None:
    database = tmp_path / "analysis.db"
    create_history_database(database, [("VNM.VN", raw, "2026-07-16 15:10:00")])

    with pytest.raises(callback.QuoteUnavailableError):
        callback.extract_current_run_quote(str(database), "VNM.VN", "2026-07-16T08:00:00Z")


def test_extract_current_run_quote_rejects_old_or_ambiguous_rows(tmp_path: Path) -> None:
    old_database = tmp_path / "old.db"
    create_history_database(old_database, [("VNM.VN", {"current_price": 68_400, "data_sources": "fixture"}, "2026-07-16 08:00:00")])
    with pytest.raises(callback.QuoteUnavailableError):
        callback.extract_current_run_quote(str(old_database), "VNM.VN", "2026-07-16T08:00:00Z")

    ambiguous_database = tmp_path / "ambiguous.db"
    create_history_database(ambiguous_database, [
        ("VNM.VN", {"current_price": 68_400, "data_sources": "fixture"}, "2026-07-16 15:10:00"),
        ("VNM.VN", {"current_price": 68_500, "data_sources": "fixture"}, "2026-07-16 15:11:00"),
    ])
    with pytest.raises(callback.QuoteUnavailableError):
        callback.extract_current_run_quote(str(ambiguous_database), "VNM.VN", "2026-07-16T08:00:00Z")


def test_callback_delivery_retries_twice_then_succeeds_without_real_sleep() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(_request, timeout: int):
        assert timeout == 15
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("temporary")
        return Response()

    assert callback.deliver_callback(
        RUN_ID,
        "https://project.supabase.co/functions/v1/analysis-callback",
        "secret",
        "{}",
        opener=opener,
        sleeper=sleeps.append,
    )
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]


def test_callback_configuration_rejects_non_https_endpoints() -> None:
    assert callback.is_safe_callback_url("https://project.supabase.co/functions/v1/analysis-callback")
    assert not callback.is_safe_callback_url("http://localhost:54321/functions/v1/analysis-callback")
    with pytest.raises(ValueError):
        callback.encode_callback_payload(RUN_ID, "unexpected")


def test_workflow_passes_exact_current_run_quote_context() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "id: tracking_context" in workflow
    assert "date --utc '+%Y-%m-%dT%H:%M:%SZ'" in workflow
    assert "ANALYSIS_CALLBACK_SYMBOL: ${{ inputs.stock_symbols }}" in workflow
    assert "ANALYSIS_CALLBACK_STARTED_AT: ${{ steps.tracking_context.outputs.started_at }}" in workflow
    assert "DATABASE_PATH: ${{ env.DATABASE_PATH }}" in workflow
