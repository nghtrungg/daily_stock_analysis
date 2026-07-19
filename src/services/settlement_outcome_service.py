# -*- coding: utf-8 -*-
"""Versioned, settlement-aware signal and execution outcome measurement."""

from __future__ import annotations

from datetime import date, datetime, time
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo

from src.core.trading_calendar import (
    MARKET_TIMEZONE,
    SettlementCalculationStatus,
    calculate_vn_settlement,
)
from src.repositories.settlement_outcome_repo import SettlementOutcomeRepository
from src.repositories.stock_repo import StockRepository
from src.services.decision_signal_service import DecisionSignalNotFoundError
from src.storage import (
    DatabaseManager,
    DecisionSignalRecord,
    PortfolioTrade,
    PortfolioTradeSettlement,
    SettlementOutcomeRecord,
)


SETTLEMENT_OUTCOME_ENGINE_VERSION = "vn-settlement-outcome-v1"
SIGNAL_ENTRY_POLICY_VERSION = "vn-next-session-open-v1"
EXECUTION_ENTRY_POLICY_VERSION = "vn-linked-trade-price-v1"
OUTCOME_TYPES = frozenset({"signal", "execution"})
ROUND_TRIP_FEE_PCT = 0.30
SIGNAL_ROUND_TRIP_SLIPPAGE_PCT = 0.20
EXECUTION_EXIT_SLIPPAGE_PCT = 0.10


