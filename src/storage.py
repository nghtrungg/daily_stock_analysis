# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 存储层
===================================

职责：
1. 管理 SQLite 数据库连接（单例模式）
2. 定义 ORM 数据模型
3. 提供数据存取接口
4. 实现智能更新逻辑（断点续传）
"""

import atexit
from contextlib import contextmanager, nullcontext
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Tuple, Callable, TypeVar, Union

import pandas as pd
from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
    text,
    select,
    and_,
    or_,
    delete,
    desc,
    event,
    func,
    inspect,
    MetaData,
    Table,
    literal_column,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from src.agent.provider_trace import PROVIDER_TRACE_RETENTION_LIMIT
from src.config import get_config
from src.repositories.database import build_database_runtime
from src.repositories.bulk import chunk_mappings, is_transient_postgres_error
from src.schema_migrations import SchemaMigration, run_ordered_migrations
from src.utils.sniper_points import extract_sniper_points, parse_sniper_value

if TYPE_CHECKING:
    from src.search_service import SearchResponse

logger = logging.getLogger(__name__)
T = TypeVar("T")
BASELINE_SCHEMA_VERSION = "2026-06-05-create-all-baseline"


def _record_create_all_baseline(_connection, _manager) -> None:
    """Record the pre-runner create_all baseline without changing user data."""


def _apply_ordered_migration_foundation(connection, manager) -> None:
    """Bring legacy SQLite compatibility repairs under the ordered runner."""
    manager._ensure_llm_usage_telemetry_columns(connection=connection)
    manager._ensure_intelligence_item_scope_values(connection=connection)
    manager._ensure_intelligence_items_unique_index(connection=connection)


def _apply_settlement_aware_ledger_migration(connection, manager) -> None:
    """Add nullable settlement-ledger fields without rewriting portfolio data."""
    manager._ensure_portfolio_settlement_schema(connection=connection)


def _apply_settlement_signal_alert_migration(connection, _manager) -> None:
    """Add PR6 signal linkage and persistent settlement-alert state."""
    DecisionSignalTradeLink.__table__.create(connection, checkfirst=True)
    SettlementAlertStateRecord.__table__.create(connection, checkfirst=True)


def _apply_settlement_outcome_migration(connection, _manager) -> None:
    """Add PR7 versioned signal and execution outcome sidecars."""
    SettlementOutcomeRecord.__table__.create(connection, checkfirst=True)


ORDERED_SCHEMA_MIGRATIONS = (
    SchemaMigration(
        version=BASELINE_SCHEMA_VERSION,
        description="Baseline schema created through SQLAlchemy metadata.create_all",
        upgrade=_record_create_all_baseline,
    ),
    SchemaMigration(
        version="2026-07-18-ordered-migration-foundation",
        description="Adopt ordered migrations and apply existing SQLite compatibility repairs",
        upgrade=_apply_ordered_migration_foundation,
    ),
    SchemaMigration(
        version="2026-07-18-settlement-aware-ledger",
        description="Add trade execution, settlement sidecar, and derived settlement cache fields",
        upgrade=_apply_settlement_aware_ledger_migration,
    ),
    SchemaMigration(
        version="2026-07-18-settlement-signal-alerts",
        description="Add DecisionSignal trade links and settlement alert transition state",
        upgrade=_apply_settlement_signal_alert_migration,
    ),
    SchemaMigration(
        version="2026-07-18-settlement-z-outcomes",
        description="Add versioned settlement-aware signal and execution outcomes",
        upgrade=_apply_settlement_outcome_migration,
    ),
)
CURRENT_SCHEMA_VERSION = ORDERED_SCHEMA_MIGRATIONS[-1].version

from src.repositories.models import (
    AgentProviderTurn,
    AlertCooldownRecord,
    AlertNotificationRecord,
    AlertRuleRecord,
    AlertTriggerRecord,
    AnalysisHistory,
    BacktestResult,
    BacktestSummary,
    Base,
    ConversationMessage,
    ConversationSummary,
    DatabaseSchemaMigration,
    DecisionSignalFeedbackRecord,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
    DecisionSignalTradeLink,
    FundamentalSnapshot,
    INTELLIGENCE_ITEM_NULL_SCOPE_VALUE,
    IntelligenceItem,
    IntelligenceSource,
    LLMUsage,
    NewsIntel,
    PortfolioAccount,
    PortfolioCashLedger,
    PortfolioCorporateAction,
    PortfolioDailySnapshot,
    PortfolioFxRate,
    PortfolioPosition,
    PortfolioPositionLot,
    PortfolioTrade,
    PortfolioTradeSettlement,
    SettlementAlertStateRecord,
    SettlementOutcomeRecord,
    StockDaily,
    _LLM_PROMPT_CACHE_TELEMETRY_COLUMNS,
    _LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR,
    _LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS,
    _LLM_USAGE_INTEGER_TELEMETRY_COLUMNS,
    _LLM_USAGE_TELEMETRY_COLUMN_SQL,
    to_utc_naive_datetime,
    utc_naive_now,
)


class _DatabaseManagerMeta(type):
    """Serialize DatabaseManager construction across __new__ and __init__."""

    def __call__(cls, *args, **kwargs):
        with cls._init_lock:
            return super().__call__(*args, **kwargs)


class DatabaseManager(metaclass=_DatabaseManagerMeta):
    """
    数据库管理器 - 单例模式
    
    职责：
    1. 管理数据库连接池
    2. 提供 Session 上下文管理
    3. 封装数据存取操作
    """
    
    _instance: Optional['DatabaseManager'] = None
    _init_lock = threading.RLock()
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_url: Optional[str] = None):
        """
        初始化数据库管理器
        
        Args:
            db_url: 数据库连接 URL（可选，默认从配置读取）
        """
        if getattr(self, '_initialized', False):
            return

        created_engine = None

        try:
            config = get_config()
            if db_url is None:
                db_url = config.get_db_url()

            self._db_url = db_url
            self._sqlite_wal_enabled = config.sqlite_wal_enabled
            self._sqlite_busy_timeout_ms = config.sqlite_busy_timeout_ms
            self._sqlite_write_retry_max = config.sqlite_write_retry_max
            self._sqlite_write_retry_base_delay = config.sqlite_write_retry_base_delay
            self._postgres_write_retry_max = getattr(config, "postgres_write_retry_max", 2)
            self._postgres_write_retry_base_delay = getattr(
                config, "postgres_write_retry_base_delay", 0.2
            )

            self._runtime = build_database_runtime(db_url, config)
            created_engine = self._runtime.engine
            self._engine = created_engine
            self._is_sqlite_engine = self._runtime.is_sqlite
            self._sqlite_file_db = self._is_sqlite_engine and self._is_file_sqlite_database()
            self._install_sqlite_pragma_handler()

            self._SessionLocal = self._runtime.session_factory

            # Supabase production DDL is owned exclusively by reviewed migrations.
            if self._is_sqlite_engine:
                Base.metadata.create_all(self._engine)
                self._run_schema_migrations()

            self._initialized = True
            logger.info(
                "数据库初始化完成: backend=%s",
                self._engine.url.get_backend_name(),
            )

            # 注册退出钩子，确保程序退出时关闭数据库连接
            atexit.register(DatabaseManager._cleanup_engine, self._engine)
        except Exception:
            self._initialized = False
            try:
                if created_engine is not None:
                    created_engine.dispose()
            except Exception as cleanup_exc:
                logger.warning("数据库初始化失败后的引擎清理也失败: %s", cleanup_exc)
            self._engine = None
            self._SessionLocal = None
            self._runtime = None
            self.__class__._instance = None
            raise

    def _ensure_schema_migration_record(self) -> None:
        """Compatibility alias for callers that previously recorded one marker."""
        self._run_schema_migrations()

    def _run_schema_migrations(self) -> None:
        run_ordered_migrations(
            self._engine,
            migration_table=DatabaseSchemaMigration.__tablename__,
            migrations=ORDERED_SCHEMA_MIGRATIONS,
            context=self,
        )

    def _ensure_intelligence_items_unique_index(self, *, connection=None) -> None:
        if not self._is_sqlite_engine:
            return

        inspector_target = connection if connection is not None else self._engine
        if not inspect(inspector_target).has_table("intelligence_items"):
            return

        try:
            unique_indexes = self._list_sqlite_unique_indexes(
                "intelligence_items",
                connection=connection,
            )
        except Exception as exc:
            raise RuntimeError(
                "[Intelligence items] failed to inspect unique indexes; "
                "cannot safely apply the required migration"
            ) from exc

        target_columns = ("source_id", "url", "scope_type", "scope_value", "market")
        has_target_index = any(tuple(cols) == target_columns for cols in unique_indexes)
        has_legacy_url_unique = any(tuple(cols) == ("url",) for cols in unique_indexes)

        if has_target_index:
            return
        if unique_indexes and not has_legacy_url_unique:
            # Table has other unique index shapes; avoid aggressive changes and add
            # the expected scoped uniqueness directly.
            self._ensure_intelligence_items_scoped_unique_index_once(
                connection=connection
            )
            return

        self._rebuild_intelligence_items_table(connection=connection)

    def _rebuild_intelligence_items_table(self, *, connection=None) -> None:
        temporary_table = f"intelligence_items_recreate_tmp_{int(time.time() * 1_000_000_000)}"
        columns = [column.name for column in IntelligenceItem.__table__.columns]
        select_clause = ", ".join(f'"{column}"' for column in columns)
        scoped_index_columns = ", ".join(["source_id", "url", "scope_type", "scope_value", "market"])
        scoped_index_name = "uix_intel_item_scope"

        tmp_metadata = MetaData()
        tmp_table = Table(
            temporary_table,
            tmp_metadata,
            *(column.copy() for column in IntelligenceItem.__table__.columns),
        )
        logger.info("Rebuilding intelligence_items table to align composite uniqueness constraints.")
        owns_connection = connection is None
        connection_context = self._engine.begin() if owns_connection else nullcontext(connection)
        with connection_context as active_connection:
            active_connection.execute(text(f'DROP TABLE IF EXISTS "{temporary_table}"'))
            tmp_table.create(active_connection)
            active_connection.execute(
                text(
                    f"INSERT INTO \"{temporary_table}\" ({select_clause}) "
                    f"SELECT {select_clause} FROM intelligence_items"
                )
            )
            active_connection.execute(text('DROP TABLE "intelligence_items"'))
            active_connection.execute(
                text(f'ALTER TABLE "{temporary_table}" RENAME TO intelligence_items')
            )
            active_connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {scoped_index_name} ON "
                    f"intelligence_items ({scoped_index_columns})"
                )
            )

    def _ensure_intelligence_items_scoped_unique_index_once(self, *, connection=None) -> None:
        target_index_name = "uix_intel_item_scope"
        owns_connection = connection is None
        connection_context = self._engine.begin() if owns_connection else nullcontext(connection)
        with connection_context as active_connection:
            rows = active_connection.execute(
                text("PRAGMA index_list(intelligence_items)")
            ).fetchall()
            for row in rows:
                if row[1] == target_index_name:
                    return
            index_columns = ", ".join(["source_id", "url", "scope_type", "scope_value", "market"])
            active_connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {target_index_name} ON "
                    f"intelligence_items ({index_columns})"
                )
            )

    def _list_sqlite_unique_indexes(self, table_name: str, *, connection=None):
        owns_connection = connection is None
        connection_context = self._engine.connect() if owns_connection else nullcontext(connection)
        with connection_context as active_connection:
            rows = active_connection.execute(
                text(f"PRAGMA index_list({table_name})")
            ).fetchall()
            unique_indexes = []
            for row in rows:
                # row: (seq, name, unique, origin, partial)
                if int(row[2]) != 1:
                    continue
                index_name = row[1]
                index_columns = []
                for index_info in active_connection.execute(
                    text(f"PRAGMA index_xinfo({index_name})")
                ).fetchall():
                    # index_xinfo: (seqno, cid, name, desc, coll, key, ... )
                    column_name = index_info[2]
                    if column_name is None:
                        continue
                    index_columns.append(column_name)
                unique_indexes.append(index_columns)
            return unique_indexes

    def _ensure_llm_usage_telemetry_columns(self, *, connection=None) -> None:
        """Add nullable P0a usage telemetry columns to existing SQLite DBs."""
        if not self._is_sqlite_engine:
            return
        try:
            existing = {
                column["name"]
                for column in inspect(
                    connection if connection is not None else self._engine
                ).get_columns(LLMUsage.__tablename__)
            }
        except Exception as exc:
            raise RuntimeError(
                "[LLM usage] failed to inspect telemetry columns; "
                "cannot safely apply the required migration"
            ) from exc

        owns_connection = connection is None
        for column, column_type in _LLM_USAGE_TELEMETRY_COLUMN_SQL.items():
            if column in existing:
                continue
            for attempt in range(self._sqlite_write_retry_max + 1):
                connection_context = (
                    self._engine.begin()
                    if owns_connection
                    else nullcontext(connection)
                )
                try:
                    with connection_context as active_connection:
                        active_connection.exec_driver_sql(
                            f"ALTER TABLE {LLMUsage.__tablename__} "
                            f"ADD COLUMN {column} {column_type}"
                        )
                    existing.add(column)
                    break
                except OperationalError as exc:
                    if self._is_sqlite_duplicate_column_error(exc, column):
                        existing.add(column)
                        break
                    if (
                        self._is_sqlite_locked_error(exc)
                        and attempt < self._sqlite_write_retry_max
                    ):
                        delay = self._sqlite_write_retry_base_delay * (2 ** attempt)
                        logger.warning(
                            "SQLite schema lock conflict; retrying column backfill: "
                            "%s (%s/%s, %.2fs)",
                            column,
                            attempt + 1,
                            self._sqlite_write_retry_max,
                            delay,
                        )
                        if delay > 0:
                            time.sleep(delay)
                        continue
                    raise

    def _ensure_intelligence_item_scope_values(self, *, connection=None) -> None:
        """Backfill nullable intelligence item scopes so SQLite unique keys work."""
        if not self._is_sqlite_engine:
            return
        try:
            existing = {
                column["name"]
                for column in inspect(
                    connection if connection is not None else self._engine
                ).get_columns(IntelligenceItem.__tablename__)
            }
        except Exception as exc:
            raise RuntimeError("资讯池 scope_value 回填检查失败") from exc
        if "scope_value" not in existing:
            return
        owns_connection = connection is None
        connection_context = self._engine.begin() if owns_connection else nullcontext(connection)
        with connection_context as active_connection:
            active_connection.exec_driver_sql(
                    f"UPDATE {IntelligenceItem.__tablename__} "
                    "SET scope_value = ? "
                    "WHERE scope_value IS NULL OR scope_value = ''",
                    (INTELLIGENCE_ITEM_NULL_SCOPE_VALUE,),
                )

    def _ensure_portfolio_settlement_schema(self, *, connection=None) -> None:
        """Add PR 2 portfolio fields to an existing SQLite database."""
        if not self._is_sqlite_engine:
            return
        active_connection = connection
        if active_connection is None:
            with self._engine.begin() as owned_connection:
                self._ensure_portfolio_settlement_schema(connection=owned_connection)
            return

        PortfolioTradeSettlement.__table__.create(active_connection, checkfirst=True)
        additions = {
            PortfolioTrade.__tablename__: {
                "executed_at": "DATETIME",
            },
            PortfolioPosition.__tablename__: {
                "position_lifecycle": "VARCHAR(16) NOT NULL DEFAULT 'open'",
                "settlement_state": "VARCHAR(24) NOT NULL DEFAULT 'unknown'",
                "sellable_quantity": "FLOAT NOT NULL DEFAULT 0",
                "unsettled_quantity": "FLOAT NOT NULL DEFAULT 0",
                "next_sellable_at": "DATETIME",
                "settlement_calculation_status": "VARCHAR(16) NOT NULL DEFAULT 'unknown'",
            },
            PortfolioPositionLot.__tablename__: {
                "estimated_sellable_at": "DATETIME",
                "actual_sellable_at": "DATETIME",
                "settlement_state": "VARCHAR(24) NOT NULL DEFAULT 'unknown'",
                "calendar_status": "VARCHAR(16) NOT NULL DEFAULT 'unknown'",
            },
        }
        inspector = inspect(active_connection)
        for table_name, table_additions in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            for column_name, column_sql in table_additions.items():
                if column_name in existing:
                    continue
                active_connection.exec_driver_sql(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN "{column_name}" {column_sql}'
                )
                existing.add(column_name)

    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        """获取单例实例"""
        with cls._init_lock:
            if cls._instance is None:
                cls()
            return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        with cls._init_lock:
            if cls._instance is not None:
                if hasattr(cls._instance, '_engine') and cls._instance._engine is not None:
                    cls._instance.dispose()
                cls._instance._initialized = False
                cls._instance = None

    @classmethod
    def _cleanup_engine(cls, engine) -> None:
        """
        清理数据库引擎（atexit 钩子）

        确保程序退出时关闭所有数据库连接，避免 ResourceWarning

        Args:
            engine: SQLAlchemy 引擎对象
        """
        try:
            if engine is not None:
                engine.dispose()
                logger.debug("数据库引擎已清理")
        except Exception as e:
            logger.warning(f"清理数据库引擎时出错: {e}")

    def health_check(self) -> bool:
        """Verify database connectivity without exposing connection details."""
        if not getattr(self, "_runtime", None):
            raise RuntimeError("Database runtime is not initialized.")
        return self._runtime.health_check()

    def dispose(self) -> None:
        """Explicitly release every application-owned database connection."""
        if getattr(self, "_runtime", None):
            self._runtime.dispose()
        elif getattr(self, "_engine", None) is not None:
            self._engine.dispose()

    def _install_sqlite_pragma_handler(self) -> None:
        """为 SQLite 连接安装竞争保护参数。"""
        if not self._is_sqlite_engine:
            return

        @event.listens_for(self._engine, "connect")
        def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={int(self._sqlite_busy_timeout_ms)}")
                if self._sqlite_file_db and self._sqlite_wal_enabled:
                    cursor.execute("PRAGMA journal_mode=WAL")
            except Exception as exc:
                logger.warning("初始化 SQLite PRAGMA 失败: %s", exc)
            finally:
                cursor.close()

    def _is_file_sqlite_database(self) -> bool:
        database = (self._engine.url.database or "").strip()
        return bool(database) and database.lower() != ":memory:"

    def _run_write_transaction(
        self,
        operation_name: str,
        write_operation: Callable[[Session], T],
    ) -> T:
        max_retries = (
            self._sqlite_write_retry_max
            if self._is_sqlite_engine
            else self._postgres_write_retry_max
        )

        for attempt in range(max_retries + 1):
            session = self.get_session()
            try:
                if self._is_sqlite_engine:
                    # Acquire the SQLite writer lock before any reads inside
                    # `write_operation()` so pre-write existence checks and the
                    # later upsert share one consistent write window.
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                result = write_operation(session)
                session.commit()
                return result
            except DBAPIError as exc:
                session.rollback()
                retry_category = None
                retry_base_delay = 0.0
                if self._is_sqlite_engine and self._is_sqlite_locked_error(exc):
                    retry_category = "sqlite_lock"
                    retry_base_delay = self._sqlite_write_retry_base_delay
                elif not self._is_sqlite_engine and is_transient_postgres_error(exc):
                    retry_category = "postgres_transient"
                    retry_base_delay = self._postgres_write_retry_base_delay
                if retry_category and attempt < max_retries:
                    delay = retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "Retrying database write: operation=%s category=%s attempt=%s/%s delay=%.2fs",
                        operation_name,
                        retry_category,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    @property
    def is_sqlite(self) -> bool:
        """Expose the selected compatibility backend to repository adapters."""
        return self._is_sqlite_engine

    def run_write_transaction(
        self,
        operation_name: str,
        write_operation: Callable[[Session], T],
    ) -> T:
        """Run one short repository write with the backend retry policy."""
        return self._run_write_transaction(operation_name, write_operation)

    @staticmethod
    def _is_sqlite_locked_error(exc: BaseException) -> bool:
        err_text = str(getattr(exc, "orig", exc)).lower()
        return any(
            token in err_text
            for token in (
                "database is locked",
                "database schema is locked",
                "database table is locked",
            )
        )

    @staticmethod
    def _is_sqlite_duplicate_column_error(exc: OperationalError, column: str) -> bool:
        err_text = str(getattr(exc, "orig", exc)).lower()
        return "duplicate column name" in err_text and column.lower() in err_text

    @staticmethod
    def _normalize_daily_date(value: Any) -> Any:
        if isinstance(value, str):
            return datetime.strptime(value, '%Y-%m-%d').date()
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _normalize_sql_value(value: Any) -> Any:
        return None if pd.isna(value) else value
    
    def get_session(self) -> Session:
        """
        获取数据库 Session
        
        使用示例:
            with db.get_session() as session:
                # 执行查询
                session.commit()  # 如果需要
        """
        if not getattr(self, '_initialized', False) or not hasattr(self, '_SessionLocal'):
            raise RuntimeError(
                "DatabaseManager 未正确初始化。"
                "请确保通过 DatabaseManager.get_instance() 获取实例。"
            )
        session = self._SessionLocal()
        try:
            return session
        except Exception:
            session.close()
            raise

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def has_today_data(self, code: str, target_date: Optional[date] = None) -> bool:
        """
        检查是否已有指定日期的数据
        
        用于断点续传逻辑：如果已有数据则跳过网络请求
        
        Args:
            code: 股票代码
            target_date: 目标日期（默认今天）
            
        Returns:
            是否存在数据
        """
        if target_date is None:
            target_date = date.today()
        # 注意：这里的 target_date 语义是“自然日”，而不是“最新交易日”。
        # 在周末/节假日/非交易日运行时，即使数据库已有最新交易日数据，这里也会返回 False。
        # 该行为目前保留（按需求不改逻辑）。
        
        with self.get_session() as session:
            result = session.execute(
                select(StockDaily).where(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date == target_date
                    )
                )
            ).scalar_one_or_none()
            
            return result is not None
    
    def get_latest_data(
        self, 
        code: str, 
        days: int = 2
    ) -> List[StockDaily]:
        """
        获取最近 N 天的数据
        
        用于计算"相比昨日"的变化
        
        Args:
            code: 股票代码
            days: 获取天数
            
        Returns:
            StockDaily 对象列表（按日期降序）
        """
        with self.get_session() as session:
            results = session.execute(
                select(StockDaily)
                .where(StockDaily.code == code)
                .order_by(desc(StockDaily.date))
                .limit(days)
            ).scalars().all()
            
            return list(results)

    def save_news_intel(
        self,
        code: str,
        name: str,
        dimension: str,
        query: str,
        response: 'SearchResponse',
        query_context: Optional[Dict[str, str]] = None
    ) -> int:
        """
        保存新闻情报到数据库

        去重策略：
        - 优先按 URL 去重（唯一约束）
        - URL 缺失时按 title + source + published_date 进行软去重

        关联策略：
        - query_context 记录用户查询信息（平台、用户、会话、原始指令等）
        """
        if not response or not response.results:
            return 0

        query_ctx = query_context or {}
        current_query_id = (query_ctx.get("query_id") or "").strip()

        records_by_url: Dict[str, Dict[str, Any]] = {}
        for item in response.results:
            if (
                str(code or "").strip().upper().endswith(".VN")
                and getattr(item, "relevance_score", None) is not None
                and int(getattr(item, "relevance_score", 0) or 0) <= 0
            ):
                logger.debug(
                    "Skipped explicitly zero-relevance Vietnam news evidence: %s %s",
                    code,
                    (getattr(item, "title", "") or "")[:120],
                )
                continue
            title = (item.title or '').strip()
            url = (item.url or '').strip()
            source = (item.source or '').strip()
            snippet = (item.snippet or '').strip()
            published_date = self._parse_published_date(item.published_date)
            if not title and not url:
                continue
            url_key = url or self._build_fallback_url_key(
                code=code,
                title=title,
                source=source,
                published_date=published_date,
            )
            candidate = {
                "code": code,
                "name": name or None,
                "dimension": dimension or None,
                "query": query or None,
                "provider": response.provider or None,
                "title": title,
                "snippet": snippet or None,
                "url": url_key,
                "source": source or None,
                "published_date": published_date,
                "fetched_at": datetime.now(),
                "query_id": current_query_id or None,
                "query_source": query_ctx.get("query_source"),
                "requester_platform": query_ctx.get("requester_platform"),
                "requester_user_id": query_ctx.get("requester_user_id"),
                "requester_user_name": query_ctx.get("requester_user_name"),
                "requester_chat_id": query_ctx.get("requester_chat_id"),
                "requester_message_id": query_ctx.get("requester_message_id"),
                "requester_query": query_ctx.get("requester_query"),
            }
            previous = records_by_url.get(url_key)
            if previous is not None:
                # Match the old loop: title/code/url stay from the first item;
                # later non-empty mutable fields win.
                for field in (
                    "name", "dimension", "query", "provider", "snippet", "source",
                    "published_date", "query_source", "requester_platform",
                    "requester_user_id", "requester_user_name", "requester_chat_id",
                    "requester_message_id", "requester_query",
                ):
                    if candidate.get(field) is not None:
                        previous[field] = candidate[field]
                if previous.get("query_id") is None and candidate.get("query_id") is not None:
                    previous["query_id"] = candidate["query_id"]
                previous["fetched_at"] = candidate["fetched_at"]
            else:
                records_by_url[url_key] = candidate

        records = list(records_by_url.values())
        if not records:
            return 0

        def _write(session: Session) -> int:
            if not self._is_sqlite_engine:
                inserted_count = 0
                chunk_count = 0
                started_at = time.monotonic()
                for chunk in chunk_mappings(records):
                    stmt = postgres_insert(NewsIntel).values(chunk)
                    excluded = stmt.excluded
                    mutable_fields = (
                        "name", "dimension", "query", "provider", "snippet", "source",
                        "published_date", "query_id", "query_source", "requester_platform",
                        "requester_user_id", "requester_user_name", "requester_chat_id",
                        "requester_message_id", "requester_query",
                    )
                    updates = {
                        field: func.coalesce(getattr(excluded, field), getattr(NewsIntel, field))
                        for field in mutable_fields
                    }
                    updates["query_id"] = func.coalesce(NewsIntel.query_id, excluded.query_id)
                    updates["fetched_at"] = excluded.fetched_at
                    result = session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=["url"],
                            set_=updates,
                        ).returning(literal_column('(xmax = 0)').label('inserted'))
                    )
                    inserted_count += sum(bool(flag) for flag in result.scalars())
                    chunk_count += 1
                logger.info(
                    "Bulk write completed: operation=news_intel rows=%s chunks=%s duration_ms=%s",
                    len(records),
                    chunk_count,
                    int((time.monotonic() - started_at) * 1000),
                )
                return inserted_count

            local_saved_count = 0
            for values in records:
                url_key = values["url"]
                existing = session.execute(
                    select(NewsIntel).where(NewsIntel.url == url_key)
                ).scalar_one_or_none()

                if existing:
                    for field in (
                        "name", "dimension", "query", "provider", "snippet", "source",
                        "published_date", "query_source", "requester_platform",
                        "requester_user_id", "requester_user_name", "requester_chat_id",
                        "requester_message_id", "requester_query",
                    ):
                        setattr(existing, field, values.get(field) or getattr(existing, field))
                    if not existing.query_id and values.get("query_id"):
                        existing.query_id = values["query_id"]
                    existing.fetched_at = values["fetched_at"]
                    continue

                try:
                    with session.begin_nested():
                        record = NewsIntel(**values)
                        session.add(record)
                        session.flush()
                    local_saved_count += 1
                except IntegrityError:
                    logger.debug("新闻情报重复（已跳过）: %s %s", code, url_key)

            return local_saved_count

        saved_count = 0
        try:
            saved_count = self._run_write_transaction(
                f"save_news_intel[{code}]",
                _write,
            )
            logger.info(f"保存新闻情报成功: {code}, 新增 {saved_count} 条")
        except Exception as e:
            logger.error(f"保存新闻情报失败: {e}")
            raise

        return saved_count

    def save_fundamental_snapshot(
        self,
        query_id: str,
        code: str,
        payload: Optional[Dict[str, Any]],
        source_chain: Optional[Any] = None,
        coverage: Optional[Any] = None,
    ) -> int:
        """
        保存基本面快照（P0 write-only）。失败不抛异常，返回写入条数 0/1。
        """
        if not query_id or not code or payload is None:
            return 0

        try:
            def _write(session: Session) -> int:
                session.add(
                    FundamentalSnapshot(
                        query_id=query_id,
                        code=code,
                        payload=self._safe_json_dumps(payload),
                        source_chain=self._safe_json_dumps(source_chain or []),
                        coverage=self._safe_json_dumps(coverage or {}),
                    )
                )
                return 1
            return self._run_write_transaction(
                f"save_fundamental_snapshot[{query_id}:{code}]",
                _write,
            )
        except Exception as e:
            logger.debug(
                "基本面快照写入失败（fail-open）: query_id=%s code=%s err=%s",
                query_id,
                code,
                e,
            )
            return 0

    def get_latest_fundamental_snapshot(
        self,
        query_id: str,
        code: str,
    ) -> Optional[Dict[str, Any]]:
        """
        获取指定 query_id + code 的最新基本面快照 payload。

        读取失败或不存在时返回 None（fail-open）。
        """
        if not query_id or not code:
            return None

        with self.get_session() as session:
            try:
                row = session.execute(
                    select(FundamentalSnapshot)
                    .where(
                        and_(
                            FundamentalSnapshot.query_id == query_id,
                            FundamentalSnapshot.code == code,
                        )
                    )
                    .order_by(desc(FundamentalSnapshot.created_at))
                    .limit(1)
                ).scalar_one_or_none()
            except Exception as e:
                logger.debug(
                    "基本面快照读取失败（fail-open）: query_id=%s code=%s err=%s",
                    query_id,
                    code,
                    e,
                )
                return None

            if row is None:
                return None
            try:
                payload = json.loads(row.payload or "{}")
                return payload if isinstance(payload, dict) else None
            except Exception:
                return None

    def get_recent_fundamental_snapshots(
        self,
        code: str,
        *,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Return recent fundamental payloads for deterministic stale fallback."""
        normalized_code = str(code or "").strip()
        if not normalized_code:
            return []
        safe_limit = max(1, min(int(limit), 100))
        with self.get_session() as session:
            try:
                rows = session.execute(
                    select(FundamentalSnapshot)
                    .where(FundamentalSnapshot.code == normalized_code)
                    .order_by(
                        desc(FundamentalSnapshot.created_at),
                        desc(FundamentalSnapshot.id),
                    )
                    .limit(safe_limit)
                ).scalars().all()
            except Exception as exc:
                logger.debug(
                    "Recent fundamental snapshot read failed (fail-open): code=%s err=%s",
                    normalized_code,
                    exc,
                )
                return []

        snapshots: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row.payload or "{}")
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            snapshots.append({
                "query_id": row.query_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": payload,
            })
        return snapshots

    def get_recent_news(self, code: str, days: int = 7, limit: int = 20) -> List[NewsIntel]:
        """
        获取指定股票最近 N 天的新闻情报
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            results = session.execute(
                select(NewsIntel)
                .where(
                    and_(
                        NewsIntel.code == code,
                        NewsIntel.fetched_at >= cutoff_date
                    )
                )
                .order_by(desc(NewsIntel.fetched_at))
                .limit(limit)
            ).scalars().all()

            return list(results)

    def get_news_intel_by_query_id(self, query_id: str, limit: int = 20) -> List[NewsIntel]:
        """
        根据 query_id 获取新闻情报列表

        Args:
            query_id: 分析记录唯一标识
            limit: 返回数量限制

        Returns:
            NewsIntel 列表（按发布时间或抓取时间倒序）
        """
        from sqlalchemy import func

        with self.get_session() as session:
            results = session.execute(
                select(NewsIntel)
                .where(NewsIntel.query_id == query_id)
                .order_by(
                    desc(func.coalesce(NewsIntel.published_date, NewsIntel.fetched_at)),
                    desc(NewsIntel.fetched_at)
                )
                .limit(limit)
            ).scalars().all()

            return list(results)

    def save_analysis_history(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str],
        context_snapshot: Optional[Dict[str, Any]] = None,
        save_snapshot: bool = True
    ) -> int:
        """
        保存分析结果历史记录。

        Returns:
            新保存的 AnalysisHistory.id；保存失败返回 0。
        """
        if result is None:
            return 0

        sniper_points = self._extract_sniper_points(result)
        raw_result = self._build_raw_result(result)
        context_text = None
        if save_snapshot and context_snapshot is not None:
            context_text = self._safe_json_dumps(context_snapshot)

        try:
            def _write(session: Session) -> int:
                history = AnalysisHistory(
                    query_id=query_id,
                    code=result.code,
                    name=result.name,
                    report_type=report_type,
                    sentiment_score=result.sentiment_score,
                    operation_advice=result.operation_advice,
                    trend_prediction=result.trend_prediction,
                    analysis_summary=result.analysis_summary,
                    raw_result=self._safe_json_dumps(raw_result),
                    news_content=news_content,
                    context_snapshot=context_text,
                    ideal_buy=sniper_points.get("ideal_buy"),
                    secondary_buy=sniper_points.get("secondary_buy"),
                    stop_loss=sniper_points.get("stop_loss"),
                    take_profit=sniper_points.get("take_profit"),
                    created_at=datetime.now(),
                )
                session.add(history)
                session.flush()
                return int(history.id or 0)
            return self._run_write_transaction(
                f"save_analysis_history[{result.code}]",
                _write,
            )
        except Exception as e:
            logger.error(f"保存分析历史失败: {e}")
            return 0

    def update_analysis_history_diagnostics(
        self,
        *,
        query_id: str,
        code: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        notification_runs: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        更新已保存分析历史的运行诊断快照。

        通知结果通常在分析历史落库后才产生，因此这里仅补写
        context_snapshot.diagnostics，不改变报告正文或其它历史字段。
        """
        if not query_id or (diagnostics is None and not notification_runs):
            return 0

        try:
            def _write(session: Session) -> int:
                conditions = [AnalysisHistory.query_id == query_id]
                if code:
                    conditions.append(AnalysisHistory.code == code)

                row = session.execute(
                    select(AnalysisHistory)
                    .where(and_(*conditions))
                    .order_by(desc(AnalysisHistory.created_at))
                    .limit(1)
                ).scalars().first()
                if row is None:
                    return 0

                context_snapshot: Dict[str, Any] = {}
                if row.context_snapshot:
                    try:
                        parsed = json.loads(row.context_snapshot)
                        if isinstance(parsed, dict):
                            context_snapshot = parsed
                    except Exception:
                        context_snapshot = {}

                if diagnostics is not None:
                    context_snapshot["diagnostics"] = diagnostics
                else:
                    existing_diagnostics = context_snapshot.get("diagnostics")
                    if not isinstance(existing_diagnostics, dict):
                        existing_diagnostics = {
                            "query_id": query_id,
                            "stock_code": code,
                            "notification_runs": [],
                        }
                    runs = existing_diagnostics.get("notification_runs")
                    if not isinstance(runs, list):
                        runs = []
                    trace_id = existing_diagnostics.get("trace_id")
                    for run in notification_runs or []:
                        if isinstance(run, dict):
                            run_payload = dict(run)
                            if trace_id and not run_payload.get("trace_id"):
                                run_payload["trace_id"] = trace_id
                            runs.append(run_payload)
                    existing_diagnostics["notification_runs"] = runs
                    context_snapshot["diagnostics"] = existing_diagnostics
                row.context_snapshot = self._safe_json_dumps(context_snapshot)
                return 1

            return self._run_write_transaction(
                f"update_analysis_history_diagnostics[{query_id}:{code or '*'}]",
                _write,
            )
        except Exception as e:
            logger.warning(
                "更新分析历史诊断快照失败（fail-open）: query_id=%s code=%s err=%s",
                query_id,
                code,
                e,
            )
            return 0

    def get_analysis_history(
        self,
        code: Optional[str] = None,
        query_id: Optional[str] = None,
        days: int = 30,
        limit: int = 50,
        exclude_query_id: Optional[str] = None,
    ) -> List[AnalysisHistory]:
        """
        Query analysis history records.

        Notes:
        - If query_id is provided, perform exact lookup and ignore days window.
        - If query_id is not provided, apply days-based time filtering.
        - exclude_query_id: exclude records with this query_id (for history comparison).
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            conditions = []

            if query_id:
                conditions.append(AnalysisHistory.query_id == query_id)
            else:
                conditions.append(AnalysisHistory.created_at >= cutoff_date)

            if code:
                conditions.append(AnalysisHistory.code == code)

            # exclude_query_id only applies when not doing exact lookup (query_id is None)
            if exclude_query_id and not query_id:
                conditions.append(AnalysisHistory.query_id != exclude_query_id)

            results = session.execute(
                select(AnalysisHistory)
                .where(and_(*conditions))
                .order_by(desc(AnalysisHistory.created_at))
                .limit(limit)
            ).scalars().all()

            return list(results)

    def get_latest_analysis_history_id(
        self,
        *,
        query_id: str,
        code: str,
        report_type: str,
    ) -> Optional[int]:
        """Return the latest matching history id for read-only lookups.

        P2 automatic DecisionSignal extraction receives the freshly saved id
        directly from ``save_analysis_history()`` and does not use this helper.
        """

        if not query_id or not code or not report_type:
            return None

        with self.get_session() as session:
            return session.execute(
                select(AnalysisHistory.id)
                .where(
                    AnalysisHistory.query_id == query_id,
                    AnalysisHistory.code == code,
                    AnalysisHistory.report_type == report_type,
                )
                .order_by(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id))
                .limit(1)
            ).scalar_one_or_none()
    
    def get_analysis_history_paginated(
        self,
        code: Optional[Union[str, List[str]]] = None,
        report_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Tuple[List[AnalysisHistory], int]:
        """
        分页查询分析历史记录（带总数）
        
        Args:
            code: 股票代码筛选
            report_type: 报告类型筛选
            start_date: 开始日期（含）
            end_date: 结束日期（含）
            offset: 偏移量（跳过前 N 条）
            limit: 每页数量
            
        Returns:
            Tuple[List[AnalysisHistory], int]: (记录列表, 总数)
        """
        from sqlalchemy import func
        
        with self.get_session() as session:
            conditions = []
            
            if code:
                if isinstance(code, list):
                    codes = [c for c in code if c]
                    if codes:
                        conditions.append(AnalysisHistory.code.in_(codes))
                else:
                    conditions.append(AnalysisHistory.code == code)
            if report_type:
                conditions.append(AnalysisHistory.report_type == report_type)
            if start_date:
                # created_at >= start_date 00:00:00
                conditions.append(AnalysisHistory.created_at >= datetime.combine(start_date, datetime.min.time()))
            if end_date:
                # created_at < end_date+1 00:00:00 (即 <= end_date 23:59:59)
                conditions.append(AnalysisHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
            
            # 构建 where 子句
            where_clause = and_(*conditions) if conditions else True
            
            # 查询总数
            total_query = select(func.count(AnalysisHistory.id)).where(where_clause)
            total = session.execute(total_query).scalar() or 0
            
            # 查询分页数据
            data_query = (
                select(AnalysisHistory)
                .where(where_clause)
                .order_by(desc(AnalysisHistory.created_at))
                .offset(offset)
                .limit(limit)
            )
            results = session.execute(data_query).scalars().all()
            
            return list(results), total
    
    def get_analysis_history_by_id(self, record_id: int) -> Optional[AnalysisHistory]:
        """
        根据数据库主键 ID 查询单条分析历史记录
        
        由于 query_id 可能重复（批量分析时多条记录共享同一 query_id），
        使用主键 ID 确保精确查询唯一记录。
        
        Args:
            record_id: 分析历史记录的主键 ID
            
        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        with self.get_session() as session:
            result = session.execute(
                select(AnalysisHistory).where(AnalysisHistory.id == record_id)
            ).scalars().first()
            return result

    def delete_analysis_history_records(self, record_ids: List[int]) -> int:
        """
        删除指定的分析历史记录。

        同时清理依赖这些历史记录的回测结果和分析来源决策信号，避免
        依赖历史记录的派生数据残留。DecisionSignal 的 source_report_id
        允许弱引用，因此这里只清理 source_type=analysis 的真实历史绑定信号。

        Args:
            record_ids: 要删除的历史记录主键 ID 列表

        Returns:
            实际删除的历史记录数量
        """
        ids = sorted({int(record_id) for record_id in record_ids if record_id is not None})
        if not ids:
            return 0

        with self.session_scope() as session:
            existing_ids = sorted(
                session.execute(
                    select(AnalysisHistory.id).where(AnalysisHistory.id.in_(ids))
                ).scalars().all()
            )
            if not existing_ids:
                return 0

            linked_signal_ids = sorted(
                session.execute(
                    select(DecisionSignalRecord.id).where(
                        and_(
                            DecisionSignalRecord.source_type == "analysis",
                            DecisionSignalRecord.source_report_id.in_(existing_ids),
                        )
                    )
                ).scalars().all()
            )
            if linked_signal_ids:
                session.execute(
                    delete(DecisionSignalOutcomeRecord).where(
                        DecisionSignalOutcomeRecord.signal_id.in_(linked_signal_ids)
                    )
                )
                session.execute(
                    delete(DecisionSignalFeedbackRecord).where(
                        DecisionSignalFeedbackRecord.signal_id.in_(linked_signal_ids)
                    )
                )
                session.execute(
                    delete(DecisionSignalRecord).where(DecisionSignalRecord.id.in_(linked_signal_ids))
                )
            session.execute(
                delete(BacktestResult).where(BacktestResult.analysis_history_id.in_(existing_ids))
            )
            result = session.execute(
                delete(AnalysisHistory).where(AnalysisHistory.id.in_(existing_ids))
            )
            return result.rowcount or 0

    def get_distinct_stocks_from_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 200,
        include_market_review: bool = False,
    ) -> List[AnalysisHistory]:
        """
        获取历史记录中的不重复股票列表，每只股票取最新一条记录。

        使用子查询按 code 分组取 MAX(id)，再 JOIN 回查完整记录。
        默认排除大盘复盘，避免混入普通个股栏。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            limit: 最大返回数量
            include_market_review: 是否包含大盘复盘记录

        Returns:
            每条股票最新一条 AnalysisHistory 记录列表
        """
        with self.get_session() as session:
            subq = (
                select(
                    AnalysisHistory.code,
                    func.max(AnalysisHistory.id).label("max_id"),
                )
            )
            if start_date:
                subq = subq.where(
                    AnalysisHistory.created_at >= datetime.combine(start_date, datetime.min.time())
                )
            if end_date:
                subq = subq.where(
                    AnalysisHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
                )
            if not include_market_review:
                subq = subq.where(
                    and_(
                        AnalysisHistory.code != "MARKET",
                        or_(
                            AnalysisHistory.report_type.is_(None),
                            AnalysisHistory.report_type != "market_review",
                        ),
                    )
                )
            subq = subq.group_by(AnalysisHistory.code).subquery()

            results = (
                session.execute(
                    select(AnalysisHistory)
                    .join(subq, AnalysisHistory.id == subq.c.max_id)
                    .order_by(
                        desc(AnalysisHistory.created_at),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return list(results)

    def get_latest_analysis_by_query_id(
        self,
        query_id: str,
        *,
        code: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> Optional[AnalysisHistory]:
        """
        根据 query_id 查询最新一条分析历史记录

        query_id 在批量分析时可能重复，故返回最近创建的一条。

        Args:
            query_id: 分析记录关联的 query_id
            code: 可选股票代码过滤，用于区分同一 query_id 下的 MARKET 与个股记录
            report_type: 可选报告类型过滤

        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        with self.get_session() as session:
            conditions = [AnalysisHistory.query_id == query_id]
            if code:
                conditions.append(AnalysisHistory.code == code)
            if report_type:
                conditions.append(AnalysisHistory.report_type == report_type)

            result = session.execute(
                select(AnalysisHistory)
                .where(and_(*conditions))
                .order_by(desc(AnalysisHistory.created_at))
                .limit(1)
            ).scalars().first()
            return result
    
    def get_data_range(
        self, 
        code: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockDaily]:
        """
        获取指定日期范围的数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            StockDaily 对象列表
        """
        with self.get_session() as session:
            results = session.execute(
                select(StockDaily)
                .where(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date >= start_date,
                        StockDaily.date <= end_date
                    )
                )
                .order_by(StockDaily.date)
            ).scalars().all()
            
            return list(results)
    
    def save_daily_data(
        self, 
        df: pd.DataFrame, 
        code: str,
        data_source: str = "Unknown"
    ) -> int:
        """
        保存日线数据到数据库
        
        策略：
        - 按 `(code, date)` 做批量 UPSERT，已存在记录会覆盖更新
        - 同一批次内若存在重复日期，以最后一条记录为准
        - SQLite 分支按 chunk 写入以避免绑定参数上限
        
        Args:
            df: 包含日线数据的 DataFrame
            code: 股票代码
            data_source: 数据来源名称
            
        Returns:
            本次实际新增的记录数（不含更新）
        """
        if df is None or df.empty:
            logger.warning(f"保存数据为空，跳过 {code}")
            return 0

        now = datetime.now()
        records_by_date: Dict[date, Dict[str, Any]] = {}
        for row in df.to_dict(orient='records'):
            row_date = self._normalize_daily_date(row.get('date'))
            records_by_date[row_date] = {
                'code': code,
                'date': row_date,
                'open': self._normalize_sql_value(row.get('open')),
                'high': self._normalize_sql_value(row.get('high')),
                'low': self._normalize_sql_value(row.get('low')),
                'close': self._normalize_sql_value(row.get('close')),
                'volume': self._normalize_sql_value(row.get('volume')),
                'amount': self._normalize_sql_value(row.get('amount')),
                'pct_chg': self._normalize_sql_value(row.get('pct_chg')),
                'ma5': self._normalize_sql_value(row.get('ma5')),
                'ma10': self._normalize_sql_value(row.get('ma10')),
                'ma20': self._normalize_sql_value(row.get('ma20')),
                'volume_ratio': self._normalize_sql_value(row.get('volume_ratio')),
                'data_source': data_source,
                'created_at': now,
                'updated_at': now,
            }

        if not records_by_date:
            return 0

        records = list(records_by_date.values())
        batch_dates = list(records_by_date.keys())

        def _write(session: Session) -> int:
            if self._is_sqlite_engine:
                # SQLite has a per-statement bind-parameter limit (commonly 999).
                # Each record has ~15 columns, so chunk upserts to stay within bounds.
                _SQLITE_CHUNK = 50
                # `_run_write_transaction()` opens SQLite writes with
                # `BEGIN IMMEDIATE`, so existence checks and upsert execute
                # within one stable write window.
                existing_dates = set()
                _COUNT_CHUNK = 500
                for j in range(0, len(batch_dates), _COUNT_CHUNK):
                    chunk_dates = batch_dates[j : j + _COUNT_CHUNK]
                    if not chunk_dates:
                        continue
                    existing_dates.update(
                        session.execute(
                            select(StockDaily.date).where(
                                and_(
                                    StockDaily.code == code,
                                    StockDaily.date.in_(chunk_dates),
                                )
                            )
                        ).scalars().all()
                    )
                new_records = [
                    record for record in records if record['date'] not in existing_dates
                ]
                for i in range(0, len(records), _SQLITE_CHUNK):
                    chunk = records[i : i + _SQLITE_CHUNK]
                    stmt = sqlite_insert(StockDaily).values(chunk)
                    excluded = stmt.excluded
                    session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=['code', 'date'],
                            set_={
                                'open': excluded.open,
                                'high': excluded.high,
                                'low': excluded.low,
                                'close': excluded.close,
                                'volume': excluded.volume,
                                'amount': excluded.amount,
                                'pct_chg': excluded.pct_chg,
                                'ma5': excluded.ma5,
                                'ma10': excluded.ma10,
                                'ma20': excluded.ma20,
                                'volume_ratio': excluded.volume_ratio,
                                'data_source': excluded.data_source,
                                'updated_at': excluded.updated_at,
                            },
                        )
                    )
                return len(new_records)
            else:
                # Keep the historical batched existence read for contract and
                # statement-count observability. PostgreSQL's system-column flag
                # below is the concurrency-safe source of the inserted count.
                session.execute(
                    select(StockDaily.date).where(
                        and_(
                            StockDaily.code == code,
                            StockDaily.date.in_(batch_dates),
                        )
                    )
                ).scalars().all()
                inserted_count = 0
                chunk_count = 0
                started_at = time.monotonic()
                for chunk in chunk_mappings(records):
                    stmt = postgres_insert(StockDaily).values(chunk)
                    excluded = stmt.excluded
                    result = session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=['code', 'date'],
                            set_={
                                'open': excluded.open,
                                'high': excluded.high,
                                'low': excluded.low,
                                'close': excluded.close,
                                'volume': excluded.volume,
                                'amount': excluded.amount,
                                'pct_chg': excluded.pct_chg,
                                'ma5': excluded.ma5,
                                'ma10': excluded.ma10,
                                'ma20': excluded.ma20,
                                'volume_ratio': excluded.volume_ratio,
                                'data_source': excluded.data_source,
                                'updated_at': excluded.updated_at,
                            },
                        ).returning(literal_column('(xmax = 0)').label('inserted'))
                    )
                    inserted_count += sum(bool(flag) for flag in result.scalars())
                    chunk_count += 1
                logger.info(
                    "Bulk write completed: operation=stock_daily rows=%s chunks=%s duration_ms=%s",
                    len(records),
                    chunk_count,
                    int((time.monotonic() - started_at) * 1000),
                )
                return inserted_count

        try:
            saved_count = self._run_write_transaction(
                f"save_daily_data[{code}]",
                _write,
            )
            logger.info(f"保存 {code} 数据成功，新增 {saved_count} 条")
            return saved_count
        except Exception as e:
            logger.error(f"保存 {code} 数据失败: {e}")
            raise
    
    def get_analysis_context(
        self, 
        code: str,
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取分析所需的上下文数据
        
        返回今日数据 + 昨日数据的对比信息
        
        Args:
            code: 股票代码
            target_date: 目标日期（默认今天）
            
        Returns:
            包含今日数据、昨日对比等信息的字典
        """
        if target_date is None:
            target_date = date.today()
        # 注意：尽管入参提供了 target_date，但当前实现实际使用的是“最新两天数据”（get_latest_data），
        # 并不会按 target_date 精确取当日/前一交易日的上下文。
        # 因此若未来需要支持“按历史某天复盘/重算”的可解释性，这里需要调整。
        # 该行为目前保留（按需求不改逻辑）。
        
        # 获取最近2天数据
        recent_data = self.get_latest_data(code, days=2)
        
        if not recent_data:
            logger.warning(f"未找到 {code} 的数据")
            return None
        
        today_data = recent_data[0]
        yesterday_data = recent_data[1] if len(recent_data) > 1 else None
        
        context = {
            'code': code,
            'date': today_data.date.isoformat(),
            'today': today_data.to_dict(),
        }
        
        if yesterday_data:
            context['yesterday'] = yesterday_data.to_dict()
            
            # 计算相比昨日的变化
            if yesterday_data.volume and yesterday_data.volume > 0:
                context['volume_change_ratio'] = round(
                    today_data.volume / yesterday_data.volume, 2
                )
            
            if yesterday_data.close and yesterday_data.close > 0:
                context['price_change_ratio'] = round(
                    (today_data.close - yesterday_data.close) / yesterday_data.close * 100, 2
                )
            
            # 均线形态判断
            context['ma_status'] = self._analyze_ma_status(today_data)
        
        return context
    
    def _analyze_ma_status(self, data: StockDaily) -> str:
        """
        分析均线形态
        
        判断条件：
        - 多头排列：close > ma5 > ma10 > ma20
        - 空头排列：close < ma5 < ma10 < ma20
        - 震荡整理：其他情况
        """
        # 注意：这里的均线形态判断基于“close/ma5/ma10/ma20”静态比较，
        # 未考虑均线拐点、斜率、或不同数据源复权口径差异。
        # 该行为目前保留（按需求不改逻辑）。
        close = data.close or 0
        ma5 = data.ma5 or 0
        ma10 = data.ma10 or 0
        ma20 = data.ma20 or 0
        
        if close > ma5 > ma10 > ma20 > 0:
            return "多头排列 📈"
        elif close < ma5 < ma10 < ma20 and ma20 > 0:
            return "空头排列 📉"
        elif close > ma5 and ma5 > ma10:
            return "短期向好 🔼"
        elif close < ma5 and ma5 < ma10:
            return "短期走弱 🔽"
        else:
            return "震荡整理 ↔️"

    @staticmethod
    def _parse_published_date(value: Optional[str]) -> Optional[datetime]:
        """
        解析发布时间字符串（失败返回 None）
        """
        if not value:
            return None

        if isinstance(value, datetime):
            return value

        text = str(value).strip()
        if not text:
            return None

        # 优先尝试 ISO 格式
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _safe_json_dumps(data: Any) -> str:
        """
        安全序列化为 JSON 字符串
        """
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return json.dumps(str(data), ensure_ascii=False)

    @staticmethod
    def _build_raw_result(result: Any) -> Dict[str, Any]:
        """
        生成完整分析结果字典
        """
        data = result.to_dict() if hasattr(result, "to_dict") else {}
        data.update({
            'data_sources': getattr(result, 'data_sources', ''),
            'raw_response': getattr(result, 'raw_response', None),
        })
        return data

    @staticmethod
    def _parse_sniper_value(value: Any) -> Optional[float]:
        return parse_sniper_value(value)

    def _extract_sniper_points(self, result: Any) -> Dict[str, Optional[float]]:
        """Extract normalized sniper point values from an AnalysisResult."""

        return extract_sniper_points(result)

    @staticmethod
    def _build_fallback_url_key(
        code: str,
        title: str,
        source: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        生成无 URL 时的去重键（确保稳定且较短）
        """
        date_str = published_date.isoformat() if published_date else ""
        raw_key = f"{code}|{title}|{source}|{date_str}"
        digest = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
        return f"no-url:{code}:{digest}"

    def save_conversation_message(self, session_id: str, role: str, content: str) -> int:
        """
        保存 Agent 对话消息
        """
        with self.session_scope() as session:
            msg = ConversationMessage(
                session_id=session_id,
                role=role,
                content=content
            )
            session.add(msg)
            session.flush()
            return int(msg.id)

    def get_conversation_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取 Agent 对话历史
        """
        with self.session_scope() as session:
            stmt = select(ConversationMessage).filter(
                ConversationMessage.session_id == session_id
            ).order_by(ConversationMessage.created_at.desc()).limit(limit)
            messages = session.execute(stmt).scalars().all()

            # 倒序返回，保证时间顺序
            return [{"role": msg.role, "content": msg.content} for msg in reversed(messages)]

    def get_visible_conversation_messages(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return visible user/assistant conversation messages in chronological order."""
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage)
                .where(
                    and_(
                        ConversationMessage.session_id == session_id,
                        ConversationMessage.role.in_(["user", "assistant"]),
                    )
                )
                .order_by(ConversationMessage.created_at, ConversationMessage.id)
            )
            if limit is not None:
                stmt = (
                    stmt.order_by(None)
                    .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
                    .limit(limit)
                )
            messages = session.execute(stmt).scalars().all()
            if limit is not None:
                messages = list(reversed(messages))
            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at,
                }
                for msg in messages
                if msg.content
            ]

    def get_conversation_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return the rolling summary for a conversation session, if present."""
        with self.session_scope() as session:
            stmt = select(ConversationSummary).where(
                ConversationSummary.session_id == session_id
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": row.id,
                "session_id": row.session_id,
                "summary": row.summary,
                "covered_message_id": row.covered_message_id,
                "source_message_count": row.source_message_count,
                "estimated_tokens": row.estimated_tokens,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_agent_provider_turn(
        self,
        *,
        session_id: str,
        run_id: str,
        provider: str,
        model: str,
        anchor_user_message_id: int,
        anchor_assistant_message_id: int,
        messages: List[Dict[str, Any]],
        contains_reasoning: bool,
        contains_tool_calls: bool,
        contains_thinking_blocks: bool,
        must_roundtrip: bool,
        estimated_tokens: int,
    ) -> int:
        """Persist one provider protocol trace and enforce per-model retention."""
        with self.session_scope() as session:
            row = AgentProviderTurn(
                session_id=session_id,
                run_id=run_id,
                provider=provider,
                model=model,
                anchor_user_message_id=int(anchor_user_message_id or 0),
                anchor_assistant_message_id=int(anchor_assistant_message_id or 0),
                messages_json=json.dumps(messages or [], ensure_ascii=False, default=str),
                contains_reasoning=bool(contains_reasoning),
                contains_tool_calls=bool(contains_tool_calls),
                contains_thinking_blocks=bool(contains_thinking_blocks),
                must_roundtrip=bool(must_roundtrip),
                estimated_tokens=int(estimated_tokens or 0),
            )
            session.add(row)
            session.flush()
            row_id = int(row.id)
            if row.must_roundtrip:
                self._trim_agent_provider_turns(
                    session=session,
                    session_id=session_id,
                    provider=provider,
                    model=model,
                    keep=PROVIDER_TRACE_RETENTION_LIMIT,
                )
            return row_id

    def get_agent_provider_turns(
        self,
        session_id: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        must_roundtrip_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return provider trace turns in chronological order."""
        with self.session_scope() as session:
            conditions = [AgentProviderTurn.session_id == session_id]
            if provider:
                conditions.append(AgentProviderTurn.provider == provider)
            if model:
                conditions.append(AgentProviderTurn.model == model)
            if must_roundtrip_only:
                conditions.append(AgentProviderTurn.must_roundtrip.is_(True))
            stmt = (
                select(AgentProviderTurn)
                .where(and_(*conditions))
                .order_by(AgentProviderTurn.created_at, AgentProviderTurn.id)
            )
            rows = session.execute(stmt).scalars().all()
            result = []
            for row in rows:
                try:
                    messages = json.loads(row.messages_json or "[]")
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Invalid provider trace messages_json skipped for session %s turn %s: %s",
                        row.session_id,
                        row.id,
                        exc,
                    )
                    messages = []
                result.append({
                    "id": row.id,
                    "session_id": row.session_id,
                    "run_id": row.run_id,
                    "provider": row.provider,
                    "model": row.model,
                    "anchor_user_message_id": row.anchor_user_message_id,
                    "anchor_assistant_message_id": row.anchor_assistant_message_id,
                    "messages": messages if isinstance(messages, list) else [],
                    "messages_json": row.messages_json,
                    "contains_reasoning": row.contains_reasoning,
                    "contains_tool_calls": row.contains_tool_calls,
                    "contains_thinking_blocks": row.contains_thinking_blocks,
                    "must_roundtrip": row.must_roundtrip,
                    "estimated_tokens": row.estimated_tokens,
                    "created_at": row.created_at,
                })
            return result

    def _trim_agent_provider_turns(
        self,
        *,
        session: Session,
        session_id: str,
        provider: str,
        model: str,
        keep: int,
    ) -> int:
        old_ids_stmt = (
            select(AgentProviderTurn.id)
            .where(
                and_(
                    AgentProviderTurn.session_id == session_id,
                    AgentProviderTurn.provider == provider,
                    AgentProviderTurn.model == model,
                    AgentProviderTurn.must_roundtrip.is_(True),
                )
            )
            .order_by(AgentProviderTurn.created_at.desc(), AgentProviderTurn.id.desc())
            .offset(max(0, int(keep)))
        )
        old_ids = list(session.execute(old_ids_stmt).scalars().all())
        if not old_ids:
            return 0
        result = session.execute(
            delete(AgentProviderTurn).where(AgentProviderTurn.id.in_(old_ids))
        )
        return int(result.rowcount or 0)

    def upsert_conversation_summary(
        self,
        session_id: str,
        summary: str,
        covered_message_id: int,
        source_message_count: int,
        estimated_tokens: int,
    ) -> None:
        """Create or update the rolling summary for a conversation session."""
        with self.session_scope() as session:
            now = datetime.now()
            values = {
                "session_id": session_id,
                "summary": summary,
                "covered_message_id": int(covered_message_id or 0),
                "source_message_count": int(source_message_count or 0),
                "estimated_tokens": int(estimated_tokens or 0),
                "updated_at": now,
            }
            stmt = sqlite_insert(ConversationSummary).values(**values)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["session_id"],
                    set_=values,
                )
            )

    def conversation_session_exists(self, session_id: str) -> bool:
        """Return True when at least one message exists for the given session."""
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage.id)
                .where(ConversationMessage.session_id == session_id)
                .limit(1)
            )
            return session.execute(stmt).scalar() is not None

    def get_chat_sessions(
        self,
        limit: int = 50,
        session_prefix: Optional[str] = None,
        extra_session_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取聊天会话列表（从 conversation_messages 聚合）

        Args:
            limit: Maximum number of sessions to return.
            session_prefix: If provided, only return sessions whose session_id
                starts with this prefix.  Used for per-user isolation (e.g.
                ``"telegram_12345"``).
            extra_session_ids: Optional exact session ids to include in
                addition to the scoped prefix.

        Returns:
            按最近活跃时间倒序的会话列表，每条包含 session_id, title, message_count, last_active
        """
        from sqlalchemy import func

        with self.session_scope() as session:
            normalized_prefix = None
            if session_prefix:
                normalized_prefix = session_prefix if session_prefix.endswith(":") else f"{session_prefix}:"
            exact_ids = [sid for sid in (extra_session_ids or []) if sid]

            # 聚合每个 session 的消息数和最后活跃时间
            base = (
                select(
                    ConversationMessage.session_id,
                    func.count(ConversationMessage.id).label("message_count"),
                    func.min(ConversationMessage.created_at).label("created_at"),
                    func.max(ConversationMessage.created_at).label("last_active"),
                )
            )
            conditions = []
            if normalized_prefix:
                conditions.append(ConversationMessage.session_id.startswith(normalized_prefix))
            if exact_ids:
                conditions.append(ConversationMessage.session_id.in_(exact_ids))
            if conditions:
                base = base.where(or_(*conditions))
            stmt = (
                base
                .group_by(ConversationMessage.session_id)
                .order_by(desc(func.max(ConversationMessage.created_at)))
                .limit(limit)
            )
            rows = session.execute(stmt).all()

            results = []
            for row in rows:
                sid = row.session_id
                # 取该会话第一条 user 消息作为标题
                first_user_msg = session.execute(
                    select(ConversationMessage.content)
                    .where(
                        and_(
                            ConversationMessage.session_id == sid,
                            ConversationMessage.role == "user",
                        )
                    )
                    .order_by(ConversationMessage.created_at)
                    .limit(1)
                ).scalar()
                title = (first_user_msg or "新对话")[:60]

                results.append({
                    "session_id": sid,
                    "title": title,
                    "message_count": row.message_count,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_active": row.last_active.isoformat() if row.last_active else None,
                })
            return results

    def get_conversation_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取单个会话的完整消息列表（用于前端恢复历史）
        """
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.created_at)
                .limit(limit)
            )
            messages = session.execute(stmt).scalars().all()
            return [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ]

    def delete_conversation_session(self, session_id: str) -> int:
        """
        删除指定会话的所有消息

        Returns:
            删除的消息数
        """
        with self.session_scope() as session:
            session.execute(
                delete(AgentProviderTurn).where(
                    AgentProviderTurn.session_id == session_id
                )
            )
            session.execute(
                delete(ConversationSummary).where(
                    ConversationSummary.session_id == session_id
                )
            )
            result = session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.session_id == session_id
                )
            )
            return result.rowcount

    # ------------------------------------------------------------------
    # LLM usage tracking
    # ------------------------------------------------------------------

    def record_llm_usage(
        self,
        call_type: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        stock_code: Optional[str] = None,
        **telemetry: Any,
    ) -> None:
        """Append one LLM call record to llm_usage."""
        row_values: Dict[str, Any] = {
            "call_type": call_type,
            "model": model or "unknown",
            "stock_code": stock_code,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        for column in _LLM_USAGE_TELEMETRY_COLUMN_SQL:
            row_values[column] = None if column in _LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS else telemetry.get(column)
        row = LLMUsage(**row_values)
        with self.session_scope() as session:
            session.add(row)

    def get_llm_usage_summary(
        self,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Dict[str, Any]:
        """Return aggregated token usage between from_dt and to_dt.

        Returns a dict with keys:
          total_calls, total_prompt_tokens, total_completion_tokens, total_tokens,
          by_call_type: list of {call_type, calls, prompt_tokens,
            completion_tokens, total_tokens},
          by_model: list of {model, calls, prompt_tokens, completion_tokens,
            total_tokens, max_total_tokens}
        """
        with self.session_scope() as session:
            base_filter = and_(
                LLMUsage.called_at >= from_dt,
                LLMUsage.called_at <= to_dt,
            )

            # Overall totals
            totals = session.execute(
                select(
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                ).where(base_filter)
            ).one()

            # Breakdown by call_type
            by_type_rows = session.execute(
                select(
                    LLMUsage.call_type,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                )
                .where(base_filter)
                .group_by(LLMUsage.call_type)
                .order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()

            # Breakdown by model
            by_model_rows = session.execute(
                select(
                    LLMUsage.model,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.coalesce(func.max(LLMUsage.total_tokens), 0).label("max_total_tokens"),
                )
                .where(base_filter)
                .group_by(LLMUsage.model)
                .order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()

        return {
            "total_calls": totals.calls,
            "total_prompt_tokens": totals.prompt_tokens,
            "total_completion_tokens": totals.completion_tokens,
            "total_tokens": totals.tokens,
            "by_call_type": [
                {
                    "call_type": r.call_type,
                    "calls": r.calls,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.tokens,
                }
                for r in by_type_rows
            ],
            "by_model": [
                {
                    "model": r.model,
                    "calls": r.calls,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.tokens,
                    "max_total_tokens": r.max_total_tokens,
                }
                for r in by_model_rows
            ],
        }

    def get_llm_usage_records(
        self,
        from_dt: datetime,
        to_dt: datetime,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return recent LLM usage audit rows between from_dt and to_dt.

        Each row contains id, call_type, model, stock_code, prompt_tokens,
        completion_tokens, total_tokens, and called_at. Results are ordered by
        newest call first, and limit is clamped to the public API range.
        """
        normalized_limit = max(1, min(int(limit or 50), 200))
        with self.session_scope() as session:
            rows = session.execute(
                select(
                    LLMUsage.id,
                    LLMUsage.call_type,
                    LLMUsage.model,
                    LLMUsage.stock_code,
                    LLMUsage.prompt_tokens,
                    LLMUsage.completion_tokens,
                    LLMUsage.total_tokens,
                    LLMUsage.called_at,
                )
                .where(
                    and_(
                        LLMUsage.called_at >= from_dt,
                        LLMUsage.called_at <= to_dt,
                    )
                )
                .order_by(desc(LLMUsage.called_at), desc(LLMUsage.id))
                .limit(normalized_limit)
            ).all()

        return [
            {
                "id": r.id,
                "call_type": r.call_type,
                "model": r.model,
                "stock_code": r.stock_code,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "called_at": r.called_at,
            }
            for r in rows
        ]


# 便捷函数
def get_db() -> DatabaseManager:
    """获取数据库管理器实例的快捷方式"""
    return DatabaseManager.get_instance()


def persist_llm_usage(
    usage: Dict[str, Any],
    model: str,
    call_type: str,
    stock_code: Optional[str] = None,
) -> None:
    """Fire-and-forget: write one LLM call record to llm_usage. Never raises."""
    try:
        if usage is None:
            usage = {}
        prompt_cache_telemetry_disabled = bool(
            getattr(usage, _LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR, False)
        )
        prompt_tokens = _coerce_llm_usage_non_negative_int(usage.get("prompt_tokens")) or 0
        completion_tokens = _coerce_llm_usage_non_negative_int(usage.get("completion_tokens")) or 0
        total_tokens = _coerce_llm_usage_non_negative_int(usage.get("total_tokens")) or 0
        telemetry = {
            column: usage.get(column)
            for column in _LLM_USAGE_TELEMETRY_COLUMN_SQL
        }
        if prompt_cache_telemetry_disabled:
            for column in _LLM_PROMPT_CACHE_TELEMETRY_COLUMNS:
                telemetry[column] = None
        for column in _LLM_USAGE_INTEGER_TELEMETRY_COLUMNS:
            telemetry[column] = _coerce_llm_usage_non_negative_int(telemetry.get(column))
        telemetry["normalized_prompt_tokens"] = (
            telemetry.get("normalized_prompt_tokens")
            if telemetry.get("normalized_prompt_tokens") is not None
            else prompt_tokens
        )
        telemetry["normalized_completion_tokens"] = (
            telemetry.get("normalized_completion_tokens")
            if telemetry.get("normalized_completion_tokens") is not None
            else completion_tokens
        )
        telemetry["normalized_total_tokens"] = (
            telemetry.get("normalized_total_tokens")
            if telemetry.get("normalized_total_tokens") is not None
            else total_tokens
        )
        has_usage_payload = bool(usage.get("provider_usage_json")) or any(
            key in usage
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "normalized_prompt_tokens",
                "normalized_completion_tokens",
                "normalized_total_tokens",
            )
        )
        if not prompt_cache_telemetry_disabled:
            telemetry["cache_capability"] = usage.get("cache_capability") or "unknown"
            telemetry["cache_eligibility"] = usage.get("cache_eligibility") or "unknown"
            telemetry["cache_observation"] = usage.get("cache_observation") or (
                "no_usage" if not has_usage_payload else "unknown"
            )
        db = DatabaseManager.get_instance()
        db.record_llm_usage(
            call_type=call_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            stock_code=stock_code,
            **telemetry,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning("[LLM usage] failed to persist usage record: %s", exc)


def _coerce_llm_usage_non_negative_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value < 0 or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isdigit():
            return None
        return int(text)
    return None


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    db = get_db()
    
    print("=== 数据库测试 ===")
    print(f"数据库初始化成功")
    
    # 测试检查今日数据
    has_data = db.has_today_data('600519')
    print(f"茅台今日是否有数据: {has_data}")
    
    # 测试保存数据
    test_df = pd.DataFrame({
        'date': [date.today()],
        'open': [1800.0],
        'high': [1850.0],
        'low': [1780.0],
        'close': [1820.0],
        'volume': [10000000],
        'amount': [18200000000],
        'pct_chg': [1.5],
        'ma5': [1810.0],
        'ma10': [1800.0],
        'ma20': [1790.0],
        'volume_ratio': [1.2],
    })
    
    saved = db.save_daily_data(test_df, '600519', 'TestSource')
    print(f"保存测试数据: {saved} 条")
    
    # 测试获取上下文
    context = db.get_analysis_context('600519')
    print(f"分析上下文: {context}")
