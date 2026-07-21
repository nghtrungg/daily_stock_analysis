# -*- coding: utf-8 -*-
"""Repository for DecisionSignal feedback and forward outcomes."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from src.repositories.bulk import chunk_mappings

from src.storage import (
    DatabaseManager,
    DecisionSignalFeedbackRecord,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
    utc_naive_now,
)


logger = logging.getLogger(__name__)


class DecisionSignalOutcomeRepository:
    """DB access for signal-level outcome and feedback sidecar tables."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def list_candidate_signals(
        self,
        *,
        signal_id: Optional[int] = None,
        stock_codes: Optional[List[str]] = None,
        market: Optional[str] = None,
        action: Optional[str] = None,
        source_type: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[DecisionSignalRecord]:
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        conditions = []
        if signal_id is not None:
            conditions.append(DecisionSignalRecord.id == signal_id)
        if stock_codes:
            conditions.append(DecisionSignalRecord.stock_code.in_(stock_codes))
        if market:
            conditions.append(DecisionSignalRecord.market == market)
        if action:
            conditions.append(DecisionSignalRecord.action == action)
        if source_type:
            conditions.append(DecisionSignalRecord.source_type == source_type)
        if statuses:
            conditions.append(DecisionSignalRecord.status.in_(statuses))
        where_clause = and_(*conditions) if conditions else True
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalRecord)
                .where(where_clause)
                .order_by(desc(DecisionSignalRecord.created_at), desc(DecisionSignalRecord.id))
                .offset(safe_offset)
                .limit(safe_limit)
            ).scalars().all()
            return list(rows)

    def list_outcomes_for_signals(
        self,
        *,
        signal_ids: List[int],
        engine_version: str,
    ) -> List[DecisionSignalOutcomeRecord]:
        if not signal_ids:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalOutcomeRecord)
                .where(
                    DecisionSignalOutcomeRecord.signal_id.in_(signal_ids),
                    DecisionSignalOutcomeRecord.engine_version == engine_version,
                )
            ).scalars().all()
            return list(rows)

    def get_outcome(
        self,
        *,
        signal_id: int,
        horizon: str,
        engine_version: str,
    ) -> Optional[DecisionSignalOutcomeRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(DecisionSignalOutcomeRecord)
                .where(
                    DecisionSignalOutcomeRecord.signal_id == signal_id,
                    DecisionSignalOutcomeRecord.horizon == horizon,
                    DecisionSignalOutcomeRecord.engine_version == engine_version,
                )
                .limit(1)
            ).scalar_one_or_none()

    def upsert_outcome(self, fields: Dict[str, Any]) -> Tuple[DecisionSignalOutcomeRecord, bool]:
        return self.upsert_outcomes([fields])[0]

    def upsert_outcomes(
        self,
        fields_list: List[Dict[str, Any]],
    ) -> List[Tuple[DecisionSignalOutcomeRecord, bool]]:
        """Upsert one evaluated outcome batch while preserving input order."""
        if not fields_list:
            return []
        keys = [
            (fields["signal_id"], fields["horizon"], fields["engine_version"])
            for fields in fields_list
        ]
        now = utc_naive_now()

        if self.db.is_sqlite:
            results: List[Tuple[DecisionSignalOutcomeRecord, bool]] = []
            with self.db.get_session() as session:
                try:
                    for fields, key in zip(fields_list, keys):
                        existing = session.execute(
                            select(DecisionSignalOutcomeRecord).where(
                                DecisionSignalOutcomeRecord.signal_id == key[0],
                                DecisionSignalOutcomeRecord.horizon == key[1],
                                DecisionSignalOutcomeRecord.engine_version == key[2],
                            )
                        ).scalar_one_or_none()
                        if existing is None:
                            existing = DecisionSignalOutcomeRecord(**fields)
                            session.add(existing)
                            results.append((existing, True))
                        else:
                            for field, value in fields.items():
                                if field not in {"id", "created_at"}:
                                    setattr(existing, field, value)
                            existing.updated_at = now
                            results.append((existing, False))
                    session.commit()
                    for row, _created in results:
                        session.refresh(row)
                    return results
                except Exception:
                    session.rollback()
                    raise

        mappings_by_key: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for fields, key in zip(fields_list, keys):
            mapping = dict(fields)
            mapping.setdefault("created_at", now)
            mapping["updated_at"] = now
            mappings_by_key[key] = mapping
        mutable_fields = [
            column.name
            for column in DecisionSignalOutcomeRecord.__table__.columns
            if column.name not in {"id", "signal_id", "horizon", "engine_version", "created_at"}
        ]

        def _write(session: Any) -> Dict[Tuple[Any, ...], Tuple[DecisionSignalOutcomeRecord, bool]]:
            rows_by_key: Dict[
                Tuple[Any, ...], Tuple[DecisionSignalOutcomeRecord, bool]
            ] = {}
            chunk_count = 0
            started_at = time.monotonic()
            for chunk in chunk_mappings(mappings_by_key.values()):
                stmt = postgres_insert(DecisionSignalOutcomeRecord).values(chunk)
                excluded = stmt.excluded
                returned = session.execute(
                    stmt.on_conflict_do_update(
                        constraint="uix_decision_signal_outcome_key",
                        set_={field: getattr(excluded, field) for field in mutable_fields},
                    ).returning(
                        DecisionSignalOutcomeRecord,
                        literal_column("(xmax = 0)").label("inserted"),
                    )
                ).all()
                for row, inserted in returned:
                    row_key = (row.signal_id, row.horizon, row.engine_version)
                    rows_by_key[row_key] = (row, bool(inserted))
                chunk_count += 1
            logger.info(
                "Bulk write completed: operation=decision_signal_outcomes rows=%s chunks=%s duration_ms=%s",
                len(mappings_by_key),
                chunk_count,
                int((time.monotonic() - started_at) * 1000),
            )
            return rows_by_key

        rows_by_key = self.db.run_write_transaction(
            "upsert_decision_signal_outcomes", _write
        )
        return [rows_by_key[key] for key in keys]

    def list_outcomes(
        self,
        *,
        signal_id: Optional[int] = None,
        horizon: Optional[str] = None,
        engine_version: Optional[str] = None,
        eval_status: Optional[str] = None,
        outcome: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[DecisionSignalOutcomeRecord], int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 100))
        conditions = []
        if signal_id is not None:
            conditions.append(DecisionSignalOutcomeRecord.signal_id == signal_id)
        if horizon:
            conditions.append(DecisionSignalOutcomeRecord.horizon == horizon)
        if engine_version:
            conditions.append(DecisionSignalOutcomeRecord.engine_version == engine_version)
        if eval_status:
            conditions.append(DecisionSignalOutcomeRecord.eval_status == eval_status)
        if outcome:
            conditions.append(DecisionSignalOutcomeRecord.outcome == outcome)
        where_clause = and_(*conditions) if conditions else True
        offset = (safe_page - 1) * safe_page_size
        with self.db.get_session() as session:
            total = session.execute(
                select(func.count(DecisionSignalOutcomeRecord.id))
                .select_from(DecisionSignalOutcomeRecord)
                .where(where_clause)
            ).scalar() or 0
            rows = session.execute(
                select(DecisionSignalOutcomeRecord)
                .where(where_clause)
                .order_by(desc(DecisionSignalOutcomeRecord.updated_at), desc(DecisionSignalOutcomeRecord.id))
                .offset(offset)
                .limit(safe_page_size)
            ).scalars().all()
            return list(rows), int(total)

    def list_stats_rows(
        self,
        *,
        engine_version: str,
        horizons: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        action: Optional[str] = None,
        market: Optional[str] = None,
        market_phase: Optional[str] = None,
        source_type: Optional[str] = None,
        data_quality_level: Optional[str] = None,
        source_agent: Optional[str] = None,
    ) -> List[DecisionSignalOutcomeRecord]:
        conditions = [DecisionSignalOutcomeRecord.engine_version == engine_version]
        if horizons:
            conditions.append(DecisionSignalOutcomeRecord.horizon.in_(horizons))
        if statuses:
            conditions.append(DecisionSignalRecord.status.in_(statuses))
        if action:
            conditions.append(DecisionSignalOutcomeRecord.action == action)
        if market:
            conditions.append(DecisionSignalOutcomeRecord.market == market)
        if market_phase:
            conditions.append(DecisionSignalOutcomeRecord.market_phase == market_phase)
        if source_type:
            conditions.append(DecisionSignalOutcomeRecord.source_type == source_type)
        if data_quality_level:
            conditions.append(DecisionSignalOutcomeRecord.data_quality_level == data_quality_level)
        if source_agent:
            conditions.append(DecisionSignalOutcomeRecord.source_agent == source_agent)
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalOutcomeRecord)
                .join(DecisionSignalRecord, DecisionSignalRecord.id == DecisionSignalOutcomeRecord.signal_id)
                .where(and_(*conditions))
            ).scalars().all()
            return list(rows)

    def get_feedback(self, *, signal_id: int) -> Optional[DecisionSignalFeedbackRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(DecisionSignalFeedbackRecord)
                .where(DecisionSignalFeedbackRecord.signal_id == signal_id)
                .limit(1)
            ).scalar_one_or_none()

    def upsert_feedback(self, fields: Dict[str, Any]) -> DecisionSignalFeedbackRecord:
        now = utc_naive_now()
        with self.db.get_session() as session:
            existing = session.execute(
                select(DecisionSignalFeedbackRecord)
                .where(DecisionSignalFeedbackRecord.signal_id == fields["signal_id"])
                .limit(1)
            ).scalar_one_or_none()
            if existing is None:
                row = DecisionSignalFeedbackRecord(**fields)
                session.add(row)
                session.commit()
                session.refresh(row)
                return row

            for key, value in fields.items():
                if key in {"id", "created_at"}:
                    continue
                setattr(existing, key, value)
            existing.updated_at = now
            session.commit()
            session.refresh(existing)
            return existing