class SettlementOutcomeService:
    """Calculate reproducible daily-bar settlement outcomes."""

    def __init__(
        self,
        *,
        db_manager: Optional[DatabaseManager] = None,
        repo: Optional[SettlementOutcomeRepository] = None,
        stock_repo: Optional[StockRepository] = None,
        engine_version: str = SETTLEMENT_OUTCOME_ENGINE_VERSION,
        calendar_directory: Optional[Path] = None,
    ) -> None:
        self.repo = repo or SettlementOutcomeRepository(db_manager)
        self.stock_repo = stock_repo or StockRepository(db_manager)
        self.engine_version = str(engine_version).strip() or SETTLEMENT_OUTCOME_ENGINE_VERSION
        self.calendar_directory = calendar_directory

    def run(
        self,
        *,
        signal_id: Optional[int] = None,
        outcome_types: Optional[Sequence[str]] = None,
        force: bool = False,
        limit: int = 100,
    ) -> Dict[str, Any]:
        types = self._normalize_outcome_types(outcome_types)
        signals = self.repo.list_signals(signal_id=signal_id, limit=limit)
        if signal_id is not None and not signals:
            raise DecisionSignalNotFoundError(f"Decision signal not found: {signal_id}")

        items: List[Dict[str, Any]] = []
        created = updated = skipped = 0
        for signal in signals:
            candidates: List[Dict[str, Any]] = []
            if "signal" in types:
                candidates.append(self._evaluate_signal(signal))
            if "execution" in types:
                for trade, settlement in self.repo.linked_buy_executions(signal_id=int(signal.id)):
                    candidates.append(self._evaluate_execution(signal, trade, settlement))

            for fields in candidates:
                existing = self.repo.get(fields=fields)
                if existing is not None and not force and not existing.unavailable_reason:
                    skipped += 1
                    items.append(self._serialize(existing))
                    continue
                row, was_created = self.repo.upsert(fields)
                created += int(was_created)
                updated += int(not was_created)
                items.append(self._serialize(row))

        return {
            "items": items,
            "evaluated": created + updated,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "engine_version": self.engine_version,
        }

    def list(
        self,
        *,
        signal_id: Optional[int] = None,
        outcome_type: Optional[str] = None,
        engine_version: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        normalized_type = self._normalize_optional_outcome_type(outcome_type)
        rows, total = self.repo.list_rows(
            engine_version=str(engine_version or self.engine_version),
            outcome_type=normalized_type,
            signal_id=signal_id,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._serialize(row) for row in rows],
            "total": total,
            "page": max(1, int(page)),
            "page_size": max(1, min(int(page_size), 100)),
        }

    def stats(
        self,
        *,
        outcome_type: Optional[str] = None,
        engine_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_type = self._normalize_optional_outcome_type(outcome_type)
        rows = self.repo.list_stats_rows(
            engine_version=str(engine_version or self.engine_version),
            outcome_type=normalized_type,
        )
        return self._aggregate(rows, outcome_type=normalized_type)

    def _evaluate_signal(self, signal: DecisionSignalRecord) -> Dict[str, Any]:
        policy = SIGNAL_ENTRY_POLICY_VERSION
        base = self._base_fields(
            signal,
            outcome_type="signal",
            record_key="signal",
            source_trade_id=None,
            entry_policy_version=policy,
        )
        if signal.action not in {"buy", "add"}:
            return self._unable(base, "non_entry_action")
        signal_date = self._signal_date(signal)
        if signal_date is None:
            return self._unable(base, "missing_signal_date")
        entry_candidates = self.stock_repo.get_forward_bars(
            code=signal.stock_code,
            analysis_date=signal_date,
            eval_window_days=1,
        )
        if not entry_candidates:
            return self._unable(base, "missing_entry_bar")
        entry_bar = entry_candidates[0]
        if not self._positive(entry_bar.open):
            return self._unable(base, "invalid_entry_open")
        trade_time = datetime.combine(
            entry_bar.date,
            time(9, 0),
            tzinfo=ZoneInfo(MARKET_TIMEZONE["vn"]),
        )
        settlement = calculate_vn_settlement(
            trade_time,
            calendar_directory=self.calendar_directory,
        )
        return self._evaluate_prices(
            base,
            signal=signal,
            anchor_date=entry_bar.date,
            entry_price=float(entry_bar.open),
            settlement_date=settlement.settlement_date,
            sellable_at=settlement.estimated_sellable_at,
            calendar_version=settlement.calendar_version,
            settlement_policy_version=settlement.policy_version,
            calculation_status=settlement.calculation_status.value,
            fee_pct=ROUND_TRIP_FEE_PCT,
            slippage_pct=SIGNAL_ROUND_TRIP_SLIPPAGE_PCT,
        )

    def _evaluate_execution(
        self,
        signal: DecisionSignalRecord,
        trade: PortfolioTrade,
        settlement: Optional[PortfolioTradeSettlement],
    ) -> Dict[str, Any]:
        base = self._base_fields(
            signal,
            outcome_type="execution",
            record_key=f"trade:{int(trade.id)}",
            source_trade_id=int(trade.id),
            entry_policy_version=EXECUTION_ENTRY_POLICY_VERSION,
        )
        if trade.side != "buy" or trade.market != "vn":
            return self._unable(base, "linked_trade_not_vn_buy")
        if not self._positive(trade.price):
            return self._unable(base, "invalid_execution_price")

        if settlement is None:
            trade_time = datetime.combine(
                trade.trade_date,
                time(9, 0),
                tzinfo=ZoneInfo(MARKET_TIMEZONE["vn"]),
            )
            calculated = calculate_vn_settlement(
                trade_time,
                calendar_directory=self.calendar_directory,
            )
            settlement_date = calculated.settlement_date
            sellable_at = calculated.estimated_sellable_at
            calendar_version = calculated.calendar_version
            settlement_policy_version = calculated.policy_version
            calculation_status = calculated.calculation_status.value
        else:
            settlement_date = settlement.settlement_date
            sellable_at = settlement.estimated_sellable_at
            calendar_version = settlement.calendar_version
            settlement_policy_version = settlement.policy_version
            calculation_status = settlement.calculation_status

        notional = float(trade.quantity or 0) * float(trade.price)
        recorded_entry_fee_pct = (
            float(trade.fee or 0) / notional * 100 if notional > 0 else 0.0
        )
        fee_pct = round(recorded_entry_fee_pct + ROUND_TRIP_FEE_PCT / 2, 4)
        return self._evaluate_prices(
            base,
            signal=signal,
            anchor_date=trade.trade_date,
            entry_price=float(trade.price),
            settlement_date=settlement_date,
            sellable_at=sellable_at,
            calendar_version=calendar_version,
            settlement_policy_version=settlement_policy_version,
            calculation_status=calculation_status,
            fee_pct=fee_pct,
            slippage_pct=EXECUTION_EXIT_SLIPPAGE_PCT,
        )

    def _evaluate_prices(
        self,
        base: Dict[str, Any],
        *,
        signal: DecisionSignalRecord,
        anchor_date: date,
        entry_price: float,
        settlement_date: date,
        sellable_at: datetime,
        calendar_version: str,
        settlement_policy_version: str,
        calculation_status: str,
        fee_pct: float,
        slippage_pct: float,
    ) -> Dict[str, Any]:
        bars = self.stock_repo.get_forward_bars(
            code=signal.stock_code,
            analysis_date=anchor_date,
            eval_window_days=20,
        )
        flags = ["daily_bar_mae_mfe_proxy", "t2_intraday_ordering_ambiguous"]
        if calculation_status != SettlementCalculationStatus.CONFIRMED.value:
            flags.append("calendar_coverage_not_confirmed")
        by_date = {bar.date: bar for bar in bars}
        sellable_bar = by_date.get(settlement_date)
        first_sellable_return = self._return_pct(
            getattr(sellable_bar, "close", None),
            entry_price,
        )
        pre_sellable = [bar for bar in bars if bar.date <= settlement_date]
        valid_lows = [float(bar.low) for bar in pre_sellable if self._positive(bar.low)]
        valid_highs = [float(bar.high) for bar in pre_sellable if self._positive(bar.high)]
        mae = self._return_pct(min(valid_lows), entry_price) if valid_lows else None
        mfe = self._return_pct(max(valid_highs), entry_price) if valid_highs else None
        invalidation = self._invalidation_proxy(
            stop_loss=signal.stop_loss,
            bars=pre_sellable,
            settlement_date=settlement_date,
            flags=flags,
        )
        data_quality = (
            "confirmed"
            if calculation_status == "confirmed" and sellable_bar is not None
            else "degraded"
            if calculation_status != "unknown" and bars
            else "unknown"
        )
        unavailable_reason = None
        if sellable_bar is None:
            unavailable_reason = "missing_first_sellable_price"
        risk = self._risk_context(signal)
        return {
            **base,
            "calendar_version": calendar_version,
            "settlement_policy_version": settlement_policy_version,
            "anchor_date": anchor_date,
            "estimated_settlement_date": settlement_date,
            "estimated_first_sellable_at": self._utc_naive(sellable_at),
            "entry_price": entry_price,
            "return_t1_pct": self._bar_return(bars, 1, entry_price),
            "return_t2_pct": self._bar_return(bars, 2, entry_price),
            "return_first_sellable_pct": first_sellable_return,
            "return_t5_pct": self._bar_return(bars, 5, entry_price),
            "return_t10_pct": self._bar_return(bars, 10, entry_price),
            "return_t20_pct": self._bar_return(bars, 20, entry_price),
            "mae_before_sellable_pct": mae,
            "mfe_before_sellable_pct": mfe,
            "invalidation_before_sellable": invalidation,
            "operationally_executable": sellable_bar is not None,
            "estimated_fee_pct": fee_pct,
            "estimated_slippage_pct": slippage_pct,
            "net_return_first_sellable_pct": (
                round(first_sellable_return - fee_pct - slippage_pct, 4)
                if first_sellable_return is not None
                else None
            ),
            "data_quality": data_quality,
            "unavailable_reason": unavailable_reason,
            "ambiguity_flags_json": json.dumps(flags, ensure_ascii=False),
            **risk,
        }

    def _base_fields(
        self,
        signal: DecisionSignalRecord,
        *,
        outcome_type: str,
        record_key: str,
        source_trade_id: Optional[int],
        entry_policy_version: str,
    ) -> Dict[str, Any]:
        return {
            "signal_id": int(signal.id),
            "source_trade_id": source_trade_id,
            "outcome_type": outcome_type,
            "record_key": record_key,
            "engine_version": self.engine_version,
            "entry_policy_version": entry_policy_version,
            "guarded_action": signal.action,
            "ambiguity_flags_json": "[]",
            "data_quality": "unknown",
            "operationally_executable": False,
        }

    def _unable(self, base: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            **base,
            "unavailable_reason": reason,
            "ambiguity_flags_json": "[]",
        }

    @staticmethod
    def _signal_date(signal: DecisionSignalRecord) -> Optional[date]:
        try:
            metadata = json.loads(signal.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        raw = (metadata.get("market_phase_summary") or {}).get("session_date")
        if raw:
            try:
                return date.fromisoformat(str(raw)[:10])
            except ValueError:
                pass
        return signal.created_at.date() if signal.created_at else None

    @staticmethod
    def _risk_context(signal: DecisionSignalRecord) -> Dict[str, Any]:
        try:
            metadata = json.loads(signal.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        risk = metadata.get("settlement_risk") or {}
        score = risk.get("survivability_score")
        return {
            "settlement_risk_score": float(score) if SettlementOutcomeService._finite(score) else None,
            "survivability_bucket": risk.get("survivability_status"),
            "liquidity_bucket": risk.get("liquidity_status"),
        }

    @staticmethod
    def _invalidation_proxy(
        *,
        stop_loss: Optional[float],
        bars: Sequence[Any],
        settlement_date: date,
        flags: List[str],
    ) -> Optional[bool]:
        if not SettlementOutcomeService._positive(stop_loss):
            return None
        prior_breach = any(
            bar.date < settlement_date
            and SettlementOutcomeService._positive(bar.low)
            and float(bar.low) <= float(stop_loss)
            for bar in bars
        )
        if prior_breach:
            return True
        sellable_breach = any(
            bar.date == settlement_date
            and SettlementOutcomeService._positive(bar.low)
            and float(bar.low) <= float(stop_loss)
            for bar in bars
        )
        if sellable_breach:
            if "invalidation_ordering_ambiguous" not in flags:
                flags.append("invalidation_ordering_ambiguous")
            return None
        return False

    @staticmethod
    def _bar_return(bars: Sequence[Any], number: int, entry_price: float) -> Optional[float]:
        if len(bars) < number:
            return None
        return SettlementOutcomeService._return_pct(bars[number - 1].close, entry_price)

    @staticmethod
    def _return_pct(value: Any, entry_price: float) -> Optional[float]:
        if not SettlementOutcomeService._positive(value):
            return None
        return round((float(value) / float(entry_price) - 1) * 100, 4)

    @staticmethod
    def _positive(value: Any) -> bool:
        return SettlementOutcomeService._finite(value) and float(value) > 0

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    @staticmethod
    def _normalize_optional_outcome_type(value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        normalized = str(value).strip().lower()
        if normalized not in OUTCOME_TYPES:
            raise ValueError("outcome_type must be signal or execution")
        return normalized

    @classmethod
    def _normalize_outcome_types(cls, values: Optional[Sequence[str]]) -> List[str]:
        if not values:
            return ["signal", "execution"]
        result = []
        for value in values:
            normalized = cls._normalize_optional_outcome_type(value)
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _serialize(row: SettlementOutcomeRecord) -> Dict[str, Any]:
        try:
            flags = json.loads(row.ambiguity_flags_json or "[]")
        except json.JSONDecodeError:
            flags = ["invalid_ambiguity_flags_json"]
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "source_trade_id": row.source_trade_id,
            "outcome_type": row.outcome_type,
            "engine_version": row.engine_version,
            "entry_policy_version": row.entry_policy_version,
            "calendar_version": row.calendar_version,
            "settlement_policy_version": row.settlement_policy_version,
            "anchor_date": row.anchor_date.isoformat() if row.anchor_date else None,
            "estimated_settlement_date": (
                row.estimated_settlement_date.isoformat()
                if row.estimated_settlement_date
                else None
            ),
            "estimated_first_sellable_at": (
                row.estimated_first_sellable_at.isoformat()
                if row.estimated_first_sellable_at
                else None
            ),
            "entry_price": row.entry_price,
            "return_t1_pct": row.return_t1_pct,
            "return_t2_pct": row.return_t2_pct,
            "return_first_sellable_pct": row.return_first_sellable_pct,
            "return_t5_pct": row.return_t5_pct,
            "return_t10_pct": row.return_t10_pct,
            "return_t20_pct": row.return_t20_pct,
            "mae_before_sellable_pct": row.mae_before_sellable_pct,
            "mfe_before_sellable_pct": row.mfe_before_sellable_pct,
            "invalidation_before_sellable": row.invalidation_before_sellable,
            "operationally_executable": row.operationally_executable,
            "estimated_fee_pct": row.estimated_fee_pct,
            "estimated_slippage_pct": row.estimated_slippage_pct,
            "net_return_first_sellable_pct": row.net_return_first_sellable_pct,
            "data_quality": row.data_quality,
            "unavailable_reason": row.unavailable_reason,
            "ambiguity_flags": flags if isinstance(flags, list) else [],
            "settlement_risk_score": row.settlement_risk_score,
            "survivability_bucket": row.survivability_bucket,
            "liquidity_bucket": row.liquidity_bucket,
            "guarded_action": row.guarded_action,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @classmethod
    def _aggregate(
        cls,
        rows: Sequence[SettlementOutcomeRecord],
        *,
        outcome_type: Optional[str],
    ) -> Dict[str, Any]:
        settlement_eligible = [
            row for row in rows if row.guarded_action in {"buy", "add"}
        ]
        returns = [
            float(row.return_first_sellable_pct)
            for row in rows
            if row.return_first_sellable_pct is not None
        ]
        net_returns = [
            float(row.net_return_first_sellable_pct)
            for row in rows
            if row.net_return_first_sellable_pct is not None
        ]
        maes = [
            float(row.mae_before_sellable_pct)
            for row in rows
            if row.mae_before_sellable_pct is not None
        ]
        invalidation_rows = [
            row for row in rows if row.invalidation_before_sellable is not None
        ]
        failures = sum(
            1 for row in settlement_eligible if not row.operationally_executable
        )
        gains = [value for value in net_returns if value > 0]
        losses = [value for value in net_returns if value < 0]
        risk_adjusted = [
            float(row.net_return_first_sellable_pct) / float(row.settlement_risk_score)
            for row in rows
            if row.net_return_first_sellable_pct is not None
            and row.settlement_risk_score
            and row.settlement_risk_score > 0
        ]
        metrics = {
            "settlement_failure_rate_pct": cls._metric(
                (
                    round(failures / len(settlement_eligible) * 100, 4)
                    if settlement_eligible
                    else None
                ),
                len(settlement_eligible),
                "no_settlement_eligible_outcomes",
            ),
            "median_return_first_sellable_pct": cls._metric(
                round(median(returns), 4) if returns else None,
                len(returns),
                "no_completed_first_sellable_returns",
            ),
            "average_adverse_movement_before_sellable_pct": cls._metric(
                round(sum(maes) / len(maes), 4) if maes else None,
                len(maes),
                "no_daily_bar_mae_samples",
            ),
            "invalidation_breach_rate_pct": cls._metric(
                (
                    round(
                        sum(row.invalidation_before_sellable is True for row in invalidation_rows)
                        / len(invalidation_rows)
                        * 100,
                        4,
                    )
                    if invalidation_rows
                    else None
                ),
                len(invalidation_rows),
                "no_unambiguous_invalidation_samples",
            ),
            "net_win_rate_pct": cls._metric(
                (
                    round(sum(value > 0 for value in net_returns) / len(net_returns) * 100, 4)
                    if net_returns
                    else None
                ),
                len(net_returns),
                "no_net_return_samples",
            ),
            "profit_factor": cls._metric(
                round(sum(gains) / abs(sum(losses)), 4) if gains and losses else None,
                len(gains) + len(losses),
                "requires_positive_and_negative_net_returns",
            ),
            "expected_return_pct": cls._metric(
                round(sum(net_returns) / len(net_returns), 4) if net_returns else None,
                len(net_returns),
                "no_net_return_samples",
            ),
            "expected_return_per_settlement_risk_point": cls._metric(
                round(sum(risk_adjusted) / len(risk_adjusted), 6)
                if risk_adjusted
                else None,
                len(risk_adjusted),
                "no_returns_with_positive_settlement_risk_score",
            ),
        }
        return {
            "engine_version": rows[0].engine_version if rows else SETTLEMENT_OUTCOME_ENGINE_VERSION,
            "outcome_type": outcome_type,
            "sample_count": len(rows),
            "metrics": metrics,
            "breakdowns": {
                "survivability_bucket": cls._breakdown(rows, "survivability_bucket"),
                "liquidity_bucket": cls._breakdown(rows, "liquidity_bucket"),
                "guarded_action": cls._breakdown(rows, "guarded_action"),
            },
        }

    @staticmethod
    def _metric(value: Optional[float], sample_count: int, reason: str) -> Dict[str, Any]:
        return {
            "value": value,
            "sample_count": sample_count,
            "unavailable_reason": None if value is not None else reason,
        }

    @classmethod
    def _breakdown(
        cls,
        rows: Sequence[SettlementOutcomeRecord],
        field: str,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[float]] = {}
        counts: Dict[str, int] = {}
        for row in rows:
            key = str(getattr(row, field, None) or "unknown")
            counts[key] = counts.get(key, 0) + 1
            if row.net_return_first_sellable_pct is not None:
                grouped.setdefault(key, []).append(float(row.net_return_first_sellable_pct))
        return [
            {
                "value": key,
                "sample_count": counts[key],
                "expected_return_pct": (
                    round(sum(grouped.get(key, [])) / len(grouped[key]), 4)
                    if grouped.get(key)
                    else None
                ),
                "unavailable_reason": (
                    None if grouped.get(key) else "no_net_return_samples"
                ),
            }
            for key in sorted(counts)
        ]
