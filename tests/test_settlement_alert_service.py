"""PR6 persistent settlement lifecycle alert tests."""

from __future__ import annotations

import os
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from src.config import Config
from src.repositories.settlement_alert_repo import SettlementAlertRepository
from src.services.alert_service import AlertService
from src.services.alert_worker import AlertWorker
from src.services.settlement_alert_service import (
    SettlementAlertService,
    SettlementPositionObservation,
)
from src.storage import (
    AlertTriggerRecord,
    AnalysisHistory,
    DatabaseManager,
    DecisionSignalRecord,
)


class SettlementAlertServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.db_path = Path(self.temp_dir.name) / "settlement_alerts.db"
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
        self.repo = SettlementAlertRepository(self.db)
        self.current = [self._observation()]
        self.service = SettlementAlertService(
            repo=self.repo,
            observation_provider=lambda: list(self.current),
            now_provider=lambda: datetime(2026, 7, 8, 6, 0),
        )

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    @staticmethod
    def _observation(**overrides) -> SettlementPositionObservation:
        values = {
            "account_id": 7,
            "symbol": "VNM.VN",
            "market": "vn",
            "settlement_state": "unsettled",
            "total_quantity": 200.0,
            "sellable_quantity": 0.0,
            "unsettled_quantity": 200.0,
            "thesis_invalidated": False,
            "source_signal_id": 11,
            "risk_level": "low",
            "risk_rank": 1,
            "risk_policy_version": "vn-settlement-risk-v1",
            "observed_at": datetime(2026, 7, 8, 6, 0),
        }
        values.update(overrides)
        return SettlementPositionObservation(**values)

    def test_partial_and_full_sellability_transitions_are_one_shot(self) -> None:
        self.assertEqual(self.service.evaluate_transitions(), [])

        self.current = [
            self._observation(
                settlement_state="partially_sellable",
                sellable_quantity=100,
                unsettled_quantity=100,
                observed_at=datetime(2026, 7, 9, 6, 0),
            )
        ]
        partial = self.service.evaluate_transitions()
        self.assertEqual(
            [event.event_type for event in partial],
            ["position_became_partially_sellable"],
        )

        self.current = [
            self._observation(
                settlement_state="sellable",
                sellable_quantity=200,
                unsettled_quantity=0,
                observed_at=datetime(2026, 7, 10, 6, 0),
            )
        ]
        full = self.service.evaluate_transitions()
        self.assertEqual(
            [event.event_type for event in full],
            ["position_became_sellable"],
        )
        self.assertEqual(self.service.evaluate_transitions(), [])

    def test_process_restart_deduplicates_unchanged_state(self) -> None:
        self.service.evaluate_transitions()
        self.current = [
            self._observation(
                settlement_state="sellable",
                sellable_quantity=200,
                unsettled_quantity=0,
                observed_at=datetime(2026, 7, 10, 6, 0),
            )
        ]
        self.assertEqual(len(self.service.evaluate_transitions()), 1)

        restarted = SettlementAlertService(
            repo=SettlementAlertRepository(self.db),
            observation_provider=lambda: list(self.current),
            now_provider=lambda: datetime(2026, 7, 10, 6, 1),
        )
        self.assertEqual(restarted.evaluate_transitions(), [])

    def test_risk_increase_and_invalidated_thesis_are_independent(self) -> None:
        self.service.evaluate_transitions()
        self.current = [
            self._observation(
                thesis_invalidated=True,
                risk_level="high",
                risk_rank=3,
                observed_at=datetime(2026, 7, 8, 7, 0),
            )
        ]

        events = self.service.evaluate_transitions()

        self.assertEqual(
            {event.event_type for event in events},
            {
                "thesis_invalidated_while_unsettled",
                "settlement_risk_increased",
            },
        )
        for event in events:
            self.assertEqual(
                set(event.diagnostics),
                {
                    "event_type",
                    "account_id",
                    "symbol",
                    "market",
                    "settlement_state",
                    "total_quantity",
                    "sellable_quantity",
                    "unsettled_quantity",
                    "source_signal_id",
                    "risk_level",
                    "risk_policy_version",
                },
            )
            self.assertNotIn("owner_id", event.diagnostics)
            self.assertNotIn("total_cost", event.diagnostics)

    def test_risk_policy_change_resets_baseline_without_increase_alert(self) -> None:
        self.service.evaluate_transitions()
        self.current = [
            self._observation(
                risk_level="high",
                risk_rank=3,
                risk_policy_version="vn-settlement-risk-v2",
                observed_at=datetime(2026, 7, 8, 7, 0),
            )
        ]

        self.assertEqual(self.service.evaluate_transitions(), [])
        state = self.repo.get_state(account_id=7, symbol="VNM.VN")
        self.assertEqual(state.risk_level, "high")
        self.assertEqual(state.risk_rank, 3)
        self.assertEqual(state.risk_policy_version, "vn-settlement-risk-v2")

    def test_latest_risk_uses_analysis_time_not_mutable_signal_update_time(self) -> None:
        with self.db.get_session() as session:
            older_history = AnalysisHistory(
                code="VNM.VN",
                report_type="simple",
                raw_result=json.dumps(
                    {
                        "settlement_risk": {
                            "risk_level": "high",
                            "policy_version": "vn-settlement-risk-v1",
                        }
                    }
                ),
                created_at=datetime(2026, 7, 7, 6, 0),
            )
            newer_history = AnalysisHistory(
                code="VNM.VN",
                report_type="simple",
                raw_result=json.dumps(
                    {
                        "settlement_risk": {
                            "risk_level": "low",
                            "policy_version": "vn-settlement-risk-v1",
                        }
                    }
                ),
                created_at=datetime(2026, 7, 8, 6, 0),
            )
            session.add_all([older_history, newer_history])
            session.flush()
            session.add_all(
                [
                    DecisionSignalRecord(
                        stock_code="VNM.VN",
                        market="vn",
                        source_type="analysis",
                        source_report_id=older_history.id,
                        trigger_source="analysis",
                        action="buy",
                        plan_quality="complete",
                        status="invalidated",
                        created_at=datetime(2026, 7, 7, 6, 0),
                        updated_at=datetime(2026, 7, 9, 6, 0),
                    ),
                    DecisionSignalRecord(
                        stock_code="VNM.VN",
                        market="vn",
                        source_type="analysis",
                        source_report_id=newer_history.id,
                        trigger_source="analysis",
                        action="buy",
                        plan_quality="complete",
                        status="active",
                        created_at=datetime(2026, 7, 8, 6, 0),
                        updated_at=datetime(2026, 7, 8, 6, 0),
                    ),
                ]
            )
            session.commit()

        self.assertEqual(
            self.service._latest_settlement_risk(symbol="VNM.VN"),
            {
                "risk_level": "low",
                "risk_rank": 1,
                "policy_version": "vn-settlement-risk-v1",
            },
        )

    def test_snapshot_uses_explicit_vietnam_business_date(self) -> None:
        captured = {}

        class PortfolioSnapshotStub:
            def get_portfolio_snapshot(self, **kwargs):
                captured.update(kwargs)
                return {"accounts": []}

        service = SettlementAlertService(
            repo=self.repo,
            portfolio_service=PortfolioSnapshotStub(),
            today_provider=lambda: date(2026, 7, 9),
        )

        self.assertEqual(service.evaluate_transitions(), [])
        self.assertEqual(captured["as_of"], date(2026, 7, 9))

    def test_notification_failure_isolated_and_attempt_is_sanitized(self) -> None:
        self.service.evaluate_transitions()
        self.current = [
            self._observation(
                settlement_state="partially_sellable",
                sellable_quantity=100,
                unsettled_quantity=100,
                observed_at=datetime(2026, 7, 9, 6, 0),
            )
        ]

        class FailingNotifier:
            def send_with_results(self, *_args, **_kwargs):
                raise RuntimeError("webhook token=secret-value failed")

        alert_service = AlertService()
        worker = AlertWorker(
            config_provider=lambda: SimpleNamespace(
                agent_event_monitor_enabled=True,
                agent_event_alert_rules_json="",
                trading_day_check_enabled=False,
            ),
            service=alert_service,
            settlement_alert_service=self.service,
            notifier=FailingNotifier(),
        )

        stats = worker.run_once()

        self.assertEqual(stats["triggered"], 1)
        self.assertEqual(stats["recorded"], 1)
        self.assertEqual(stats["notified"], 0)
        self.assertEqual(stats["notification_attempts"], 1)
        triggers = alert_service.list_triggers(page_size=20)["items"]
        attempts = alert_service.list_notifications(page_size=20)["items"]
        self.assertEqual(len(triggers), 1)
        self.assertEqual(len(attempts), 1)
        self.assertNotIn("secret-value", attempts[0]["diagnostics"])
        with self.db.get_session() as session:
            trigger_row = session.get(AlertTriggerRecord, triggers[0]["id"])
            trigger_diagnostics = json.loads(trigger_row.diagnostics)
        self.assertEqual(
            trigger_diagnostics["event_type"],
            "position_became_partially_sellable",
        )


if __name__ == "__main__":
    unittest.main()
