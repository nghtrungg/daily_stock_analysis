# -*- coding: utf-8 -*-
"""Repository for the DecisionSignal-to-PortfolioTrade sidecar."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from sqlalchemy import delete, select

from src.storage import (
    DatabaseManager,
    DecisionSignalRecord,
    DecisionSignalTradeLink,
)


SOURCE_RECOMMENDATION_LINK = "source_recommendation"


class DuplicateDecisionSignalTradeLinkError(ValueError):
    """Raised when a trade already has the same source-link identity."""


class DecisionSignalTradeLinkRepository:
    """Persist additive recommendation/execution traceability."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    @staticmethod
    def get_signal_in_session(
        *,
        session: Any,
        signal_id: int,
    ) -> Optional[DecisionSignalRecord]:
        return session.execute(
            select(DecisionSignalRecord)
            .where(DecisionSignalRecord.id == int(signal_id))
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def create_in_session(
        *,
        session: Any,
        signal_id: int,
        trade_id: int,
        link_type: str = SOURCE_RECOMMENDATION_LINK,
    ) -> DecisionSignalTradeLink:
        existing = session.execute(
            select(DecisionSignalTradeLink)
            .where(
                DecisionSignalTradeLink.trade_id == int(trade_id),
                DecisionSignalTradeLink.link_type == link_type,
            )
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateDecisionSignalTradeLinkError(
                f"Trade {trade_id} already has a {link_type} DecisionSignal link"
            )
        row = DecisionSignalTradeLink(
            signal_id=int(signal_id),
            trade_id=int(trade_id),
            link_type=link_type,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return row

    def create(
        self,
        *,
        signal_id: int,
        trade_id: int,
        link_type: str = SOURCE_RECOMMENDATION_LINK,
    ) -> DecisionSignalTradeLink:
        with self.db.get_session() as session:
            row = self.create_in_session(
                session=session,
                signal_id=signal_id,
                trade_id=trade_id,
                link_type=link_type,
            )
            session.commit()
            return row

    def links_by_trade_ids(
        self,
        trade_ids: Iterable[int],
    ) -> Dict[int, DecisionSignalTradeLink]:
        ids = sorted({int(trade_id) for trade_id in trade_ids})
        if not ids:
            return {}
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalTradeLink).where(
                    DecisionSignalTradeLink.trade_id.in_(ids),
                    DecisionSignalTradeLink.link_type == SOURCE_RECOMMENDATION_LINK,
                )
            ).scalars().all()
            return {int(row.trade_id): row for row in rows}

    @staticmethod
    def delete_for_trade_in_session(*, session: Any, trade_id: int) -> None:
        session.execute(
            delete(DecisionSignalTradeLink).where(
                DecisionSignalTradeLink.trade_id == int(trade_id)
            )
        )
