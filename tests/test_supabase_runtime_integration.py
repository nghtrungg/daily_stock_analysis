# -*- coding: utf-8 -*-
"""Disposable PostgreSQL validation for the PR2 SQLAlchemy runtime."""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import delete, event, select

from src.repositories.database import build_database_runtime
from src.repositories.backtest_repo import BacktestRepository
from src.repositories.intelligence_repo import IntelligenceRepository
from src.repositories.decision_signal_outcome_repo import DecisionSignalOutcomeRepository
from src.repositories.models import (
    AnalysisHistory,
    BacktestResult,
    BacktestSummary,
    DecisionSignalOutcomeRecord,
    IntelligenceItem,
    NewsIntel,
    StockDaily,
)
from src.search_service import SearchResponse, SearchResult
from src.storage import DatabaseManager


pytestmark = pytest.mark.integration


def _runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        sqlite_busy_timeout_ms=5000,
        database_connect_timeout_seconds=10,
        database_statement_timeout_ms=120000,
        database_idle_transaction_timeout_ms=30000,
        database_pool_strategy="null",
        database_pool_size=1,
        database_max_overflow=0,
        database_pool_timeout_seconds=10,
        database_pool_recycle_seconds=300,
    )


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL is provided only by the disposable database CI job.",
)
def test_supabase_runtime_health_jsonb_timestamp_and_rollback() -> None:
    """Exercise the real driver, private schema mapping, JSONB, and timestamptz."""
    runtime = build_database_runtime(os.environ["SUPABASE_DB_URL"], _runtime_config())
    query_id = f"pr2-runtime-{uuid4()}"
    supplied_time = datetime(2026, 7, 21, 12, 30, tzinfo=timezone(timedelta(hours=7)))
    expected_time = datetime(2026, 7, 21, 5, 30)
    payload = {"message": "Kiểm tra PostgreSQL", "currency": "VND"}

    try:
        assert runtime.health_check() is True
        with runtime.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    AnalysisHistory.__table__.insert().values(
                        query_id=query_id,
                        code="VNM.VN",
                        report_type="stock",
                        raw_result=payload,
                        context_snapshot={},
                        created_at=supplied_time,
                    )
                )
                row = connection.execute(
                    select(
                        AnalysisHistory.raw_result,
                        AnalysisHistory.context_snapshot,
                        AnalysisHistory.created_at,
                    ).where(AnalysisHistory.query_id == query_id)
                ).one()

                assert row.raw_result == payload
                assert row.context_snapshot == {}
                assert row.created_at == expected_time
            finally:
                transaction.rollback()
    finally:
        runtime.dispose()


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL is provided only by the disposable database CI job.",
)
def test_postgres_daily_and_news_upserts_are_batched_and_idempotent() -> None:
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_url=os.environ["SUPABASE_DB_URL"])
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        lowered = statement.lower()
        if "stock_daily" in lowered or "news_intel" in lowered:
            statements.append(lowered)

    event.listen(db._engine, "before_cursor_execute", capture_statement)
    dates = pd.date_range("2025-11-01", periods=250, freq="D")
    daily = pd.DataFrame(
        {
            "date": dates,
            "open": range(250),
            "high": range(1, 251),
            "low": range(250),
            "close": range(1, 251),
            "volume": [1_000] * 250,
        }
    )
    news = SearchResponse(
        query="VNM.VN",
        provider="integration",
        results=[
            SearchResult(
                title=f"Tin Việt Nam {index}",
                snippet=f"Nội dung {index}",
                url=f"https://integration.example/news/{index}",
                source="integration",
                published_date="2026-07-21",
                relevance_score=5,
            )
            for index in range(100)
        ],
    )
    try:
        with db._engine.begin() as connection:
            connection.execute(delete(StockDaily).where(StockDaily.code == "VNM.VN"))
            connection.execute(
                delete(NewsIntel).where(NewsIntel.provider == "integration")
            )
        statements.clear()

        assert db.save_daily_data(daily, "VNM.VN", "integration-first") == 250
        daily_writes = list(statements)
        assert sum(stmt.lstrip().startswith("select") for stmt in daily_writes) == 1
        assert sum(stmt.lstrip().startswith("insert") for stmt in daily_writes) == 1

        with db.get_session() as session:
            original_created_at = session.execute(
                select(StockDaily.created_at).where(
                    StockDaily.code == "VNM.VN",
                    StockDaily.date == date(2025, 11, 1),
                )
            ).scalar_one()

        daily.loc[0, "close"] = 999
        assert db.save_daily_data(daily, "VNM.VN", "integration-update") == 0
        with db.get_session() as session:
            row = session.execute(
                select(StockDaily).where(
                    StockDaily.code == "VNM.VN",
                    StockDaily.date == date(2025, 11, 1),
                )
            ).scalar_one()
            assert row.close == 999
            assert row.created_at == original_created_at

        statements.clear()
        assert db.save_news_intel(
            "VNM.VN", "Vinamilk", "latest_news", "VNM.VN", news
        ) == 100
        assert sum(stmt.lstrip().startswith("select") for stmt in statements) == 0
        assert sum(stmt.lstrip().startswith("insert") for stmt in statements) == 1
        assert db.save_news_intel(
            "VNM.VN", "Vinamilk", "latest_news", "VNM.VN", news
        ) == 0
    finally:
        event.remove(db._engine, "before_cursor_execute", capture_statement)
        with db._engine.begin() as connection:
            connection.execute(delete(StockDaily).where(StockDaily.code == "VNM.VN"))
            connection.execute(
                delete(NewsIntel).where(NewsIntel.provider == "integration")
            )
        DatabaseManager.reset_instance()


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL is provided only by the disposable database CI job.",
)
def test_postgres_null_source_intelligence_upsert_is_concurrency_safe() -> None:
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_url=os.environ["SUPABASE_DB_URL"])
    url = f"https://integration.example/intelligence/{uuid4()}"
    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait()
            saved = IntelligenceRepository(db).upsert_items(
                [
                    {
                        "source_id": None,
                        "source_name": "integration-feed",
                        "source_type": "rss",
                        "title": "Tin doanh nghiệp Việt Nam",
                        "summary": "Thông tin kiểm thử đồng thời.",
                        "url": url,
                        "source": "integration",
                        "scope_type": "symbol",
                        "scope_value": "VNM.VN",
                        "market": "vn",
                    }
                ]
            )
            results.append(saved)
        except BaseException as exc:  # surfaced after both writers finish
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        assert not errors
        assert all(not thread.is_alive() for thread in threads)
        assert sorted(results) == [0, 1]
        with db.get_session() as session:
            rows = session.execute(
                select(IntelligenceItem).where(IntelligenceItem.url == url)
            ).scalars().all()
            assert len(rows) == 1
    finally:
        with db._engine.begin() as connection:
            connection.execute(delete(IntelligenceItem).where(IntelligenceItem.url == url))
        DatabaseManager.reset_instance()


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL is provided only by the disposable database CI job.",
)
def test_postgres_backtest_metric_batches_use_bounded_statements() -> None:
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_url=os.environ["SUPABASE_DB_URL"])
    repo = BacktestRepository(db)
    prefix = f"pr3-metrics-{uuid4()}"
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "backtest_results" in statement.lower() or "backtest_summaries" in statement.lower():
            statements.append(statement.lower())

    event.listen(db._engine, "before_cursor_execute", capture_statement)
    history_ids: list[int] = []
    try:
        with db._engine.begin() as connection:
            for index in range(50):
                history_ids.append(
                    connection.execute(
                        AnalysisHistory.__table__.insert()
                        .values(
                            query_id=f"{prefix}-{index}",
                            code="FPT.VN",
                            report_type="stock",
                            raw_result={},
                            context_snapshot={},
                        )
                        .returning(AnalysisHistory.id)
                    ).scalar_one()
                )

        statements.clear()
        results = [
            BacktestResult(
                analysis_history_id=history_id,
                code="FPT.VN",
                analysis_date=date(2026, 7, 1),
                eval_window_days=10,
                engine_version="pr3",
                eval_status="completed",
            )
            for history_id in history_ids
        ]
        assert repo.save_results_batch(results) == 50
        assert sum(stmt.lstrip().startswith("insert") for stmt in statements) == 1

        statements.clear()
        summaries = [
            BacktestSummary(
                scope="overall",
                code="__OVERALL__",
                eval_window_days=10,
                engine_version="pr3",
                total_evaluations=50,
                advice_breakdown_json={},
                diagnostics_json={},
            ),
            BacktestSummary(
                scope="stock",
                code="FPT.VN",
                eval_window_days=10,
                engine_version="pr3",
                total_evaluations=50,
                advice_breakdown_json={},
                diagnostics_json={},
            ),
        ]
        assert repo.upsert_summaries(summaries) == 2
        assert sum(stmt.lstrip().startswith("insert") for stmt in statements) == 1
        summaries[1].total_evaluations = 51
        assert repo.upsert_summaries(summaries) == 2
        with db.get_session() as session:
            assert session.execute(
                select(BacktestSummary.total_evaluations).where(
                    BacktestSummary.scope == "stock",
                    BacktestSummary.code == "FPT.VN",
                    BacktestSummary.eval_window_days == 10,
                    BacktestSummary.engine_version == "pr3",
                )
            ).scalar_one() == 51
    finally:
        event.remove(db._engine, "before_cursor_execute", capture_statement)
        with db._engine.begin() as connection:
            connection.execute(
                delete(BacktestSummary).where(BacktestSummary.engine_version == "pr3")
            )
            if history_ids:
                connection.execute(
                    delete(BacktestResult).where(
                        BacktestResult.analysis_history_id.in_(history_ids)
                    )
                )
                connection.execute(
                    delete(AnalysisHistory).where(AnalysisHistory.id.in_(history_ids))
                )
        DatabaseManager.reset_instance()


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"),
    reason="SUPABASE_DB_URL is provided only by the disposable database CI job.",
)
def test_postgres_decision_outcome_batch_is_idempotent() -> None:
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_url=os.environ["SUPABASE_DB_URL"])
    repo = DecisionSignalOutcomeRepository(db)
    signal_ids = list(range(9_100_000, 9_100_050))
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "decision_signal_outcomes" in statement.lower():
            statements.append(statement.lower())

    event.listen(db._engine, "before_cursor_execute", capture_statement)
    fields = [
        {
            "signal_id": signal_id,
            "horizon": "5d",
            "engine_version": "pr3-integration",
            "eval_status": "completed",
            "outcome": "hit",
            "market": "vn",
        }
        for signal_id in signal_ids
    ]
    try:
        with db._engine.begin() as connection:
            connection.execute(
                delete(DecisionSignalOutcomeRecord).where(
                    DecisionSignalOutcomeRecord.engine_version == "pr3-integration"
                )
            )
        statements.clear()

        first = repo.upsert_outcomes(fields)
        assert all(created for _row, created in first)
        assert sum(stmt.lstrip().startswith("insert") for stmt in statements) == 1

        statements.clear()
        second = repo.upsert_outcomes(fields)
        assert all(not created for _row, created in second)
        assert sum(stmt.lstrip().startswith("insert") for stmt in statements) == 1
    finally:
        event.remove(db._engine, "before_cursor_execute", capture_statement)
        with db._engine.begin() as connection:
            connection.execute(
                delete(DecisionSignalOutcomeRecord).where(
                    DecisionSignalOutcomeRecord.engine_version == "pr3-integration"
                )
            )
        DatabaseManager.reset_instance()
