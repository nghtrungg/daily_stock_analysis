# -*- coding: utf-8 -*-
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from src.config import Config
from src.core.config_registry import WEB_SETTINGS_HIDDEN_FROM_UI
from src.repositories.database import (
    DatabaseConnectionError,
    build_database_runtime,
)
from src.repositories.json_compat import InvalidLegacyJSON, normalize_json_value
from src.repositories.models import AnalysisHistory, Base
from src.storage import AnalysisHistory as FacadeAnalysisHistory
from src.storage import DatabaseManager


def _config(**changes) -> Config:
    return replace(Config(), **changes)


def test_supabase_backend_requires_secret_without_echoing_a_url() -> None:
    config = _config(database_backend="supabase", supabase_db_url=None)

    with pytest.raises(ValueError, match="SUPABASE_DB_URL is required") as exc_info:
        config.get_db_url()

    assert "password" not in str(exc_info.value).lower()


def test_supabase_backend_rejects_non_postgres_url_without_echoing_it() -> None:
    secret_url = "mysql://worker:very-secret@example.test/db"
    config = _config(database_backend="supabase", supabase_db_url=secret_url)

    with pytest.raises(ValueError, match="must use PostgreSQL") as exc_info:
        config.get_db_url()

    assert secret_url not in str(exc_info.value)
    assert "very-secret" not in str(exc_info.value)


def test_supabase_settings_load_from_env_and_remain_hidden_from_web_settings() -> None:
    env = {
        "DATABASE_BACKEND": "supabase",
        "SUPABASE_DB_URL": "postgresql+psycopg2://worker:secret@example.test/postgres",
        "DATABASE_POOL_STRATEGY": "queue",
        "DATABASE_POOL_SIZE": "2",
        "DATABASE_MAX_OVERFLOW": "1",
    }
    with patch.dict("os.environ", env, clear=False):
        config = Config._load_from_env()

    assert config.database_backend == "supabase"
    assert config.database_pool_strategy == "queue"
    assert config.database_pool_size == 2
    assert config.database_max_overflow == 1
    assert {
        "DATABASE_BACKEND",
        "SUPABASE_DB_URL",
        "DATABASE_POOL_STRATEGY",
    }.issubset(WEB_SETTINGS_HIDDEN_FROM_UI)


def test_sqlite_runtime_health_check_and_disposal() -> None:
    runtime = build_database_runtime("sqlite:///:memory:", _config())
    try:
        assert runtime.is_sqlite is True
        assert runtime.health_check() is True
    finally:
        runtime.dispose()


def test_supabase_null_pool_is_bounded_and_secret_safe() -> None:
    engine = MagicMock()
    engine.execution_options.return_value = engine
    config = _config(database_backend="supabase", database_pool_strategy="null")
    secret_url = "postgresql+psycopg2://worker:very-secret@example.test:6543/postgres"

    with patch("src.repositories.database.create_engine", return_value=engine) as mocked:
        runtime = build_database_runtime(secret_url, config)

    _, kwargs = mocked.call_args
    assert kwargs["poolclass"] is NullPool
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["connect_args"]["connect_timeout"] == 10
    assert kwargs["connect_args"]["application_name"] == "daily_stock_analysis_worker"
    assert "statement_timeout=120000" in kwargs["connect_args"]["options"]
    engine.execution_options.assert_called_once_with(
        schema_translate_map={None: "dsa"}
    )
    assert runtime.is_sqlite is False


def test_supabase_queue_pool_uses_one_runner_limits() -> None:
    engine = MagicMock()
    engine.execution_options.return_value = engine
    config = _config(
        database_backend="supabase",
        database_pool_strategy="queue",
        database_pool_size=1,
        database_max_overflow=0,
    )

    with patch("src.repositories.database.create_engine", return_value=engine) as mocked:
        build_database_runtime(
            "postgresql+psycopg2://worker:secret@example.test/postgres",
            config,
        )

    _, kwargs = mocked.call_args
    assert kwargs["pool_size"] == 1
    assert kwargs["max_overflow"] == 0
    assert kwargs["pool_timeout"] == 10
    assert kwargs["pool_recycle"] == 300


