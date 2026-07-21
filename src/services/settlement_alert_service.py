# -*- coding: utf-8 -*-
"""Detect settlement lifecycle transitions for the existing alert worker."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.repositories.settlement_alert_repo import SettlementAlertRepository
from src.services.portfolio_service import PortfolioService
from src.storage import (
    AnalysisHistory,
    DecisionSignalRecord,
    DecisionSignalTradeLink,
    PortfolioPositionLot,
    utc_naive_now,
)

logger = logging.getLogger(__name__)

SETTLEMENT_EVENT_TYPES = frozenset(
    {
        "position_became_partially_sellable",
        "position_became_sellable",
        "thesis_invalidated_while_unsettled",
        "settlement_risk_increased",
    }
)
RISK_RANKS = {
    "low": 1,
    "survivable": 1,
    "medium": 2,
    "caution": 2,
    "high": 3,
    "unsafe": 3,
}


@dataclass(frozen=True)
class SettlementPositionObservation:
    account_id: int
    symbol: str
    market: str
    settlement_state: str
    total_quantity: float
    sellable_quantity: float
    unsettled_quantity: float
    thesis_invalidated: bool = False
    source_signal_id: Optional[int] = None
    risk_level: Optional[str] = None
    risk_rank: Optional[int] = None
    risk_policy_version: Optional[str] = None
    observed_at: Optional[datetime] = None


@dataclass(frozen=True)
class SettlementLifecycleEvent:
    event_type: str
    rule_id: int
    target: str
    severity: str
    message: str
    observed_value: Optional[float]
    threshold: Optional[float]
    data_timestamp: datetime
    diagnostics: Dict[str, Any]
    cooldown_policy: Optional[Dict[str, Any]] = None


class SettlementAlertService:
    """Compare current deterministic state with the persisted prior observation."""

    def __init__(
        self,
        *,
        repo: Optional[SettlementAlertRepository] = None,
        portfolio_service: Optional[PortfolioService] = None,
        observation_provider: Optional[
            Callable[[], Iterable[SettlementPositionObservation]]
        ] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
        today_provider: Optional[Callable[[], date]] = None,
    ) -> None:
        self.repo = repo or SettlementAlertRepository()
        self.portfolio_service = portfolio_service or PortfolioService()
        self.observation_provider = observation_provider
        self.now_provider = now_provider or utc_naive_now
        self.today_provider = today_provider or (
            lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        )

    def evaluate_transitions(self) -> List[SettlementLifecycleEvent]:
        observations = list(
            self.observation_provider()
            if self.observation_provider is not None
            else self._build_current_observations()
        )
        events: List[SettlementLifecycleEvent] = []
        observed_keys = set()
        for observation in observations:
            normalized = self._normalize_observation(observation)
            key = (normalized.account_id, normalized.symbol)
            observed_keys.add(key)
            previous = self.repo.get_state(
                account_id=normalized.account_id,
                symbol=normalized.symbol,
            )
            if previous is not None:
                events.extend(self._detect_events(previous, normalized))
            self.repo.upsert_state(
                account_id=normalized.account_id,
                symbol=normalized.symbol,
                fields=self._state_fields(normalized, previous=previous),
            )

        for previous in self.repo.list_states():
            key = (int(previous.account_id), str(previous.symbol))
            if key in observed_keys or float(previous.total_quantity or 0.0) <= 0:
                continue
            self.repo.upsert_state(
                account_id=key[0],
                symbol=key[1],
                fields={
                    "market": previous.market,
                    "settlement_state": "closed",
                    "total_quantity": 0.0,
                    "sellable_quantity": 0.0,
                    "unsettled_quantity": 0.0,
                    "thesis_invalidated": False,
                    "source_signal_id": None,
                    "risk_level": None,
                    "risk_rank": None,
                    "risk_policy_version": None,
                    "observed_at": self.now_provider(),
                },
            )
        return events

    def _detect_events(
        self,
        previous: Any,
        current: SettlementPositionObservation,
    ) -> List[SettlementLifecycleEvent]:
        event_types: List[str] = []
        previous_total = float(previous.total_quantity or 0.0)
        previous_sellable = float(previous.sellable_quantity or 0.0)
        if previous_total > 0 and current.total_quantity > 0:
            if (
                previous_sellable + 1e-8 < previous_total
                and current.sellable_quantity + 1e-8 >= current.total_quantity
            ):
                event_types.append("position_became_sellable")
            elif (
                previous_sellable <= 1e-8
                and current.sellable_quantity > 1e-8
                and current.sellable_quantity + 1e-8 < current.total_quantity
            ):
                event_types.append("position_became_partially_sellable")

        if (
            not bool(previous.thesis_invalidated)
            and current.thesis_invalidated
            and current.unsettled_quantity > 1e-8
        ):
            event_types.append("thesis_invalidated_while_unsettled")

        previous_rank = (
            int(previous.risk_rank)
            if previous.risk_rank is not None
            else None
        )
        previous_policy_version = (
            str(previous.risk_policy_version or "").strip() or None
        )
        comparable_risk_policy = (
            previous_policy_version is not None
            and current.risk_policy_version is not None
            and previous_policy_version == current.risk_policy_version
        )
        if (
            comparable_risk_policy
            and previous_rank is not None
            and current.risk_rank is not None
            and current.risk_rank > previous_rank
        ):
            event_types.append("settlement_risk_increased")

        events = [
            self._build_event(event_type=event_type, observation=current)
            for event_type in event_types
        ]
        return [event for event in events if event is not None]

    def _build_event(
        self,
        *,
        event_type: str,
        observation: SettlementPositionObservation,
    ) -> Optional[SettlementLifecycleEvent]:
        severity = (
            "critical"
            if event_type == "thesis_invalidated_while_unsettled"
            else "warning"
        )
        rule = self.repo.get_or_create_system_rule(
            account_id=observation.account_id,
            symbol=observation.symbol,
            event_type=event_type,
            severity=severity,
        )
        if not bool(rule.enabled):
            return None
        target = self.repo.target_identity(
            account_id=observation.account_id,
            symbol=observation.symbol,
        )
        public_names = {
            "position_became_partially_sellable": "Một phần vị thế đã có thể bán",
            "position_became_sellable": "Toàn bộ vị thế đã có thể bán",
            "thesis_invalidated_while_unsettled": "Luận điểm đầu tư bị vô hiệu khi cổ phiếu chưa về",
            "settlement_risk_increased": "Rủi ro trong thời gian chờ thanh toán đã tăng",
        }
        message = f"{observation.symbol}: {public_names[event_type]}"
        diagnostics = {
            "event_type": event_type,
            "account_id": observation.account_id,
            "symbol": observation.symbol,
            "market": observation.market,
            "settlement_state": observation.settlement_state,
            "total_quantity": observation.total_quantity,
            "sellable_quantity": observation.sellable_quantity,
            "unsettled_quantity": observation.unsettled_quantity,
            "source_signal_id": observation.source_signal_id,
            "risk_level": observation.risk_level,
            "risk_policy_version": observation.risk_policy_version,
        }
        return SettlementLifecycleEvent(
            event_type=event_type,
            rule_id=int(rule.id),
            target=target,
            severity=severity,
            message=message,
            observed_value=(
                float(observation.risk_rank)
                if event_type == "settlement_risk_increased"
                and observation.risk_rank is not None
                else float(observation.sellable_quantity)
            ),
            threshold=None,
            data_timestamp=observation.observed_at or self.now_provider(),
            diagnostics=diagnostics,
            cooldown_policy=self._json_object(rule.cooldown_policy),
        )

    def _build_current_observations(self) -> List[SettlementPositionObservation]:
        snapshot = self.portfolio_service.get_portfolio_snapshot(
            as_of=self.today_provider(),
            cost_method="fifo",
            include_realtime=False,
        )
        observations: List[SettlementPositionObservation] = []
        for account in snapshot.get("accounts", []) or []:
            account_id = int(account["account_id"])
            for position in account.get("positions", []) or []:
                if (
                    str(position.get("market") or "").strip().lower() != "vn"
                    or float(position.get("quantity") or 0.0) <= 0
                ):
                    continue
                symbol = str(position.get("symbol") or "").strip().upper()
                source_signal_id, thesis_invalidated = (
                    self._linked_thesis_state(account_id=account_id, symbol=symbol)
                )
                risk = self._latest_settlement_risk(symbol=symbol)
                observations.append(
                    SettlementPositionObservation(
                        account_id=account_id,
                        symbol=symbol,
                        market="vn",
                        settlement_state=str(
                            position.get("settlement_state") or "unknown"
                        ),
                        total_quantity=float(position.get("quantity") or 0.0),
                        sellable_quantity=float(
                            position.get("sellable_quantity") or 0.0
                        ),
                        unsettled_quantity=float(
                            position.get("unsettled_quantity") or 0.0
                        ),
                        thesis_invalidated=thesis_invalidated,
                        source_signal_id=source_signal_id,
                        risk_level=risk.get("risk_level"),
                        risk_rank=risk.get("risk_rank"),
                        risk_policy_version=risk.get("policy_version"),
                        observed_at=self.now_provider(),
                    )
                )
        return observations

    def _linked_thesis_state(
        self,
        *,
        account_id: int,
        symbol: str,
    ) -> tuple[Optional[int], bool]:
        with self.repo.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalRecord)
                .join(
                    DecisionSignalTradeLink,
                    DecisionSignalTradeLink.signal_id == DecisionSignalRecord.id,
                )
                .join(
                    PortfolioPositionLot,
                    PortfolioPositionLot.source_trade_id
                    == DecisionSignalTradeLink.trade_id,
                )
                .where(
                    PortfolioPositionLot.account_id == int(account_id),
                    PortfolioPositionLot.symbol == symbol,
                    PortfolioPositionLot.cost_method == "fifo",
                    PortfolioPositionLot.remaining_quantity > 0,
                )
                .order_by(desc(DecisionSignalTradeLink.created_at))
            ).scalars().all()
        if not rows:
            return None, False
        invalidated = next(
            (row for row in rows if str(row.status) == "invalidated"),
            None,
        )
        selected = invalidated or rows[0]
        return int(selected.id), invalidated is not None

    def _latest_settlement_risk(self, *, symbol: str) -> Dict[str, Any]:
        normalized = canonical_stock_code(normalize_stock_code(symbol))
        candidates = list(dict.fromkeys([symbol, normalized]))
        with self.repo.db.get_session() as session:
            histories = session.execute(
                select(AnalysisHistory)
                .join(
                    DecisionSignalRecord,
                    DecisionSignalRecord.source_report_id == AnalysisHistory.id,
                )
                .where(
                    DecisionSignalRecord.market == "vn",
                    DecisionSignalRecord.stock_code.in_(candidates),
                    DecisionSignalRecord.source_report_id.is_not(None),
                )
                .order_by(
                    desc(AnalysisHistory.created_at),
                    desc(AnalysisHistory.id),
                )
                .distinct()
                .limit(20)
            ).scalars().all()
            for history in histories:
                risk = self._risk_from_history(history)
                if risk:
                    return risk
        return {}

    @classmethod
    def _risk_from_history(cls, history: Optional[AnalysisHistory]) -> Dict[str, Any]:
        if history is None or not history.raw_result:
            return {}
        if isinstance(history.raw_result, dict):
            payload = history.raw_result
        else:
            try:
                payload = json.loads(history.raw_result)
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
        if not isinstance(payload, dict):
            return {}
        risk = payload.get("settlement_risk")
        if not isinstance(risk, dict):
            dashboard = payload.get("dashboard")
            risk = (
                dashboard.get("settlement_risk")
                if isinstance(dashboard, dict)
                else None
            )
        if not isinstance(risk, dict):
            return {}
        level = str(
            risk.get("risk_level")
            or risk.get("survivability_status")
            or ""
        ).strip().lower()
        rank = RISK_RANKS.get(level)
        if rank is None:
            return {}
        return {
            "risk_level": level,
            "risk_rank": rank,
            "policy_version": str(risk.get("policy_version") or "") or None,
        }

    def _normalize_observation(
        self,
        value: SettlementPositionObservation,
    ) -> SettlementPositionObservation:
        observed_at = value.observed_at or self.now_provider()
        level = str(value.risk_level or "").strip().lower() or None
        rank = value.risk_rank
        if rank is None and level is not None:
            rank = RISK_RANKS.get(level)
        symbol = str(value.symbol or "").strip().upper()
        if (
            len(symbol) > 16
            or not symbol.endswith(".VN")
            or re.fullmatch(r"[A-Z0-9.-]+", symbol) is None
        ):
            raise ValueError(
                "Settlement alert observations require an explicit safe .VN symbol"
            )
        policy_version = str(value.risk_policy_version or "").strip() or None
        if policy_version is not None and (
            len(policy_version) > 64
            or re.fullmatch(r"[A-Za-z0-9._:-]+", policy_version) is None
        ):
            policy_version = None
        return SettlementPositionObservation(
            account_id=int(value.account_id),
            symbol=symbol,
            market=str(value.market or "vn").strip().lower(),
            settlement_state=str(value.settlement_state or "unknown"),
            total_quantity=max(0.0, float(value.total_quantity)),
            sellable_quantity=max(0.0, float(value.sellable_quantity)),
            unsettled_quantity=max(0.0, float(value.unsettled_quantity)),
            thesis_invalidated=bool(value.thesis_invalidated),
            source_signal_id=value.source_signal_id,
            risk_level=level,
            risk_rank=rank,
            risk_policy_version=policy_version,
            observed_at=observed_at,
        )

    @staticmethod
    def _state_fields(
        current: SettlementPositionObservation,
        *,
        previous: Optional[Any],
    ) -> Dict[str, Any]:
        risk_level = current.risk_level
        risk_rank = current.risk_rank
        risk_policy_version = current.risk_policy_version
        if previous is not None and risk_rank is None:
            risk_level = previous.risk_level
            risk_rank = previous.risk_rank
            risk_policy_version = previous.risk_policy_version
        return {
            "market": current.market,
            "settlement_state": current.settlement_state,
            "total_quantity": current.total_quantity,
            "sellable_quantity": current.sellable_quantity,
            "unsettled_quantity": current.unsettled_quantity,
            "thesis_invalidated": current.thesis_invalidated,
            "source_signal_id": current.source_signal_id,
            "risk_level": risk_level,
            "risk_rank": risk_rank,
            "risk_policy_version": risk_policy_version,
            "observed_at": current.observed_at,
        }

    @staticmethod
    def _json_object(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            return dict(value)
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return dict(parsed) if isinstance(parsed, dict) else None
