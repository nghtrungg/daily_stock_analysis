# -*- coding: utf-8 -*-
"""Persistence helpers for settlement lifecycle alert transitions."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from src.storage import (
    AlertRuleRecord,
    DatabaseManager,
    SettlementAlertStateRecord,
    utc_naive_now,
)


SETTLEMENT_ALERT_TYPE = "settlement_lifecycle"


class SettlementAlertRepository:
    """Store transition baselines and system rules in the existing alert domain."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def get_state(
        self,
        *,
        account_id: int,
        symbol: str,
    ) -> Optional[SettlementAlertStateRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(SettlementAlertStateRecord)
                .where(
                    SettlementAlertStateRecord.account_id == int(account_id),
                    SettlementAlertStateRecord.symbol == symbol,
                )
                .limit(1)
            ).scalar_one_or_none()

    def list_states(self) -> List[SettlementAlertStateRecord]:
        with self.db.get_session() as session:
            return list(
                session.execute(
                    select(SettlementAlertStateRecord).order_by(
                        SettlementAlertStateRecord.account_id.asc(),
                        SettlementAlertStateRecord.symbol.asc(),
                    )
                ).scalars().all()
            )

    def upsert_state(
        self,
        *,
        account_id: int,
        symbol: str,
        fields: Dict[str, Any],
    ) -> SettlementAlertStateRecord:
        with self.db.get_session() as session:
            row = session.execute(
                select(SettlementAlertStateRecord)
                .where(
                    SettlementAlertStateRecord.account_id == int(account_id),
                    SettlementAlertStateRecord.symbol == symbol,
                )
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = SettlementAlertStateRecord(
                    account_id=int(account_id),
                    symbol=symbol,
                )
                session.add(row)
            for name, value in fields.items():
                setattr(row, name, value)
            row.updated_at = utc_naive_now()
            session.commit()
            session.refresh(row)
            return row

    def get_or_create_system_rule(
        self,
        *,
        account_id: int,
        symbol: str,
        event_type: str,
        severity: str,
    ) -> AlertRuleRecord:
        target = self.target_identity(account_id=account_id, symbol=symbol)
        parameters = json.dumps(
            {"event_type": event_type},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.db.get_session() as session:
            row = session.execute(
                select(AlertRuleRecord)
                .where(
                    AlertRuleRecord.source == "system",
                    AlertRuleRecord.target_scope == "portfolio_position",
                    AlertRuleRecord.target == target,
                    AlertRuleRecord.alert_type == SETTLEMENT_ALERT_TYPE,
                    AlertRuleRecord.parameters == parameters,
                )
                .order_by(AlertRuleRecord.id.asc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = AlertRuleRecord(
                    name=f"Settlement {event_type}"[:64],
                    target_scope="portfolio_position",
                    target=target,
                    alert_type=SETTLEMENT_ALERT_TYPE,
                    parameters=parameters,
                    severity=severity,
                    enabled=True,
                    source="system",
                    cooldown_policy=json.dumps(
                        {"cooldown_seconds": 86400},
                        separators=(",", ":"),
                    ),
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return row

    @staticmethod
    def target_identity(*, account_id: int, symbol: str) -> str:
        return f"account:{int(account_id)}:symbol:{symbol}"[:64]
