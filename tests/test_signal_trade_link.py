"""PR6 DecisionSignal-to-trade linkage regression tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.config import Config
from src.repositories.decision_signal_trade_link_repo import (
    DecisionSignalTradeLinkRepository,
    DuplicateDecisionSignalTradeLinkError,
)
from src.services.decision_signal_service import DecisionSignalService
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


class DecisionSignalTradeLinkTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.db_path = Path(self.temp_dir.name) / "signal_trade_link.db"
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
        self.portfolio = PortfolioService()
        self.signals = DecisionSignalService(db_manager=self.db)
        self.links = DecisionSignalTradeLinkRepository(self.db)
        self.account_id = self.portfolio.create_account(
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

    def _signal(
        self,
        *,
        stock_code: str = "VNM.VN",
        action: str = "buy",
        status: str = "active",
    ) -> int:
        response = self.signals.create_signal(
            {
                "stock_code": stock_code,
                "stock_name": stock_code,
                "market": "vn",
                "source_type": "analysis",
                "trace_id": f"{stock_code}-{action}-{status}",
                "trigger_source": "api",
                "action": action,
                "status": status,
                "reason": "Khuyến nghị kiểm thử",
            }
        )
        return int(response["item"]["id"])

    def _trade(self, **overrides):
        payload = {
            "account_id": self.account_id,
            "symbol": "VNM.VN",
            "trade_date": date(2026, 7, 6),
            "side": "buy",
            "quantity": 100,
            "price": 60000,
            "market": "vn",
            "currency": "VND",
        }
        payload.update(overrides)
        return self.portfolio.record_trade(**payload)

    def test_valid_link_is_transactional_and_exposed_by_trade_list(self) -> None:
        signal_id = self._signal()

        created = self._trade(source_decision_signal_id=signal_id)

        self.assertEqual(created["source_decision_signal_id"], signal_id)
        self.assertEqual(created["link_type"], "source_recommendation")
        listed = self.portfolio.list_trade_events(account_id=self.account_id)
        self.assertEqual(listed["items"][0]["source_decision_signal_id"], signal_id)
        self.assertEqual(listed["items"][0]["link_type"], "source_recommendation")

    def test_legacy_trade_without_signal_id_remains_valid(self) -> None:
        created = self._trade()

        self.assertIsNone(created["source_decision_signal_id"])
        listed = self.portfolio.list_trade_events(account_id=self.account_id)
        self.assertIsNone(listed["items"][0]["source_decision_signal_id"])

    def test_missing_mismatched_and_non_entry_signals_are_rejected(self) -> None:
        mismatch = self._signal(stock_code="FPT.VN")
        non_entry = self._signal(action="hold")

        cases = [
            (999999, "not found"),
            (mismatch, "symbol does not match"),
            (non_entry, "entry recommendation"),
        ]
        for signal_id, message in cases:
            with self.subTest(signal_id=signal_id):
                with self.assertRaisesRegex(ValueError, message):
                    self._trade(source_decision_signal_id=signal_id)

        self.assertEqual(
            self.portfolio.list_trade_events(account_id=self.account_id)["total"],
            0,
        )

    def test_source_signal_is_rejected_for_sell_or_inactive_status(self) -> None:
        active = self._signal()
        inactive = self._signal(status="archived")

        with self.assertRaisesRegex(ValueError, "only valid for buy"):
            self._trade(
                side="sell",
                source_decision_signal_id=active,
            )
        with self.assertRaisesRegex(ValueError, "must be active"):
            self._trade(source_decision_signal_id=inactive)

    def test_duplicate_link_is_rejected(self) -> None:
        signal_id = self._signal()
        trade_id = self._trade(source_decision_signal_id=signal_id)["id"]

        with self.assertRaises(DuplicateDecisionSignalTradeLinkError):
            self.links.create(signal_id=signal_id, trade_id=trade_id)


if __name__ == "__main__":
    unittest.main()
