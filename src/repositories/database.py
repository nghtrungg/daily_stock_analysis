# -*- coding: utf-8 -*-
"""Database engine/session construction shared by storage compatibility layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool


class DatabaseConnectionError(RuntimeError):
    """Secret-safe database initialization or health-check failure."""


@dataclass(frozen=True)
class DatabaseRuntime:
    """Owned SQLAlchemy resources for one configured database backend."""

    engine: Engine
    session_factory: sessionmaker
    is_sqlite: bool

    def health_check(self) -> bool:
        """Verify that a connection can execute a bounded trivial query."""
        try:
            with self.engine.connect() as connection:
                return connection.execute(text("select 1")).scalar_one() == 1
        except Exception as exc:
            raise DatabaseConnectionError(
                "Database health check failed."
            ) from exc

    def dispose(self) -> None:
        """Release every application-owned database connection."""
        self.engine.dispose()


def _postgres_connect_args(config: Any) -> dict[str, Any]:
    options = " ".join(
        (
            f"-c statement_timeout={config.database_statement_timeout_ms}",
            (
                "-c idle_in_transaction_session_timeout="
                f"{config.database_idle_transaction_timeout_ms}"
            ),
        )
    )
    return {
        "connect_timeout": config.database_connect_timeout_seconds,
        "application_name": "daily_stock_analysis_worker",
        "options": options,
    }


def build_database_runtime(db_url: str, config: Any) -> DatabaseRuntime:
    """Create a secret-safe, backend-aware SQLAlchemy engine and session factory."""
    is_sqlite = db_url.startswith("sqlite:")
    engine_kwargs: dict[str, Any] = {
        "echo": False,
        "pool_pre_ping": True,
    }

    if is_sqlite:
        if config.sqlite_busy_timeout_ms > 0:
            engine_kwargs["connect_args"] = {
                "timeout": config.sqlite_busy_timeout_ms / 1000,
            }
    else:
        engine_kwargs["connect_args"] = _postgres_connect_args(config)
        if config.database_pool_strategy == "null":
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs.update(
                {
                    "pool_size": config.database_pool_size,
                    "max_overflow": config.database_max_overflow,
                    "pool_timeout": config.database_pool_timeout_seconds,
                    "pool_recycle": config.database_pool_recycle_seconds,
                }
            )

    try:
        engine = create_engine(db_url, **engine_kwargs)
    except Exception as exc:
        backend = "sqlite" if is_sqlite else "postgresql"
        raise DatabaseConnectionError(
            f"Could not initialize the {backend} database engine."
        ) from exc
    if not is_sqlite:
        # PR1 owns production DDL in the private compute schema. Existing models
        # remain unqualified so SQLite tests keep their historical table names.
        engine = engine.execution_options(schema_translate_map={None: "dsa"})

    return DatabaseRuntime(
        engine=engine,
        session_factory=sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
        ),
        is_sqlite=is_sqlite,
    )
