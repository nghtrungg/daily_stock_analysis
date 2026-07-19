"""Settlement-aware Vietnam portfolio ledger regression tests."""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.config import Config
from src.services.portfolio_service import (
    PortfolioService,
    PortfolioUnsettledSaleError,
)
from src.storage import (
    DatabaseManager,
    PortfolioPositionLot,
    PortfolioTrade,
    PortfolioTradeSettlement,
)


class SettlementAwarePortfolioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.db_path = Path(self.temp_dir.name) / "portfolio_settlement.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=VNM.VN",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = PortfolioService()
        self.account_id = self.service.create_account(
            name="VN account",
            broker="Demo",
            market="vn",
            base_currency="VND",
        )["id"]

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def _buy(
        self,
        *,
        trade_date: date,
        quantity: float = 100,
        executed_at: datetime | None = None,
        uid: str | None = None,
    ) -> int:
        return self.service.record_trade(
            account_id=self.account_id,
            symbol="VNM.VN",
            trade_date=trade_date,
            executed_at=executed_at,
            side="buy",
            quantity=quantity,
            price=60000,
            market="vn",
            currency="VND",
            trade_uid=uid,
        )["id"]

    def _sell(
        self,
        *,
        trade_date: date,
        quantity: float,
        executed_at: datetime | None = None,
        uid: str | None = None,
    ) -> int:
        return self.service.record_trade(
            account_id=self.account_id,
            symbol="VNM.VN",
            trade_date=trade_date,
            executed_at=executed_at,
            side="sell",
            quantity=quantity,
            price=62000,
            market="vn",
            currency="VND",
            trade_uid=uid,
        )["id"]

    def test_buy_freezes_normalized_execution_and_settlement_provenance(self) -> None:
        trade_id = self._buy(
            trade_date=date(2026, 7, 6),
            executed_at=datetime(2026, 7, 6, 3, 15, tzinfo=timezone.utc),
        )

        with self.db.get_session() as session:
            trade = session.get(PortfolioTrade, trade_id)
            settlement = session.execute(
                select(PortfolioTradeSettlement).where(
                    PortfolioTradeSettlement.trade_id == trade_id
                )
            ).scalar_one()

        self.assertEqual(trade.executed_at, datetime(2026, 7, 6, 3, 15))
        self.assertEqual(settlement.settlement_date, date(2026, 7, 8))
        self.assertEqual(
            settlement.estimated_sellable_at,
            datetime(2026, 7, 8, 6, 0),
        )
        self.assertEqual(settlement.calculation_status, "confirmed")
        self.assertIn("vn-2026", settlement.calendar_version)
        self.assertTrue(settlement.policy_version)
        self.assertEqual(settlement.warnings_json, "[]")

    def test_sale_above_sellable_but_below_held_has_domain_quantities(self) -> None:
        self._buy(trade_date=date(2026, 7, 6), quantity=100)

        with self.assertRaises(PortfolioUnsettledSaleError) as ctx:
            self._sell(
                trade_date=date(2026, 7, 7),
                executed_at=datetime(
                    2026,
                    7,
                    7,
                    14,
                    0,
                    tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
                ),
                quantity=80,
            )

        error = ctx.exception
        self.assertEqual(error.requested_quantity, 80)
        self.assertEqual(error.held_quantity, 100)
        self.assertEqual(error.sellable_quantity, 0)
        self.assertEqual(error.unsettled_quantity, 100)
        self.assertEqual(
            error.next_sellable_at,
            datetime(2026, 7, 8, 13, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        )

    def test_multiple_lots_only_consume_eligible_quantity(self) -> None:
        self._buy(trade_date=date(2026, 7, 6), quantity=100, uid="buy-1")
        self._buy(trade_date=date(2026, 7, 7), quantity=100, uid="buy-2")

        self._sell(
            trade_date=date(2026, 7, 8),
            executed_at=datetime(
                2026,
                7,
                8,
                14,
                0,
                tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
            ),
            quantity=80,
        )

        with self.assertRaises(PortfolioUnsettledSaleError) as ctx:
            self._sell(
                trade_date=date(2026, 7, 8),
                executed_at=datetime(
                    2026,
                    7,
                    8,
                    14,
                    1,
                    tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
                ),
                quantity=30,
            )

        self.assertEqual(ctx.exception.held_quantity, 120)
        self.assertEqual(ctx.exception.sellable_quantity, 20)
        self.assertEqual(ctx.exception.unsettled_quantity, 100)

        snapshot = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 8),
            cost_method="fifo",
            include_realtime=False,
        )
        position = snapshot["accounts"][0]["positions"][0]
        self.assertEqual(position["position_lifecycle"], "open")
        self.assertEqual(position["settlement_state"], "partially_sellable")
        self.assertEqual(position["total_quantity"], 120)
        self.assertEqual(position["sellable_quantity"], 20)
        self.assertEqual(position["unsettled_quantity"], 100)
        self.assertEqual(position["next_sellable_at"], "2026-07-09T13:00:00+07:00")
        self.assertEqual(position["settlement_calculation_status"], "confirmed")

    def test_average_cost_retains_acquisition_lots_and_multiple_partial_sales(self) -> None:
        self._buy(trade_date=date(2026, 7, 6), quantity=100, uid="avg-buy-1")
        self._buy(trade_date=date(2026, 7, 7), quantity=100, uid="avg-buy-2")
        self._sell(
            trade_date=date(2026, 7, 9),
            quantity=60,
            executed_at=datetime(
                2026,
                7,
                9,
                13,
                30,
                tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
            ),
            uid="avg-sell-1",
        )
        self._sell(
            trade_date=date(2026, 7, 9),
            quantity=40,
            executed_at=datetime(
                2026,
                7,
                9,
                14,
                0,
                tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
            ),
            uid="avg-sell-2",
        )

        first = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 9),
            cost_method="avg",
            include_realtime=False,
        )
        second = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 9),
            cost_method="avg",
            include_realtime=False,
        )

        position = first["accounts"][0]["positions"][0]
        self.assertEqual(position["quantity"], 100)
        self.assertEqual(position["sellable_quantity"], 100)
        self.assertEqual(first, second)
        with self.db.get_session() as session:
            lots = session.execute(
                select(PortfolioPositionLot)
                .where(
                    PortfolioPositionLot.account_id == self.account_id,
                    PortfolioPositionLot.cost_method == "avg",
                )
                .order_by(PortfolioPositionLot.source_trade_id)
            ).scalars().all()

        self.assertEqual(len(lots), 1)
        self.assertIsNotNone(lots[0].source_trade_id)
        self.assertEqual(lots[0].settlement_state, "sellable")

    def test_split_adjustment_scales_unsettled_and_sellable_lot_quantity(self) -> None:
        self._buy(trade_date=date(2026, 7, 6), quantity=100)
        self.service.record_corporate_action(
            account_id=self.account_id,
            symbol="VNM.VN",
            effective_date=date(2026, 7, 7),
            action_type="split_adjustment",
            market="vn",
            currency="VND",
            split_ratio=2,
        )

        with self.assertRaises(PortfolioUnsettledSaleError) as ctx:
            self._sell(trade_date=date(2026, 7, 7), quantity=150)
        self.assertEqual(ctx.exception.held_quantity, 200)
        self.assertEqual(ctx.exception.unsettled_quantity, 200)

        self._sell(
            trade_date=date(2026, 7, 8),
            quantity=150,
            executed_at=datetime(
                2026,
                7,
                8,
                14,
                0,
                tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
            ),
        )
        snapshot = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 8),
            cost_method="fifo",
            include_realtime=False,
        )
        self.assertEqual(snapshot["accounts"][0]["positions"][0]["quantity"], 50)

    def test_legacy_trade_without_execution_or_sidecar_remains_usable_and_unknown(self) -> None:
        legacy = self.service.repo.add_trade(
            account_id=self.account_id,
            trade_uid="legacy-buy",
            symbol="VNM.VN",
            market="vn",
            currency="VND",
            trade_date=date(2026, 7, 6),
            side="buy",
            quantity=100,
            price=60000,
            fee=0,
            tax=0,
        )
        self.assertIsNone(legacy.executed_at)

        snapshot = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 6),
            cost_method="fifo",
            include_realtime=False,
        )
        position = snapshot["accounts"][0]["positions"][0]
        self.assertEqual(position["settlement_state"], "unknown")
        self.assertEqual(position["sellable_quantity"], 100)
        self.assertEqual(position["settlement_calculation_status"], "unknown")

        self._sell(trade_date=date(2026, 7, 6), quantity=100)

    def test_calendar_status_propagates_degraded_and_unknown(self) -> None:
        trade_id = self._buy(trade_date=date(2026, 7, 6), quantity=100)

        with self.db.get_session() as session:
            settlement = session.get(PortfolioTradeSettlement, trade_id)
            settlement.calculation_status = "degraded"
            session.commit()

        degraded = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 6),
            cost_method="fifo",
            include_realtime=False,
        )
        degraded_position = degraded["accounts"][0]["positions"][0]
        self.assertEqual(
            degraded_position["settlement_calculation_status"],
            "degraded",
        )
        self.assertEqual(degraded_position["settlement_state"], "unsettled")

        with self.db.get_session() as session:
            settlement = session.get(PortfolioTradeSettlement, trade_id)
            settlement.calculation_status = "unknown"
            session.commit()

        unknown = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 7, 6),
            cost_method="fifo",
            include_realtime=False,
        )
        unknown_position = unknown["accounts"][0]["positions"][0]
        self.assertEqual(
            unknown_position["settlement_calculation_status"],
            "unknown",
        )
        self.assertEqual(unknown_position["settlement_state"], "unknown")

    def test_concurrent_settled_sales_cannot_double_consume_quantity(self) -> None:
        self._buy(trade_date=date(2026, 7, 6), quantity=100)
        barrier = threading.Barrier(3)
        successes: list[str] = []
        errors: list[Exception] = []

        def worker(uid: str) -> None:
            service = PortfolioService()
            barrier.wait()
            try:
                service.record_trade(
                    account_id=self.account_id,
                    symbol="VNM.VN",
                    trade_date=date(2026, 7, 8),
                    executed_at=datetime(
                        2026,
                        7,
                        8,
                        14,
                        0,
                        tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
                    ),
                    side="sell",
                    quantity=100,
                    price=62000,
                    market="vn",
                    currency="VND",
                    trade_uid=uid,
                )
                successes.append(uid)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(f"settled-race-{index}",))
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
