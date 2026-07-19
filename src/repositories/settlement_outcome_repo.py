# -*- coding: utf-8 -*-
"""Persistence for versioned settlement-aware outcomes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select

from src.storage import (
    DatabaseManager,
    DecisionSignalRecord,
    DecisionSignalTradeLink,
    PortfolioTrade,
    PortfolioTradeSettlement,
    SettlementOutcomeRecord,
    utc_naive_now,
)


class SettlementOutcomeRepository:
    """Read and upsert PR7 sidecars without changing legacy outcomes."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def list_signals(
        self,
        *,
        signal_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[DecisionSignalRecord]:
        conditions = [DecisionSignalRecord.market == "vn"]
        if signal_id is not None:
            conditions.append(DecisionSignalRecord.id == int(signal_id))
        with self.db.get_session() as session:
            return list(
                session.execute(
                    select(DecisionSignalRecord)
                    .where(and_(*conditions))
                    .order_by(desc(DecisionSignalRecord.created_at), desc(DecisionSignalRecord.id))
                    .limit(max(1, min(int(limit), 500)))
                ).scalars().all()
            )

    def linked_buy_executions(
        self,
        *,
        signal_id: int,
    ) -> List[Tuple[PortfolioTrade, Optional[PortfolioTradeSettlement]]]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(PortfolioTrade, PortfolioTradeSettlement)
                .join(
                    DecisionSignalTradeLink,
                    DecisionSignalTradeLink.trade_id == PortfolioTrade.id,
                )
                .outerjoin(
                    PortfolioTradeSettlement,
                    PortfolioTradeSettlement.trade_id == PortfolioTrade.id,
                )
                .where(
                    DecisionSignalTradeLink.signal_id == int(signal_id),
                    DecisionSignalTradeLink.link_type == "source_recommendation",
                    PortfolioTrade.side == "buy",
                    PortfolioTrade.market == "vn",
                )
                .order_by(PortfolioTrade.trade_date, PortfolioTrade.id)
            ).all()
            return [(trade, settlement) for trade, settlement in rows]

    def get(self, *, fields: Dict[str, Any]) -> Optional[SettlementOutcomeRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(SettlementOutcomeRecord)
                .where(
                    SettlementOutcomeRecord.signal_id == fields["signal_id"],
                    SettlementOutcomeRecord.outcome_type == fields["outcome_type"],
                    SettlementOutcomeRecord.record_key == fields["record_key"],
                    SettlementOutcomeRecord.engine_version == fields["engine_version"],
                    SettlementOutcomeRecord.entry_policy_version
                    == fields["entry_policy_version"],
                )
                .limit(1)
            ).scalar_one_or_none()

    def upsert(self, fields: Dict[str, Any]) -> Tuple[SettlementOutcomeRecord, bool]:
        now = utc_naive_now()
        with self.db.get_session() as session:
            existing = session.execute(
                select(SettlementOutcomeRecord)
                .where(
                    SettlementOutcomeRecord.signal_id == fields["signal_id"],
                    SettlementOutcomeRecord.outcome_type == fields["outcome_type"],
                    SettlementOutcomeRecord.record_key == fields["record_key"],
                    SettlementOutcomeRecord.engine_version == fields["engine_version"],
                    SettlementOutcomeRecord.entry_policy_version
                    == fields["entry_policy_version"],
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing is None:
                row = SettlementOutcomeRecord(**fields)
                session.add(row)
                session.commit()
                session.refresh(row)
                return row, True
            for key, value in fields.items():
                if key not in {"id", "created_at"}:
                    setattr(existing, key, value)
            existing.updated_at = now
            session.commit()
            session.refresh(existing)
            return existing, False

    def list_rows(
        self,
        *,
        engine_version: str,
        outcome_type: Optional[str] = None,
        signal_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[SettlementOutcomeRecord], int]:
        conditions = [SettlementOutcomeRecord.engine_version == engine_version]
        if outcome_type:
            conditions.append(SettlementOutcomeRecord.outcome_type == outcome_type)
        if signal_id is not None:
            conditions.append(SettlementOutcomeRecord.signal_id == int(signal_id))
        where_clause = and_(*conditions)
        safe_page = max(1, int(page))
        safe_size = max(1, min(int(page_size), 100))
        with self.db.get_session() as session:
            total = session.execute(
                select(func.count(SettlementOutcomeRecord.id)).where(where_clause)
            ).scalar() or 0
            rows = session.execute(
                select(SettlementOutcomeRecord)
                .where(where_clause)
                .order_by(desc(SettlementOutcomeRecord.updated_at), desc(SettlementOutcomeRecord.id))
                .offset((safe_page - 1) * safe_size)
                .limit(safe_size)
            ).scalars().all()
            return list(rows), int(total)

    def list_stats_rows(
        self,
        *,
        engine_version: str,
        outcome_type: Optional[str] = None,
    ) -> List[SettlementOutcomeRecord]:
        conditions = [SettlementOutcomeRecord.engine_version == engine_version]
        if outcome_type:
            conditions.append(SettlementOutcomeRecord.outcome_type == outcome_type)
        with self.db.get_session() as session:
            return list(
                session.execute(
                    select(SettlementOutcomeRecord).where(and_(*conditions))
                ).scalars().all()
            )
