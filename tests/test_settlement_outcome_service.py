# -*- coding: utf-8 -*-
"""Settlement-aware DecisionSignal outcome tests for PR 7."""

from __future__ import annotations

import json
import os
from datetime import date, datetime

import pytest

from src.config import Config
from src.services.settlement_outcome_service import SettlementOutcomeService
from src.storage import (
    DatabaseManager,
    DecisionSignalRecord,
    DecisionSignalTradeLink,
    PortfolioAccount,
    PortfolioTrade,
    PortfolioTradeSettlement,
    StockDaily,
)


@pytest.fixture()
def isolated_db(tmp_path):
    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "settlement_outcome.db")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


def _signal(db: DatabaseManager, *, action: str = "buy") -> int:
    metadata = {
        "market_phase_summary": {"session_date": "2026-04-23"},
        "settlement_risk": {
            "survivability_score": 60,
            "survivability_status": "moderate",
            "liquidity_status": "adequate",
        },
    }
    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code="MBB.VN",
            stock_name="MBB",
            market="vn",
            source_type="analysis",
            trigger_source="api",
            action=action,
            horizon="5d",
            stop_loss=95,
            metadata_json=json.dumps(metadata),
            status="active",
            created_at=datetime(2026, 4, 23, 15, 0),
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _bars(db: DatabaseManager) -> None:
    values = [
        # The signal-date close must never become the hypothetical entry price.
        ("2026-04-23", 80, 200, 70, 190),
        ("2026-04-24", 100, 101, 99, 100),
        ("2026-04-28", 101, 103, 97, 102),
        ("2026-04-29", 99, 105, 94, 98),
        ("2026-05-04", 100, 104, 99, 103),
        ("2026-05-05", 103, 106, 102, 105),
        ("2026-05-06", 105, 108, 104, 107),
        ("2026-05-07", 107, 110, 106, 109),
        ("2026-05-08", 109, 112, 108, 111),
        ("2026-05-11", 111, 114, 110, 113),
        ("2026-05-12", 113, 116, 112, 115),
        ("2026-05-13", 115, 118, 114, 117),
        ("2026-05-14", 117, 120, 116, 119),
        ("2026-05-15", 119, 122, 118, 121),
        ("2026-05-18", 121, 124, 120, 123),
        ("2026-05-19", 123, 126, 122, 125),
        ("2026-05-20", 125, 128, 124, 127),
        ("2026-05-21", 127, 130, 126, 129),
        ("2026-05-22", 129, 132, 128, 131),
        ("2026-05-25", 131, 134, 130, 133),
        ("2026-05-26", 133, 136, 132, 135),
        ("2026-05-27", 135, 138, 134, 137),
    ]
    with db.session_scope() as session:
        for day, open_, high, low, close in values:
            session.add(
                StockDaily(
                    code="MBB.VN",
                    date=date.fromisoformat(day),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                )
            )


def _linked_buy(db: DatabaseManager, signal_id: int) -> int:
    with db.session_scope() as session:
        account = PortfolioAccount(name="VN", market="vn", base_currency="VND")
        session.add(account)
        session.flush()
        trade = PortfolioTrade(
            account_id=account.id,
            symbol="MBB.VN",
            market="vn",
            currency="VND",
            trade_date=date(2026, 4, 24),
            side="buy",
            quantity=100,
            price=101,
            fee=15.15,
        )
        session.add(trade)
        session.flush()
        session.add(
            DecisionSignalTradeLink(
                signal_id=signal_id,
                trade_id=trade.id,
                link_type="source_recommendation",
            )
        )
        session.add(
            PortfolioTradeSettlement(
                trade_id=trade.id,
                settlement_date=date(2026, 4, 29),
                estimated_sellable_at=datetime(2026, 4, 29, 6, 0),
                calendar_version="vn-2026-v2-2025-12-26",
                policy_version="vn-equity-t2-2022-08-29",
                calculation_status="confirmed",
                warnings_json="[]",
            )
        )
        session.flush()
        return int(trade.id)


def test_signal_outcome_is_forward_only_holiday_aware_and_daily_proxy(isolated_db) -> None:
    signal_id = _signal(isolated_db)
    _bars(isolated_db)
    service = SettlementOutcomeService(db_manager=isolated_db)

    result = service.run(signal_id=signal_id, outcome_types=["signal"])
    item = result["items"][0]

    assert item["outcome_type"] == "signal"
    assert item["source_trade_id"] is None
    assert item["anchor_date"] == "2026-04-24"
    assert item["entry_price"] == 100
    assert item["estimated_settlement_date"] == "2026-04-29"
    assert item["return_t1_pct"] == 2.0
    assert item["return_t2_pct"] == -2.0
    assert item["return_first_sellable_pct"] == -2.0
    assert item["mae_before_sellable_pct"] == -6.0
    assert item["mfe_before_sellable_pct"] == 5.0
    assert item["invalidation_before_sellable"] is None
    assert "t2_intraday_ordering_ambiguous" in item["ambiguity_flags"]
    assert "daily_bar_mae_mfe_proxy" in item["ambiguity_flags"]
    assert item["net_return_first_sellable_pct"] == -2.5


def test_execution_outcome_requires_a_linked_buy_and_versions_are_idempotent(isolated_db) -> None:
    signal_id = _signal(isolated_db)
    _bars(isolated_db)
    service = SettlementOutcomeService(db_manager=isolated_db)

    first = service.run(signal_id=signal_id)
    assert [item["outcome_type"] for item in first["items"]] == ["signal"]

    trade_id = _linked_buy(isolated_db, signal_id)
    second = service.run(signal_id=signal_id)
    execution = next(item for item in second["items"] if item["outcome_type"] == "execution")
    assert execution["source_trade_id"] == trade_id
    assert execution["entry_price"] == 101
    assert execution["estimated_fee_pct"] == 0.3

    repeated = service.run(signal_id=signal_id)
    assert repeated["created"] == 0
    assert repeated["updated"] == 0
    assert repeated["skipped"] == 2

    alternate = SettlementOutcomeService(
        db_manager=isolated_db,
        engine_version="vn-settlement-outcome-v2-test",
    ).run(signal_id=signal_id)
    assert alternate["created"] == 2
    assert {item["engine_version"] for item in alternate["items"]} == {
        "vn-settlement-outcome-v2-test"
    }


def test_empty_and_populated_stats_have_samples_and_unavailable_reasons(isolated_db) -> None:
    service = SettlementOutcomeService(db_manager=isolated_db)
    empty = service.stats()
    assert empty["sample_count"] == 0
    assert empty["metrics"]["median_return_first_sellable_pct"]["value"] is None
    assert (
        empty["metrics"]["median_return_first_sellable_pct"]["unavailable_reason"]
        == "no_completed_first_sellable_returns"
    )

    signal_id = _signal(isolated_db)
    _bars(isolated_db)
    service.run(signal_id=signal_id, outcome_types=["signal"])
    stats = service.stats(outcome_type="signal")
    assert stats["sample_count"] == 1
    assert stats["metrics"]["median_return_first_sellable_pct"]["sample_count"] == 1
    assert stats["metrics"]["settlement_failure_rate_pct"]["value"] == 0.0
    assert stats["breakdowns"]["guarded_action"][0]["value"] == "buy"