def test_engine_initialization_error_does_not_expose_secret() -> None:
    secret_url = "postgresql+psycopg2://worker:very-secret@example.test/postgres"

    with patch(
        "src.repositories.database.create_engine",
        side_effect=RuntimeError(secret_url),
    ):
        with pytest.raises(DatabaseConnectionError) as exc_info:
            build_database_runtime(secret_url, _config())

    assert secret_url not in str(exc_info.value)
    assert "very-secret" not in str(exc_info.value)


def test_storage_keeps_model_import_identity_stable() -> None:
    assert FacadeAnalysisHistory is AnalysisHistory


def test_postgres_manager_never_runs_runtime_ddl() -> None:
    DatabaseManager.reset_instance()
    runtime = MagicMock()
    runtime.engine.url.get_backend_name.return_value = "postgresql"
    runtime.is_sqlite = False
    runtime.session_factory = MagicMock()
    try:
        with (
            patch("src.storage.build_database_runtime", return_value=runtime),
            patch.object(Base.metadata, "create_all") as create_all,
        ):
            manager = DatabaseManager(
                db_url="postgresql+psycopg2://worker:secret@example.test/postgres"
            )

        create_all.assert_not_called()
        assert manager._is_sqlite_engine is False
    finally:
        DatabaseManager.reset_instance()


def test_postgres_model_uses_jsonb_without_persisting_full_context_pack() -> None:
    ddl = str(CreateTable(AnalysisHistory.__table__).compile(dialect=postgresql.dialect()))

    assert "raw_result JSONB" in ddl
    assert "context_snapshot JSONB" in ddl
    assert "created_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "analysis_context_pack" not in ddl


def test_json_compat_handles_native_legacy_null_and_empty_values() -> None:
    native = {"message": "Báo cáo Việt Nam"}
    normalized = normalize_json_value(
        native,
        field_name="analysis_history.context_snapshot",
        expected_types=(dict,),
    )
    assert normalized == native
    assert normalized is not native
    assert normalize_json_value(
        '{"message":"Báo cáo Việt Nam"}',
        field_name="analysis_history.context_snapshot",
        expected_types=(dict,),
    ) == native
    assert normalize_json_value(
        None,
        field_name="analysis_history.context_snapshot",
        expected_types=(dict,),
        sql_null_value={"state": "sql-null"},
    ) == {"state": "sql-null"}
    assert normalize_json_value(
        "null",
        field_name="analysis_history.context_snapshot",
        expected_types=(dict,),
        json_null_value={"state": "json-null"},
    ) == {"state": "json-null"}
    assert normalize_json_value(
        "{}",
        field_name="analysis_history.context_snapshot",
        expected_types=(dict,),
    ) == {}
    assert normalize_json_value(
        "[]",
        field_name="intelligence_items.raw_payload",
        expected_types=(dict, list),
    ) == []


def test_json_compat_quarantines_invalid_legacy_json_without_raw_payload() -> None:
    secret_payload = '{"token":"secret"'

    with pytest.raises(InvalidLegacyJSON) as exc_info:
        normalize_json_value(
            secret_payload,
            field_name="intelligence_items.raw_payload",
        )

    assert "intelligence_items.raw_payload" in str(exc_info.value)
    assert secret_payload not in str(exc_info.value)


def test_sqlite_json_column_preserves_legacy_string_contract() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            AnalysisHistory.__table__.insert().values(
                code="VNM.VN",
                raw_result={"message": "Tiếng Việt"},
                context_snapshot={},
            )
        )
        row = connection.execute(AnalysisHistory.__table__.select()).one()

    assert row.raw_result == '{"message": "Tiếng Việt"}'
    assert row.context_snapshot == "{}"
