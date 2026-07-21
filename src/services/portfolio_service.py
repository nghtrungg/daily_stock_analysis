# -*- coding: utf-8 -*-
"""Portfolio service for P0 account/events/snapshot workflow."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.config import get_config
from src.core.trading_calendar import calculate_vn_settlement
from src.repositories.portfolio_repo import (
    DuplicateTradeDedupHashError,
    DuplicateTradeUidError,
    PortfolioBusyError as RepoPortfolioBusyError,
    PortfolioRepository,
)
from src.repositories.decision_signal_trade_link_repo import (
    DecisionSignalTradeLinkRepository,
    SOURCE_RECOMMENDATION_LINK,
)

logger = logging.getLogger(__name__)

PortfolioBusyError = RepoPortfolioBusyError

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency path
    yf = None

EPS = 1e-8
VALID_MARKETS = {"cn", "hk", "us", "jp", "kr", "tw", "vn"}
PARTIAL_VALUATION_MARKETS = {"jp", "kr", "tw", "vn"}
VALID_COST_METHODS = {"fifo", "avg"}
VALID_SIDES = {"buy", "sell"}
VALID_CASH_DIRECTIONS = {"in", "out"}
VALID_CORPORATE_ACTIONS = {"cash_dividend", "split_adjustment"}
PORTFOLIO_FX_REFRESH_DISABLED_REASON = "portfolio_fx_update_disabled"
PORTFOLIO_REALTIME_QUOTE_MAX_WORKERS = 4


def _portfolio_limitations_for_market(market: str) -> List[str]:
    """Return explicit snapshot limitations for markets with partial valuation semantics."""

    if market not in PARTIAL_VALUATION_MARKETS:
        return []
    return [
        "realtime_quote_best_effort",
        "fx_and_cost_basis_partial",
        "sector_and_risk_metrics_limited",
    ]


def _merge_portfolio_limitations(*groups: Iterable[str]) -> List[str]:
    merged: List[str] = []
    seen: Set[str] = set()
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


class PortfolioConflictError(Exception):
    """Raised when request conflicts with existing portfolio state."""


class PortfolioAmbiguousPositionError(ValueError):
    """Raised when account selection is required for a held symbol."""


class PortfolioOversellError(ValueError):
    """Raised when a sell would exceed the available position quantity."""

    def __init__(
        self,
        *,
        symbol: str,
        trade_date: Optional[date],
        requested_quantity: float,
        available_quantity: float,
    ) -> None:
        self.symbol = symbol
        self.trade_date = trade_date
        self.requested_quantity = float(requested_quantity)
        self.available_quantity = max(0.0, float(available_quantity))
        date_hint = f" on {trade_date.isoformat()}" if trade_date is not None else ""
        super().__init__(
            "Oversell detected for "
            f"{symbol}{date_hint}: requested={round(self.requested_quantity, 8)}, "
            f"available={round(self.available_quantity, 8)}"
        )


class PortfolioUnsettledSaleError(PortfolioOversellError):
    """Raised when held shares exist but are not yet sellable."""

    def __init__(
        self,
        *,
        symbol: str,
        trade_date: Optional[date],
        requested_quantity: float,
        held_quantity: float,
        sellable_quantity: float,
        unsettled_quantity: float,
        next_sellable_at: Optional[datetime],
    ) -> None:
        self.held_quantity = max(0.0, float(held_quantity))
        self.sellable_quantity = max(0.0, float(sellable_quantity))
        self.unsettled_quantity = max(0.0, float(unsettled_quantity))
        self.next_sellable_at = next_sellable_at
        super().__init__(
            symbol=symbol,
            trade_date=trade_date,
            requested_quantity=requested_quantity,
            available_quantity=sellable_quantity,
        )
        next_hint = (
            self.next_sellable_at.isoformat()
            if self.next_sellable_at is not None
            else "unknown"
        )
        self.args = (
            "Unsettled sale rejected for "
            f"{symbol}: requested={round(self.requested_quantity, 8)}, "
            f"held={round(self.held_quantity, 8)}, "
            f"sellable={round(self.sellable_quantity, 8)}, "
            f"unsettled={round(self.unsettled_quantity, 8)}, "
            f"next_sellable_at={next_hint}",
        )


@dataclass
class _AvgState:
    quantity: float = 0.0
    total_cost: float = 0.0


@dataclass(frozen=True)
class _ResolvedPositionPrice:
    price: float
    source: str
    price_date: Optional[date]
    is_stale: bool
    is_available: bool
    provider: Optional[str] = None


class PortfolioService:
    """Business logic for account CRUD, event writes, and snapshot replay."""

    def __init__(
        self,
        repo: Optional[PortfolioRepository] = None,
        signal_trade_link_repo: Optional[DecisionSignalTradeLinkRepository] = None,
    ):
        self.repo = repo or PortfolioRepository()
        self.signal_trade_link_repo = (
            signal_trade_link_repo
            or DecisionSignalTradeLinkRepository(self.repo.db)
        )

    # ------------------------------------------------------------------
    # Account CRUD
    # ------------------------------------------------------------------
    def create_account(
        self,
        *,
        name: str,
        broker: Optional[str],
        market: str,
        base_currency: str,
        owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        name_norm = (name or "").strip()
        if not name_norm:
            raise ValueError("name is required")
        market_norm = self._normalize_market(market)
        base_currency_norm = self._normalize_currency(base_currency)
        row = self.repo.create_account(
            name=name_norm,
            broker=(broker or "").strip() or None,
            market=market_norm,
            base_currency=base_currency_norm,
            owner_id=(owner_id or "").strip() or None,
        )
        return self._account_to_dict(row)

    def list_accounts(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        rows = self.repo.list_accounts(include_inactive=include_inactive)
        return [self._account_to_dict(r) for r in rows]

    def update_account(
        self,
        account_id: int,
        *,
        name: Optional[str] = None,
        broker: Optional[str] = None,
        market: Optional[str] = None,
        base_currency: Optional[str] = None,
        owner_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        fields: Dict[str, Any] = {}
        if name is not None:
            name_norm = name.strip()
            if not name_norm:
                raise ValueError("name is required")
            fields["name"] = name_norm
        if broker is not None:
            fields["broker"] = broker.strip() or None
        if market is not None:
            fields["market"] = self._normalize_market(market)
        if base_currency is not None:
            fields["base_currency"] = self._normalize_currency(base_currency)
        if owner_id is not None:
            fields["owner_id"] = owner_id.strip() or None
        if is_active is not None:
            fields["is_active"] = bool(is_active)
        if not fields:
            raise ValueError("No fields provided for update")

        row = self.repo.update_account(account_id, fields)
        if row is None:
            return None
        return self._account_to_dict(row)

    def deactivate_account(self, account_id: int) -> bool:
        return self.repo.deactivate_account(account_id)

    # ------------------------------------------------------------------
    # Event writes
    # ------------------------------------------------------------------
    def record_trade(
        self,
        *,
        account_id: int,
        symbol: str,
        trade_date: date,
        side: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        trade_uid: Optional[str] = None,
        dedup_hash: Optional[str] = None,
        note: Optional[str] = None,
        executed_at: Optional[datetime] = None,
        source_decision_signal_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        side_norm = (side or "").strip().lower()
        if side_norm not in VALID_SIDES:
            raise ValueError("side must be buy or sell")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be > 0")
        if fee < 0 or tax < 0:
            raise ValueError("fee and tax must be >= 0")
        symbol_norm = self._normalize_symbol_for_storage(symbol)
        if not symbol_norm:
            raise ValueError("symbol is required")
        trade_uid_norm = (trade_uid or "").strip() or None
        dedup_hash_norm = (dedup_hash or "").strip() or None
        try:
            with self.repo.portfolio_write_session() as session:
                account = self._require_active_account_in_session(session=session, account_id=account_id)
                market_norm = self._normalize_market(market or account.market)
                if market_norm == "vn" and not (symbol or "").strip().upper().endswith(".VN"):
                    raise ValueError("Vietnam portfolio symbols must use an explicit .VN suffix")
                currency_norm = self._normalize_currency(currency or self._default_currency_for_market(market_norm))
                source_signal = self._validate_source_decision_signal(
                    session=session,
                    source_decision_signal_id=source_decision_signal_id,
                    trade_side=side_norm,
                    trade_symbol=symbol_norm,
                    trade_market=market_norm,
                )
                stored_execution_at, effective_execution_at, execution_inferred = (
                    self._normalize_trade_execution(
                        trade_date=trade_date,
                        executed_at=executed_at,
                    )
                )
                self._validate_trade_identity(
                    account_id=account_id,
                    trade_uid=trade_uid_norm,
                    dedup_hash=dedup_hash_norm,
                    session=session,
                    )
                if side_norm == "sell":
                    self._validate_sell_quantity(
                        account_id=account_id,
                        symbol=symbol,
                        market=market_norm,
                        currency=currency_norm,
                        trade_date=trade_date,
                        sale_at=effective_execution_at,
                        quantity=float(quantity),
                        session=session,
                    )
                row = self.repo.add_trade_in_session(
                    session=session,
                    account_id=account_id,
                    trade_uid=trade_uid_norm,
                    symbol=symbol_norm,
                    market=market_norm,
                    currency=currency_norm,
                    trade_date=trade_date,
                    executed_at=stored_execution_at,
                    side=side_norm,
                    quantity=float(quantity),
                    price=float(price),
                    fee=float(fee),
                    tax=float(tax),
                    note=(note or "").strip() or None,
                    dedup_hash=dedup_hash_norm,
                )
                if side_norm == "buy" and market_norm == "vn":
                    settlement = calculate_vn_settlement(
                        effective_execution_at,
                        settlement_sessions=2,
                    )
                    settlement_warnings = list(settlement.warnings)
                    if execution_inferred:
                        settlement_warnings.append(
                            "execution_time_inferred_from_trade_date"
                        )
                    self.repo.add_trade_settlement_in_session(
                        session=session,
                        trade_id=int(row.id),
                        settlement_date=settlement.settlement_date,
                        estimated_sellable_at=self._to_utc_naive(
                            settlement.estimated_sellable_at
                        ),
                        actual_sellable_at=None,
                        calendar_version=settlement.calendar_version,
                        policy_version=settlement.policy_version,
                        calculation_status=settlement.calculation_status.value,
                        warnings_json=json.dumps(
                            settlement_warnings,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                if source_signal is not None:
                    self.signal_trade_link_repo.create_in_session(
                        session=session,
                        signal_id=int(source_signal.id),
                        trade_id=int(row.id),
                        link_type=SOURCE_RECOMMENDATION_LINK,
                    )
                return {
                    "id": int(row.id),
                    "source_decision_signal_id": (
                        int(source_signal.id) if source_signal is not None else None
                    ),
                    "link_type": (
                        SOURCE_RECOMMENDATION_LINK
                        if source_signal is not None
                        else None
                    ),
                }
        except (DuplicateTradeUidError, DuplicateTradeDedupHashError) as exc:
            raise PortfolioConflictError(str(exc)) from exc

    def record_cash_ledger(
        self,
        *,
        account_id: int,
        event_date: date,
        direction: str,
        amount: float,
        currency: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        direction_norm = (direction or "").strip().lower()
        if direction_norm not in VALID_CASH_DIRECTIONS:
            raise ValueError("direction must be in or out")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        with self.repo.portfolio_write_session() as session:
            account = self._require_active_account_in_session(session=session, account_id=account_id)
            currency_norm = self._normalize_currency(currency or account.base_currency)
            row = self.repo.add_cash_ledger_in_session(
                session=session,
                account_id=account_id,
                event_date=event_date,
                direction=direction_norm,
                amount=float(amount),
                currency=currency_norm,
                note=(note or "").strip() or None,
            )
            return {"id": int(row.id)}

    def record_corporate_action(
        self,
        *,
        account_id: int,
        symbol: str,
        effective_date: date,
        action_type: str,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        cash_dividend_per_share: Optional[float] = None,
        split_ratio: Optional[float] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        action_type_norm = (action_type or "").strip().lower()
        if action_type_norm not in VALID_CORPORATE_ACTIONS:
            raise ValueError("action_type must be cash_dividend or split_adjustment")

        if action_type_norm == "cash_dividend":
            if cash_dividend_per_share is None or cash_dividend_per_share < 0:
                raise ValueError("cash_dividend_per_share must be >= 0 for cash_dividend")
        if action_type_norm == "split_adjustment":
            if split_ratio is None or split_ratio <= 0:
                raise ValueError("split_ratio must be > 0 for split_adjustment")
        with self.repo.portfolio_write_session() as session:
            account = self._require_active_account_in_session(session=session, account_id=account_id)
            market_norm = self._normalize_market(market or account.market)
            currency_norm = self._normalize_currency(currency or self._default_currency_for_market(market_norm))
            symbol_norm = self._normalize_symbol_for_storage(symbol)
            if not symbol_norm:
                raise ValueError("symbol is required")
            row = self.repo.add_corporate_action_in_session(
                session=session,
                account_id=account_id,
                symbol=symbol_norm,
                market=market_norm,
                currency=currency_norm,
                effective_date=effective_date,
                action_type=action_type_norm,
                cash_dividend_per_share=cash_dividend_per_share,
                split_ratio=split_ratio,
                note=(note or "").strip() or None,
            )
            return {"id": int(row.id)}

    def delete_trade_event(self, trade_id: int) -> bool:
        with self.repo.portfolio_write_session() as session:
            return self.repo.delete_trade_in_session(session=session, trade_id=trade_id)

    def delete_cash_ledger_event(self, entry_id: int) -> bool:
        with self.repo.portfolio_write_session() as session:
            return self.repo.delete_cash_ledger_in_session(session=session, entry_id=entry_id)

    def delete_corporate_action_event(self, action_id: int) -> bool:
        with self.repo.portfolio_write_session() as session:
            return self.repo.delete_corporate_action_in_session(session=session, action_id=action_id)

    def list_trade_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        symbol_filters: Optional[List[str]] = None
        if symbol is not None and symbol.strip():
            symbol_filters = self._build_symbol_filter_values(symbol)
            if not symbol_filters:
                raise ValueError("symbol is invalid")

        side_norm: Optional[str] = None
        if side is not None and side.strip():
            side_norm = side.strip().lower()
            if side_norm not in VALID_SIDES:
                raise ValueError("side must be buy or sell")

        rows, total = self.repo.query_trades(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbols=symbol_filters,
            side=side_norm,
            page=page,
            page_size=page_size,
        )
        links = self.signal_trade_link_repo.links_by_trade_ids(
            int(row.id) for row in rows
        )
        return {
            "items": [
                self._trade_row_to_dict(row, source_link=links.get(int(row.id)))
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_cash_ledger_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        direction: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        direction_norm: Optional[str] = None
        if direction is not None and direction.strip():
            direction_norm = direction.strip().lower()
            if direction_norm not in VALID_CASH_DIRECTIONS:
                raise ValueError("direction must be in or out")

        rows, total = self.repo.query_cash_ledger(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            direction=direction_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._cash_ledger_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_corporate_action_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        symbol: Optional[str] = None,
        action_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        symbol_filters: Optional[List[str]] = None
        if symbol is not None and symbol.strip():
            symbol_filters = self._build_symbol_filter_values(symbol)
            if not symbol_filters:
                raise ValueError("symbol is invalid")

        action_norm: Optional[str] = None
        if action_type is not None and action_type.strip():
            action_norm = action_type.strip().lower()
            if action_norm not in VALID_CORPORATE_ACTIONS:
                raise ValueError("action_type must be cash_dividend or split_adjustment")

        rows, total = self.repo.query_corporate_actions(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbols=symbol_filters,
            action_type=action_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._corporate_action_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # Snapshot replay
    # ------------------------------------------------------------------
    def get_portfolio_snapshot(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        include_realtime: bool = True,
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        method = self._normalize_cost_method(cost_method)

        if account_id is not None:
            account = self._require_active_account(account_id)
            account_rows = [account]
        else:
            account_rows = self.repo.list_accounts(include_inactive=False)

        accounts_payload: List[Dict[str, Any]] = []
        # Vietnam-first installations aggregate accounts in the local currency.
        aggregate_currency = "VND"
        aggregate = {
            "total_cash": 0.0,
            "total_market_value": 0.0,
            "total_equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "fee_total": 0.0,
            "tax_total": 0.0,
            "fx_stale": False,
            "limitations": [],
        }

        for account in account_rows:
            account_snapshot = self._replay_account(
                account=account,
                as_of_date=as_of_date,
                cost_method=method,
                include_realtime=include_realtime,
            )

            self.repo.replace_positions_lots_and_snapshot(
                account_id=account.id,
                snapshot_date=as_of_date,
                cost_method=method,
                base_currency=account.base_currency,
                total_cash=account_snapshot["total_cash"],
                total_market_value=account_snapshot["total_market_value"],
                total_equity=account_snapshot["total_equity"],
                unrealized_pnl=account_snapshot["unrealized_pnl"],
                realized_pnl=account_snapshot["realized_pnl"],
                fee_total=account_snapshot["fee_total"],
                tax_total=account_snapshot["tax_total"],
                fx_stale=account_snapshot["fx_stale"],
                payload=json.dumps(account_snapshot["payload"], ensure_ascii=False),
                positions=account_snapshot["positions_cache"],
                lots=account_snapshot["lots_cache"],
                valuation_currency=account.base_currency,
            )

            accounts_payload.append(account_snapshot["public"])
            aggregate["limitations"] = _merge_portfolio_limitations(
                aggregate["limitations"],
                account_snapshot["public"].get("limitations", []),
            )

            cash_cny, stale_cash, _ = self._convert_amount(
                amount=account_snapshot["total_cash"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            mv_cny, stale_mv, _ = self._convert_amount(
                amount=account_snapshot["total_market_value"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            eq_cny, stale_eq, _ = self._convert_amount(
                amount=account_snapshot["total_equity"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            realized_cny, stale_realized, _ = self._convert_amount(
                amount=account_snapshot["realized_pnl"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            unrealized_cny, stale_unrealized, _ = self._convert_amount(
                amount=account_snapshot["unrealized_pnl"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            fee_cny, stale_fee, _ = self._convert_amount(
                amount=account_snapshot["fee_total"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            tax_cny, stale_tax, _ = self._convert_amount(
                amount=account_snapshot["tax_total"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )

            aggregate["total_cash"] += cash_cny
            aggregate["total_market_value"] += mv_cny
            aggregate["total_equity"] += eq_cny
            aggregate["realized_pnl"] += realized_cny
            aggregate["unrealized_pnl"] += unrealized_cny
            aggregate["fee_total"] += fee_cny
            aggregate["tax_total"] += tax_cny
            aggregate["fx_stale"] = aggregate["fx_stale"] or any(
                [
                    stale_cash,
                    stale_mv,
                    stale_eq,
                    stale_realized,
                    stale_unrealized,
                    stale_fee,
                    stale_tax,
                ]
            )

        return {
            "as_of": as_of_date.isoformat(),
            "cost_method": method,
            "currency": aggregate_currency,
            "account_count": len(account_rows),
            "total_cash": round(aggregate["total_cash"], 6),
            "total_market_value": round(aggregate["total_market_value"], 6),
            "total_equity": round(aggregate["total_equity"], 6),
            "realized_pnl": round(aggregate["realized_pnl"], 6),
            "unrealized_pnl": round(aggregate["unrealized_pnl"], 6),
            "fee_total": round(aggregate["fee_total"], 6),
            "tax_total": round(aggregate["tax_total"], 6),
            "fx_stale": aggregate["fx_stale"],
            "data_quality": "partial" if aggregate["limitations"] else "ok",
            "limitations": aggregate["limitations"],
            "accounts": accounts_payload,
        }

    def get_position_settlement(
        self,
        *,
        symbol: str,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
    ) -> Optional[Dict[str, Any]]:
        """Return an on-demand settlement projection for one held position."""
        as_of_date = as_of or date.today()
        method = self._normalize_cost_method(cost_method)
        target = self._normalize_symbol_for_position(symbol)
        if not target:
            raise ValueError("symbol must not be empty")

        accounts = (
            [self._require_active_account(account_id)]
            if account_id is not None
            else self.repo.list_accounts(include_inactive=False)
        )
        as_of_at = datetime.combine(
            as_of_date,
            time.max,
            tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
        )
        matches: List[Dict[str, Any]] = []
        for account in accounts:
            replay = self._replay_account(
                account=account,
                as_of_date=as_of_date,
                cost_method=method,
                include_realtime=False,
            )
            position = next(
                (
                    item
                    for item in replay["positions_cache"]
                    if self._normalize_symbol_for_position(item["symbol"]) == target
                    and float(item.get("quantity") or 0.0) > EPS
                ),
                None,
            )
            if position is None:
                continue
            lots = [
                item
                for item in replay["lots_cache"]
                if self._normalize_symbol_for_position(item["symbol"]) == target
                and float(item.get("remaining_quantity") or 0.0) > EPS
            ]
            warnings = sorted(
                {
                    str(warning)
                    for lot in lots
                    for warning in (lot.get("warnings") or [])
                    if str(warning)
                }
            )
            matches.append(
                {
                    "account_id": int(account.id),
                    "symbol": position["symbol"],
                    "as_of": as_of_at.isoformat(),
                    "total_quantity": float(position["quantity"]),
                    "sellable_quantity": float(position["sellable_quantity"]),
                    "unsettled_quantity": float(position["unsettled_quantity"]),
                    "settlement_state": position["settlement_state"],
                    "next_sellable_at": position.get("next_sellable_at"),
                    "calculation_status": position["settlement_calculation_status"],
                    "warnings": warnings,
                    "lots": [
                        {
                            "source_trade_id": (
                                int(lot["source_trade_id"])
                                if lot.get("source_trade_id") is not None
                                else None
                            ),
                            "acquired_at": (
                                lot["acquired_at"].isoformat()
                                if lot.get("acquired_at") is not None
                                else None
                            ),
                            "remaining_quantity": round(float(lot["remaining_quantity"]), 8),
                            "unit_cost": round(float(lot["unit_cost"]), 8),
                            "settlement_state": self._lot_settlement_state(
                                lot,
                                as_of_at=as_of_at,
                            ),
                            "estimated_sellable_at": (
                                lot["estimated_sellable_at"].isoformat()
                                if lot.get("estimated_sellable_at") is not None
                                else None
                            ),
                            "actual_sellable_at": (
                                lot["actual_sellable_at"].isoformat()
                                if lot.get("actual_sellable_at") is not None
                                else None
                            ),
                            "calculation_status": str(
                                lot.get("calendar_status") or "unknown"
                            ),
                            "warnings": list(lot.get("warnings") or []),
                        }
                        for lot in lots
                    ],
                }
            )

        if account_id is None and len(matches) > 1:
            raise PortfolioAmbiguousPositionError(
                f"{target} is held in multiple accounts; pass account_id"
            )
        return matches[0] if matches else None

    def refresh_fx_rates(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Refresh account FX pairs online with stale fallback when fetch fails."""
        as_of_date = as_of or date.today()
        config = get_config()
        refresh_enabled = bool(getattr(config, "portfolio_fx_update_enabled", True))
        if account_id is not None:
            account_rows = [self._require_active_account(account_id)]
        else:
            account_rows = self.repo.list_accounts(include_inactive=False)

        summary = {
            "as_of": as_of_date.isoformat(),
            "account_count": len(account_rows),
            "refresh_enabled": refresh_enabled,
            "disabled_reason": None if refresh_enabled else PORTFOLIO_FX_REFRESH_DISABLED_REASON,
            "pair_count": 0,
            "updated_count": 0,
            "stale_count": 0,
            "error_count": 0,
        }
        for account in account_rows:
            item = self._refresh_account_fx_rates(
                account=account,
                as_of_date=as_of_date,
                refresh_enabled=refresh_enabled,
            )
            summary["pair_count"] += item["pair_count"]
            summary["updated_count"] += item["updated_count"]
            summary["stale_count"] += item["stale_count"]
            summary["error_count"] += item["error_count"]
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate_trade_identity(
        self,
        *,
        account_id: int,
        trade_uid: Optional[str],
        dedup_hash: Optional[str],
        session: Optional[Any] = None,
    ) -> None:
        if trade_uid and self._has_trade_uid(account_id=account_id, trade_uid=trade_uid, session=session):
            raise PortfolioConflictError(f"Duplicate trade_uid for account_id={account_id}: {trade_uid}")
        if dedup_hash and self._has_trade_dedup_hash(account_id=account_id, dedup_hash=dedup_hash, session=session):
            raise PortfolioConflictError(f"Duplicate dedup_hash for account_id={account_id}: {dedup_hash}")

    def _validate_sell_quantity(
        self,
        *,
        account_id: int,
        symbol: str,
        market: str,
        currency: str,
        trade_date: date,
        sale_at: datetime,
        quantity: float,
        session: Optional[Any] = None,
    ) -> None:
        key = (
            self._normalize_symbol_for_position(symbol),
            self._normalize_market(market),
            self._normalize_currency(currency),
        )
        if market != "vn":
            available_quantity = self._calculate_available_quantity(
                account_id=account_id,
                key=key,
                as_of_date=trade_date,
                session=session,
            )
            if available_quantity + EPS < quantity:
                raise PortfolioOversellError(
                    symbol=key[0],
                    trade_date=trade_date,
                    requested_quantity=quantity,
                    available_quantity=available_quantity,
                )
            return

        inventory = self._calculate_settlement_inventory(
            account_id=account_id,
            key=key,
            as_of_date=trade_date,
            as_of_at=sale_at,
            session=session,
        )
        if inventory["held_quantity"] + EPS < quantity:
            raise PortfolioOversellError(
                symbol=key[0],
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=inventory["held_quantity"],
            )
        if inventory["sellable_quantity"] + EPS < quantity:
            raise PortfolioUnsettledSaleError(
                symbol=key[0],
                trade_date=trade_date,
                requested_quantity=quantity,
                held_quantity=inventory["held_quantity"],
                sellable_quantity=inventory["sellable_quantity"],
                unsettled_quantity=inventory["unsettled_quantity"],
                next_sellable_at=inventory["next_sellable_at"],
            )

    def _calculate_available_quantity(
        self,
        *,
        account_id: int,
        key: Tuple[str, str, str],
        as_of_date: date,
        session: Optional[Any] = None,
    ) -> float:
        if session is None:
            trades = self.repo.list_trades(account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions(account_id, as_of=as_of_date)
        else:
            trades = self.repo.list_trades_in_session(session=session, account_id=account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions_in_session(
                session=session,
                account_id=account_id,
                as_of=as_of_date,
            )

        events = []
        for row in corporate_actions:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("corp", row.effective_date, row.id, row))
        for row in trades:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("trade", row.trade_date, row.id, row))

        # Quantity validation only depends on position-changing events for one symbol.
        # Cash ledger entries do not affect shares held, so we keep the same corp->trade
        # ordering as full replay without pulling unrelated cash events into this path.
        event_priority = {"corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        quantity_held = 0.0
        for event_type, event_date, _, event in events:
            if event_type == "corp":
                action_type = (event.action_type or "").strip().lower()
                if action_type != "split_adjustment":
                    continue
                split_ratio = float(event.split_ratio or 0.0)
                if split_ratio <= 0:
                    raise ValueError(f"Invalid split_ratio for {key[0]}")
                if abs(split_ratio - 1.0) <= EPS:
                    continue
                quantity_held *= split_ratio
                continue

            qty = float(event.quantity or 0.0)
            if qty <= 0:
                raise ValueError(f"Invalid trade quantity for {key[0]}")
            side = (event.side or "").strip().lower()
            if side == "buy":
                quantity_held += qty
                continue
            if side != "sell":
                raise ValueError(f"Unsupported trade side: {event.side}")
            if quantity_held + EPS < qty:
                raise PortfolioOversellError(
                    symbol=key[0],
                    trade_date=event_date,
                    requested_quantity=qty,
                    available_quantity=quantity_held,
                )
            quantity_held -= qty
            if quantity_held <= EPS:
                quantity_held = 0.0

        return quantity_held

    def _calculate_settlement_inventory(
        self,
        *,
        account_id: int,
        key: Tuple[str, str, str],
        as_of_date: date,
        as_of_at: datetime,
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if session is None:
            trades = self.repo.list_trades(account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions(
                account_id,
                as_of=as_of_date,
            )
            settlements = self.repo.list_trade_settlements(
                trade_ids=[row.id for row in trades],
            )
        else:
            trades = self.repo.list_trades_in_session(
                session=session,
                account_id=account_id,
                as_of=as_of_date,
            )
            corporate_actions = self.repo.list_corporate_actions_in_session(
                session=session,
                account_id=account_id,
                as_of=as_of_date,
            )
            settlements = self.repo.list_trade_settlements_in_session(
                session=session,
                trade_ids=[row.id for row in trades],
            )

        events = []
        for row in corporate_actions:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("corp", row.effective_date, row.id, row))
        for row in trades:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("trade", row.trade_date, row.id, row))
        event_priority = {"corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        lots: List[Dict[str, Any]] = []
        for event_type, event_date, _, event in events:
            if event_type == "corp":
                if (event.action_type or "").strip().lower() != "split_adjustment":
                    continue
                split_ratio = float(event.split_ratio or 0.0)
                if split_ratio <= 0:
                    raise ValueError(f"Invalid split_ratio for {key[0]}")
                for lot in lots:
                    lot["remaining_quantity"] *= split_ratio
                continue

            quantity = float(event.quantity or 0.0)
            side = (event.side or "").strip().lower()
            if side == "buy":
                lot = self._settlement_lot_metadata(
                    trade=event,
                    settlement=settlements.get(int(event.id)),
                    market=key[1],
                )
                lot["remaining_quantity"] = quantity
                lots.append(lot)
                continue
            if side != "sell":
                raise ValueError(f"Unsupported trade side: {event.side}")
            _, historical_sale_at, _ = self._normalize_trade_execution(
                trade_date=event.trade_date,
                executed_at=self._from_utc_naive(event.executed_at),
            )
            self._consume_settlement_lots(
                lots,
                quantity,
                symbol=key[0],
                trade_date=event_date,
                sale_at=historical_sale_at,
            )

        return self._summarize_settlement_lots(lots, as_of_at=as_of_at)

    def _replay_account(
        self,
        *,
        account: Any,
        as_of_date: date,
        cost_method: str,
        include_realtime: bool,
    ) -> Dict[str, Any]:
        trades = self.repo.list_trades(account.id, as_of=as_of_date)
        settlements = self.repo.list_trade_settlements(
            trade_ids=[row.id for row in trades],
        )
        cash_ledger = self.repo.list_cash_ledger(account.id, as_of=as_of_date)
        corporate_actions = self.repo.list_corporate_actions(account.id, as_of=as_of_date)

        events = []
        for row in cash_ledger:
            events.append(("cash", row.event_date, row.id, row))
        for row in trades:
            events.append(("trade", row.trade_date, row.id, row))
        for row in corporate_actions:
            events.append(("corp", row.effective_date, row.id, row))

        # Same-day deterministic ordering: cash -> corporate action -> trade.
        event_priority = {"cash": 0, "corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        cash_balances: Dict[str, float] = defaultdict(float)
        fees_total_base = 0.0
        taxes_total_base = 0.0
        realized_pnl_base = 0.0
        fx_stale = False

        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        avg_state: Dict[Tuple[str, str, str], _AvgState] = defaultdict(_AvgState)
        avg_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

        for event_type, event_date, _, event in events:
            if event_type == "cash":
                currency = self._normalize_currency(event.currency)
                amount = float(event.amount or 0.0)
                if event.direction == "in":
                    cash_balances[currency] += amount
                elif event.direction == "out":
                    cash_balances[currency] -= amount
                else:
                    raise ValueError(f"Unsupported cash direction: {event.direction}")
                continue

            if event_type == "trade":
                key = (
                    self._normalize_symbol_for_position(event.symbol),
                    self._normalize_market(event.market),
                    self._normalize_currency(event.currency),
                )
                qty = float(event.quantity or 0.0)
                price = float(event.price or 0.0)
                fee = float(event.fee or 0.0)
                tax = float(event.tax or 0.0)
                if qty <= 0 or price <= 0:
                    raise ValueError(f"Invalid trade quantity or price for {event.symbol}")

                gross = qty * price
                side = (event.side or "").lower().strip()
                if side == "buy":
                    cash_balances[key[2]] -= (gross + fee + tax)
                    settlement_lot = self._settlement_lot_metadata(
                        trade=event,
                        settlement=settlements.get(int(event.id)),
                        market=key[1],
                    )
                    settlement_lot.update(
                        {
                            "symbol": key[0],
                            "market": key[1],
                            "currency": key[2],
                            "open_date": event_date,
                            "remaining_quantity": qty,
                            "unit_cost": (gross + fee + tax) / qty,
                            "source_trade_id": event.id,
                        }
                    )
                    if cost_method == "fifo":
                        fifo_lots[key].append(settlement_lot)
                    else:
                        avg_lots[key].append(settlement_lot)
                        state = avg_state[key]
                        state.quantity += qty
                        state.total_cost += (gross + fee + tax)
                elif side == "sell":
                    cash_balances[key[2]] += (gross - fee - tax)
                    proceeds_net = gross - fee - tax
                    _, sale_at, _ = self._normalize_trade_execution(
                        trade_date=event.trade_date,
                        executed_at=self._from_utc_naive(event.executed_at),
                    )
                    if cost_method == "fifo":
                        cost_basis = self._consume_fifo_lots(
                            fifo_lots[key],
                            qty,
                            key[0],
                            event_date,
                            sale_at=sale_at,
                        )
                    else:
                        self._consume_settlement_lots(
                            avg_lots[key],
                            qty,
                            symbol=key[0],
                            trade_date=event_date,
                            sale_at=sale_at,
                        )
                        cost_basis = self._consume_avg_position(
                            avg_state[key],
                            qty,
                            key[0],
                            event_date,
                        )
                    realized_local = proceeds_net - cost_basis
                    realized_base, stale_realized, _ = self._convert_amount(
                        amount=realized_local,
                        from_currency=key[2],
                        to_currency=account.base_currency,
                        as_of_date=event_date,
                    )
                    realized_pnl_base += realized_base
                    fx_stale = fx_stale or stale_realized
                else:
                    raise ValueError(f"Unsupported trade side: {event.side}")

                fee_base, stale_fee, _ = self._convert_amount(
                    amount=fee,
                    from_currency=key[2],
                    to_currency=account.base_currency,
                    as_of_date=event_date,
                )
                tax_base, stale_tax, _ = self._convert_amount(
                    amount=tax,
                    from_currency=key[2],
                    to_currency=account.base_currency,
                    as_of_date=event_date,
                )
                fees_total_base += fee_base
                taxes_total_base += tax_base
                fx_stale = fx_stale or stale_fee or stale_tax
                continue

            if event_type == "corp":
                key = (
                    self._normalize_symbol_for_position(event.symbol),
                    self._normalize_market(event.market),
                    self._normalize_currency(event.currency),
                )
                action_type = (event.action_type or "").strip().lower()
                if action_type == "cash_dividend":
                    per_share = float(event.cash_dividend_per_share or 0.0)
                    if per_share <= 0:
                        continue
                    qty_held = self._held_quantity(
                        key=key,
                        cost_method=cost_method,
                        fifo_lots=fifo_lots,
                        avg_state=avg_state,
                    )
                    if qty_held > EPS:
                        cash_balances[key[2]] += qty_held * per_share
                elif action_type == "split_adjustment":
                    split_ratio = float(event.split_ratio or 0.0)
                    if split_ratio <= 0:
                        raise ValueError(f"Invalid split_ratio for {event.symbol}")
                    if abs(split_ratio - 1.0) <= EPS:
                        continue
                    if cost_method == "fifo":
                        for lot in fifo_lots[key]:
                            lot["remaining_quantity"] *= split_ratio
                            lot["unit_cost"] /= split_ratio
                    else:
                        for lot in avg_lots[key]:
                            lot["remaining_quantity"] *= split_ratio
                            lot["unit_cost"] /= split_ratio
                        state = avg_state[key]
                        state.quantity *= split_ratio
                else:
                    raise ValueError(f"Unsupported corporate action type: {event.action_type}")

        position_rows, lot_rows, market_value_base, total_cost_base, stale_pos = self._build_positions(
            account=account,
            as_of_date=as_of_date,
            cost_method=cost_method,
            fifo_lots=fifo_lots,
            avg_state=avg_state,
            avg_lots=avg_lots,
            include_realtime=include_realtime,
        )
        fx_stale = fx_stale or stale_pos

        total_cash_base = 0.0
        for currency, amount in cash_balances.items():
            converted, stale, _ = self._convert_amount(
                amount=amount,
                from_currency=currency,
                to_currency=account.base_currency,
                as_of_date=as_of_date,
            )
            total_cash_base += converted
            fx_stale = fx_stale or stale

        unrealized_pnl_base = market_value_base - total_cost_base
        total_equity_base = total_cash_base + market_value_base
        position_limitations = [
            limitation
            for position in position_rows
            for limitation in position.get("limitations", [])
        ]
        limitations = _merge_portfolio_limitations(
            _portfolio_limitations_for_market(account.market),
            position_limitations,
        )

        public_positions = [
            {
                field: value
                for field, value in position.items()
                if field != "next_sellable_at_utc"
            }
            for position in position_rows
        ]
        account_payload = {
            "account_id": account.id,
            "account_name": account.name,
            "owner_id": account.owner_id,
            "broker": account.broker,
            "market": account.market,
            "base_currency": account.base_currency,
            "as_of": as_of_date.isoformat(),
            "cost_method": cost_method,
            "total_cash": round(total_cash_base, 6),
            "total_market_value": round(market_value_base, 6),
            "total_equity": round(total_equity_base, 6),
            "realized_pnl": round(realized_pnl_base, 6),
            "unrealized_pnl": round(unrealized_pnl_base, 6),
            "fee_total": round(fees_total_base, 6),
            "tax_total": round(taxes_total_base, 6),
            "fx_stale": fx_stale,
            "data_quality": "partial" if limitations else "ok",
            "limitations": limitations,
            "positions": public_positions,
        }

        return {
            "public": account_payload,
            "payload": account_payload,
            "positions_cache": position_rows,
            "lots_cache": lot_rows,
            "total_cash": float(total_cash_base),
            "total_market_value": float(market_value_base),
            "total_equity": float(total_equity_base),
            "realized_pnl": float(realized_pnl_base),
            "unrealized_pnl": float(unrealized_pnl_base),
            "fee_total": float(fees_total_base),
            "tax_total": float(taxes_total_base),
            "fx_stale": fx_stale,
        }

    def _build_positions(
        self,
        *,
        account: Any,
        as_of_date: date,
        cost_method: str,
        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
        avg_state: Dict[Tuple[str, str, str], _AvgState],
        avg_lots: Optional[
            Dict[Tuple[str, str, str], List[Dict[str, Any]]]
        ] = None,
        include_realtime: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, float, bool]:
        if avg_lots is None:
            avg_lots = defaultdict(list)
        position_rows: List[Dict[str, Any]] = []
        lot_rows: List[Dict[str, Any]] = []
        market_value_base = 0.0
        total_cost_base = 0.0
        fx_stale = False

        keys: Iterable[Tuple[str, str, str]]
        if cost_method == "fifo":
            keys = list(fifo_lots.keys())
        else:
            keys = list(avg_state.keys())

        active_symbols: List[str] = []
        if include_realtime and as_of_date == date.today():
            for key in sorted(keys):
                symbol, _, _ = key
                if cost_method == "fifo":
                    qty = sum(
                        float(lot["remaining_quantity"])
                        for lot in fifo_lots[key]
                        if lot["remaining_quantity"] > EPS
                    )
                else:
                    qty = float(avg_state[key].quantity)
                if qty > EPS:
                    active_symbols.append(symbol)
        realtime_prices = (
            self._prefetch_realtime_position_prices(active_symbols)
            if active_symbols
            else None
        )

        for key in sorted(keys):
            symbol, market, currency = key

            if cost_method == "fifo":
                active_lots = [lot for lot in fifo_lots[key] if lot["remaining_quantity"] > EPS]
                qty = sum(float(lot["remaining_quantity"]) for lot in active_lots)
                if qty <= EPS:
                    continue
                total_cost = sum(float(lot["remaining_quantity"]) * float(lot["unit_cost"]) for lot in active_lots)
                avg_cost = total_cost / qty
                lot_rows.extend(active_lots)
            else:
                state = avg_state[key]
                qty = float(state.quantity)
                total_cost = float(state.total_cost)
                if qty <= EPS:
                    continue
                avg_cost = total_cost / qty
                active_lots = [
                    lot for lot in avg_lots[key]
                    if lot["remaining_quantity"] > EPS
                ]
                lot_rows.extend(active_lots)

            as_of_at = datetime.combine(
                as_of_date,
                time.max,
                tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
            )
            settlement_summary = self._summarize_settlement_lots(
                active_lots,
                as_of_at=as_of_at,
            )
            for lot in active_lots:
                lot["settlement_state"] = self._lot_settlement_state(
                    lot,
                    as_of_at=as_of_at,
                )

            price_info = self._resolve_position_price(
                symbol=symbol,
                as_of_date=as_of_date,
                realtime_prices=realtime_prices,
                include_realtime=include_realtime,
            )
            last_price = price_info.price
            limitations = _portfolio_limitations_for_market(market)

            if price_info.is_available:
                local_market_value = qty * float(last_price)
                market_base, stale_market, _ = self._convert_amount(
                    amount=local_market_value,
                    from_currency=currency,
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                cost_base, stale_cost, _ = self._convert_amount(
                    amount=total_cost,
                    from_currency=currency,
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                unrealized_base = market_base - cost_base
                fx_stale = fx_stale or stale_market or stale_cost
            else:
                market_base = 0.0
                cost_base = 0.0
                unrealized_base = 0.0

            unrealized_pct = None
            if abs(cost_base) > EPS:
                unrealized_pct = unrealized_base / cost_base * 100.0

            position_rows.append(
                {
                    "symbol": symbol,
                    "market": market,
                    "currency": currency,
                    "quantity": round(qty, 8),
                    "avg_cost": round(avg_cost, 8),
                    "total_cost": round(total_cost, 8),
                    "last_price": round(float(last_price), 8),
                    "market_value_base": round(market_base, 8),
                    "unrealized_pnl_base": round(unrealized_base, 8),
                    "unrealized_pnl_pct": round(unrealized_pct, 8) if unrealized_pct is not None else None,
                    "valuation_currency": account.base_currency,
                    "price_source": price_info.source,
                    "price_provider": price_info.provider,
                    "price_date": price_info.price_date.isoformat() if price_info.price_date else None,
                    "price_stale": price_info.is_stale,
                    "price_available": price_info.is_available,
                    "data_quality": "partial" if limitations else "ok",
                    "limitations": limitations,
                    "position_lifecycle": "open",
                    "settlement_state": settlement_summary["settlement_state"],
                    "total_quantity": round(qty, 8),
                    "sellable_quantity": round(
                        settlement_summary["sellable_quantity"],
                        8,
                    ),
                    "unsettled_quantity": round(
                        settlement_summary["unsettled_quantity"],
                        8,
                    ),
                    "next_sellable_at": (
                        settlement_summary["next_sellable_at"].isoformat()
                        if settlement_summary["next_sellable_at"] is not None
                        else None
                    ),
                    "next_sellable_at_utc": (
                        self._to_utc_naive(
                            settlement_summary["next_sellable_at"]
                        )
                        if settlement_summary["next_sellable_at"] is not None
                        else None
                    ),
                    "settlement_calculation_status": settlement_summary[
                        "settlement_calculation_status"
                    ],
                    "settlement_warnings": settlement_summary[
                        "settlement_warnings"
                    ],
                }
            )

            market_value_base += market_base
            total_cost_base += cost_base

        return position_rows, lot_rows, market_value_base, total_cost_base, fx_stale

    def _resolve_position_price(
        self,
        *,
        symbol: str,
        as_of_date: date,
        realtime_prices: Optional[Dict[str, Tuple[Optional[float], Optional[str]]]] = None,
        include_realtime: bool = True,
    ) -> _ResolvedPositionPrice:
        today = date.today()

        if include_realtime and as_of_date == today:
            if realtime_prices is None:
                realtime_price, provider = self._fetch_realtime_position_price(symbol)
            else:
                realtime_price, provider = realtime_prices.get(symbol, (None, None))
            if realtime_price is not None and realtime_price > 0:
                return _ResolvedPositionPrice(
                    price=float(realtime_price),
                    source="realtime_quote",
                    price_date=today,
                    is_stale=False,
                    is_available=True,
                    provider=provider,
                )

        close = self.repo.get_latest_close_with_date(symbol=symbol, as_of=as_of_date)
        if close is not None:
            close_price, close_date = close
            if close_price > 0:
                return _ResolvedPositionPrice(
                    price=float(close_price),
                    source="history_close",
                    price_date=close_date,
                    is_stale=close_date < as_of_date,
                    is_available=True,
                )

        return _ResolvedPositionPrice(
            price=0.0,
            source="missing",
            price_date=None,
            is_stale=True,
            is_available=False,
        )

    def _prefetch_realtime_position_prices(
        self,
        symbols: Iterable[str],
    ) -> Dict[str, Tuple[Optional[float], Optional[str]]]:
        unique_symbols = sorted({symbol for symbol in symbols if symbol})
        if not unique_symbols:
            return {}

        # Bulk prefetch (when applicable) only warms the fetcher-module-level realtime cache;
        # the manager itself is discarded so per-symbol workers cannot serialize through its
        # per-fetcher call locks when individual reads still need a live fetch (e.g. mixed
        # markets, cache miss, or bulk source returning fewer rows than requested).
        if len(unique_symbols) >= 5:
            try:
                from data_provider.base import DataFetcherManager

                DataFetcherManager().prefetch_realtime_quotes(unique_symbols)
            except Exception as exc:
                logger.warning("Failed to prefetch realtime portfolio quotes: %s", exc)

        if len(unique_symbols) == 1:
            symbol = unique_symbols[0]
            return {symbol: self._fetch_realtime_position_price(symbol)}

        results: Dict[str, Tuple[Optional[float], Optional[str]]] = {}
        max_workers = min(PORTFOLIO_REALTIME_QUOTE_MAX_WORKERS, len(unique_symbols))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="portfolio-quote") as executor:
            futures = {
                executor.submit(self._fetch_realtime_position_price, symbol): symbol
                for symbol in unique_symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard for patched fetchers
                    logger.warning("Failed to prefetch realtime portfolio price for %s: %s", symbol, exc)
                    results[symbol] = (None, None)

        return results

    @staticmethod
    def _fetch_realtime_position_price(symbol: str) -> Tuple[Optional[float], Optional[str]]:
        try:
            from data_provider.base import DataFetcherManager

            fetcher_manager = DataFetcherManager()
            quote = fetcher_manager.get_realtime_quote(symbol, log_final_failure=False)
        except Exception as exc:
            logger.warning("Failed to fetch realtime portfolio price for %s: %s", symbol, exc)
            return None, None

        if quote is None:
            return None, None

        price = getattr(quote, "price", None)
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            return None, None

        if numeric_price <= 0:
            return None, None

        source = getattr(quote, "source", None)
        provider = getattr(source, "value", None) or (str(source) if source is not None else None)
        return numeric_price, provider

    @staticmethod
    def _normalize_symbol_for_storage(symbol: str) -> str:
        return canonical_stock_code(symbol)

    @staticmethod
    def _normalize_symbol_for_position(symbol: str) -> str:
        if not (symbol or "").strip():
            return ""

        raw = canonical_stock_code(symbol)
        if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
            return raw

        if "." in raw:
            base, suffix = raw.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                exchange = "SH" if suffix == "SS" else suffix
                return f"{exchange}{base}"

        return canonical_stock_code(normalize_stock_code(symbol))

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Canonicalization for symbol filtering with exchange-qualified input preservation.

        Keep explicit A-share exchange annotations (SH/SZ/BJ) intact to avoid collapsing
        different exchange variants of the same 6-digit core code.
        """
        raw = canonical_stock_code(symbol)
        if not raw:
            return ""

        if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
            return raw

        if "." in raw:
            base, suffix = raw.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                exchange = "SH" if suffix == "SS" else suffix
                return f"{exchange}{base}"

        return canonical_stock_code(normalize_stock_code(symbol))

    @classmethod
    def _build_symbol_filter_values(cls, symbol: str) -> List[str]:
        original = (symbol or "").strip().upper()
        normalized = cls._normalize_symbol(original)
        if not normalized:
            return []

        seen: Set[str] = set()
        values: List[str] = []

        def _add(value: Optional[str]) -> None:
            candidate = (value or "").strip().upper()
            if candidate and candidate not in seen:
                seen.add(candidate)
                values.append(candidate)

        _add(original)
        _add(normalized)

        if normalized.startswith("HK"):
            hk_digits = normalized[2:]
            if hk_digits.isdigit() and len(hk_digits) == 5:
                legacy_hk_digits = str(int(hk_digits))
                _add(f"HK{hk_digits}")
                _add(f"HK{legacy_hk_digits}")
                _add(f"{hk_digits}.HK")
                _add(f"{legacy_hk_digits}.HK")
            return values

        explicit_exchange: Optional[str] = None
        if len(original) >= 8 and original[:2] in {"SH", "SZ", "BJ"} and original[2:].isdigit():
            explicit_exchange = original[:2]
            explicit_code = original[2:]
        elif "." in original:
            base, suffix = original.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                explicit_exchange = "SH" if suffix == "SS" else suffix
                explicit_code = base
            else:
                explicit_code = None
        else:
            explicit_code = None

        if normalized.isdigit():
            if len(normalized) == 6:
                exchanges = [explicit_exchange] if explicit_exchange else ["SH", "SZ", "BJ"]
                for exchange in exchanges:
                    if exchange is None:
                        continue
                    _add(f"{exchange}{normalized}")
                    _add(f"{normalized}.{'SS' if exchange == 'SH' else exchange}")
                    if exchange == "SH":
                        _add(f"{normalized}.SH")
            return values

        if explicit_exchange is not None and explicit_code is not None and explicit_code.isdigit():
            if len(explicit_code) == 6:
                _add(f"{explicit_exchange}{explicit_code}")
                _add(f"{explicit_code}.{'SS' if explicit_exchange == 'SH' else explicit_exchange}")
                if explicit_exchange == "SH":
                    _add(f"{explicit_code}.SH")
            elif len(normalized) == 5:
                _add(f"HK{normalized}")
                _add(f"{normalized}.HK")

        return values

    @staticmethod
    def _normalize_trade_execution(
        *,
        trade_date: date,
        executed_at: Optional[datetime],
    ) -> Tuple[Optional[datetime], datetime, bool]:
        """Return UTC-naive storage time and an Asia/Ho_Chi_Minh effective time."""
        vietnam_tz = ZoneInfo("Asia/Ho_Chi_Minh")
        if executed_at is None:
            inferred = datetime.combine(
                trade_date,
                time(14, 45),
                tzinfo=vietnam_tz,
            )
            return None, inferred, True

        if executed_at.tzinfo is None:
            local_execution = executed_at.replace(tzinfo=vietnam_tz)
        else:
            local_execution = executed_at.astimezone(vietnam_tz)
        if local_execution.date() != trade_date:
            raise ValueError(
                "executed_at must resolve to trade_date in Asia/Ho_Chi_Minh"
            )
        return (
            PortfolioService._to_utc_naive(local_execution),
            local_execution,
            False,
        )

    @staticmethod
    def _to_utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _from_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))

    @classmethod
    def _settlement_lot_metadata(
        cls,
        *,
        trade: Any,
        settlement: Optional[Any],
        market: str,
    ) -> Dict[str, Any]:
        acquired_at = None
        if settlement is not None:
            _, acquired_at, _ = cls._normalize_trade_execution(
                trade_date=trade.trade_date,
                executed_at=cls._from_utc_naive(trade.executed_at),
            )
        if settlement is None:
            return {
                "acquired_at": None,
                "estimated_sellable_at": None,
                "estimated_sellable_at_utc": None,
                "actual_sellable_at": None,
                "actual_sellable_at_utc": None,
                "calendar_status": "unknown",
                "warnings": ["settlement_provenance_missing"],
                "legacy_sellable": True,
            }

        estimated = cls._from_utc_naive(settlement.estimated_sellable_at)
        actual = cls._from_utc_naive(settlement.actual_sellable_at)
        if isinstance(settlement.warnings_json, list):
            warnings = list(settlement.warnings_json)
        else:
            try:
                warnings = json.loads(settlement.warnings_json or "[]")
            except (TypeError, ValueError):
                warnings = ["settlement_warnings_invalid"]
        if not isinstance(warnings, list):
            warnings = ["settlement_warnings_invalid"]
        return {
            "acquired_at": acquired_at,
            "estimated_sellable_at": estimated,
            "estimated_sellable_at_utc": (
                cls._to_utc_naive(estimated) if estimated is not None else None
            ),
            "actual_sellable_at": actual,
            "actual_sellable_at_utc": (
                cls._to_utc_naive(actual) if actual is not None else None
            ),
            "calendar_status": settlement.calculation_status or "unknown",
            "warnings": [str(item) for item in warnings if str(item)],
            "legacy_sellable": False,
        }

    @staticmethod
    def _lot_is_sellable(
        lot: Dict[str, Any],
        *,
        as_of_at: datetime,
    ) -> bool:
        if lot.get("legacy_sellable"):
            return True
        sellable_at = (
            lot.get("actual_sellable_at")
            or lot.get("estimated_sellable_at")
        )
        return sellable_at is not None and sellable_at <= as_of_at

    @classmethod
    def _lot_settlement_state(
        cls,
        lot: Dict[str, Any],
        *,
        as_of_at: datetime,
    ) -> str:
        if lot.get("calendar_status") == "unknown":
            return "unknown"
        return "sellable" if cls._lot_is_sellable(lot, as_of_at=as_of_at) else "unsettled"

    @classmethod
    def _summarize_settlement_lots(
        cls,
        lots: List[Dict[str, Any]],
        *,
        as_of_at: datetime,
    ) -> Dict[str, Any]:
        active_lots = [
            lot for lot in lots
            if float(lot.get("remaining_quantity") or 0.0) > EPS
        ]
        held_quantity = sum(
            float(lot["remaining_quantity"]) for lot in active_lots
        )
        sellable_quantity = sum(
            float(lot["remaining_quantity"])
            for lot in active_lots
            if cls._lot_is_sellable(lot, as_of_at=as_of_at)
        )
        unsettled_quantity = max(0.0, held_quantity - sellable_quantity)
        upcoming = [
            lot.get("actual_sellable_at") or lot.get("estimated_sellable_at")
            for lot in active_lots
            if not cls._lot_is_sellable(lot, as_of_at=as_of_at)
        ]
        next_sellable_at = min(
            (value for value in upcoming if value is not None),
            default=None,
        )

        statuses = {
            str(lot.get("calendar_status") or "unknown")
            for lot in active_lots
        }
        if "unknown" in statuses or not statuses:
            calculation_status = "unknown"
        elif "degraded" in statuses:
            calculation_status = "degraded"
        else:
            calculation_status = "confirmed"

        if "unknown" in statuses:
            settlement_state = "unknown"
        elif unsettled_quantity <= EPS:
            settlement_state = "sellable"
        elif sellable_quantity <= EPS:
            settlement_state = "unsettled"
        else:
            settlement_state = "partially_sellable"

        return {
            "held_quantity": held_quantity,
            "sellable_quantity": sellable_quantity,
            "unsettled_quantity": unsettled_quantity,
            "next_sellable_at": next_sellable_at,
            "settlement_state": settlement_state,
            "settlement_calculation_status": calculation_status,
            "settlement_warnings": sorted(
                {
                    str(warning)
                    for lot in active_lots
                    for warning in (lot.get("warnings") or [])
                    if str(warning)
                }
            ),
        }

    @classmethod
    def _consume_settlement_lots(
        cls,
        lots: List[Dict[str, Any]],
        quantity: float,
        *,
        symbol: str,
        trade_date: Optional[date],
        sale_at: datetime,
    ) -> None:
        summary = cls._summarize_settlement_lots(lots, as_of_at=sale_at)
        if summary["held_quantity"] + EPS < quantity:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=summary["held_quantity"],
            )
        if summary["sellable_quantity"] + EPS < quantity:
            raise PortfolioUnsettledSaleError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                held_quantity=summary["held_quantity"],
                sellable_quantity=summary["sellable_quantity"],
                unsettled_quantity=summary["unsettled_quantity"],
                next_sellable_at=summary["next_sellable_at"],
            )

        remaining = quantity
        while remaining > EPS:
            eligible_index = next(
                index
                for index, lot in enumerate(lots)
                if cls._lot_is_sellable(lot, as_of_at=sale_at)
            )
            lot = lots[eligible_index]
            take = min(remaining, float(lot["remaining_quantity"]))
            lot["remaining_quantity"] = float(lot["remaining_quantity"]) - take
            remaining -= take
            if lot["remaining_quantity"] <= EPS:
                lots.pop(eligible_index)

    @staticmethod
    def _consume_fifo_lots(
        lots: List[Dict[str, Any]],
        quantity: float,
        symbol: str,
        trade_date: Optional[date] = None,
        sale_at: Optional[datetime] = None,
    ) -> float:
        remaining = quantity
        cost_basis = 0.0
        while remaining > EPS:
            eligible_index = next(
                (
                    index
                    for index, lot in enumerate(lots)
                    if sale_at is None
                    or PortfolioService._lot_is_sellable(lot, as_of_at=sale_at)
                ),
                None,
            )
            if eligible_index is None:
                summary = PortfolioService._summarize_settlement_lots(
                    lots,
                    as_of_at=sale_at
                    or datetime.max.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
                )
                raise PortfolioUnsettledSaleError(
                    symbol=symbol,
                    trade_date=trade_date,
                    requested_quantity=quantity,
                    held_quantity=summary["held_quantity"],
                    sellable_quantity=quantity - remaining,
                    unsettled_quantity=summary["unsettled_quantity"],
                    next_sellable_at=summary["next_sellable_at"],
                )
            head = lots[eligible_index]
            take = min(remaining, float(head["remaining_quantity"]))
            cost_basis += take * float(head["unit_cost"])
            head["remaining_quantity"] = float(head["remaining_quantity"]) - take
            remaining -= take
            if head["remaining_quantity"] <= EPS:
                lots.pop(eligible_index)
        return cost_basis

    @staticmethod
    def _consume_avg_position(
        state: _AvgState,
        quantity: float,
        symbol: str,
        trade_date: Optional[date] = None,
    ) -> float:
        if state.quantity + EPS < quantity:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=state.quantity,
            )
        if state.quantity <= EPS:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=0.0,
            )
        avg_cost = state.total_cost / state.quantity
        cost_basis = avg_cost * quantity
        state.quantity -= quantity
        state.total_cost -= cost_basis
        if state.quantity <= EPS:
            state.quantity = 0.0
            state.total_cost = 0.0
        return cost_basis

    @staticmethod
    def _held_quantity(
        *,
        key: Tuple[str, str, str],
        cost_method: str,
        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
        avg_state: Dict[Tuple[str, str, str], _AvgState],
    ) -> float:
        if cost_method == "fifo":
            return sum(float(lot["remaining_quantity"]) for lot in fifo_lots.get(key, []))
        return float(avg_state.get(key, _AvgState()).quantity)

    def _convert_amount(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Tuple[float, bool, str]:
        from_norm = self._normalize_currency(from_currency)
        to_norm = self._normalize_currency(to_currency)
        if abs(amount) <= EPS:
            return 0.0, False, "zero"
        if from_norm == to_norm:
            return float(amount), False, "identity"

        direct = self.repo.get_latest_fx_rate(
            from_currency=from_norm,
            to_currency=to_norm,
            as_of=as_of_date,
        )
        if direct is not None and direct.rate > 0:
            return float(amount) * float(direct.rate), bool(direct.is_stale), "direct_rate"

        inverse = self.repo.get_latest_fx_rate(
            from_currency=to_norm,
            to_currency=from_norm,
            as_of=as_of_date,
        )
        if inverse is not None and inverse.rate > 0:
            return float(amount) / float(inverse.rate), bool(inverse.is_stale), "inverse_rate"

        # P0 fallback: keep pipeline available even when FX cache is missing.
        return float(amount), True, "fallback_1_to_1"

    def convert_amount(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Tuple[float, bool, str]:
        """Public conversion entry for cross-service consumers."""
        return self._convert_amount(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )

    def _list_account_refresh_fx_currencies(
        self,
        *,
        account: Any,
        as_of_date: date,
        strict: bool = True,
    ) -> List[str]:
        """Return distinct non-base currencies participating in refresh for one account."""
        base_currency = self._normalize_currency(account.base_currency)
        currencies: Set[str] = set()
        rows = list(self.repo.list_trades(account.id, as_of=as_of_date))
        rows.extend(self.repo.list_cash_ledger(account.id, as_of=as_of_date))
        for row in rows:
            try:
                currency = self._normalize_currency(row.currency)
            except ValueError:
                if strict:
                    raise
                logger.warning(
                    "Skip invalid FX refresh currency for account %s on %s: %r",
                    account.id,
                    as_of_date.isoformat(),
                    getattr(row, "currency", None),
                )
                continue
            if currency != base_currency:
                currencies.add(currency)
        return sorted(currencies)

    def _refresh_account_fx_rates(
        self,
        *,
        account: Any,
        as_of_date: date,
        refresh_enabled: bool,
    ) -> Dict[str, int]:
        """Refresh FX pairs for one account and keep stale fallback on failures."""
        refresh_currencies = self._list_account_refresh_fx_currencies(
            account=account,
            as_of_date=as_of_date,
            strict=refresh_enabled,
        )
        if not refresh_enabled:
            return {
                "pair_count": len(refresh_currencies),
                "updated_count": 0,
                "stale_count": 0,
                "error_count": 0,
            }

        base_currency = self._normalize_currency(account.base_currency)
        summary = {
            "pair_count": len(refresh_currencies),
            "updated_count": 0,
            "stale_count": 0,
            "error_count": 0,
        }
        for from_currency in refresh_currencies:
            try:
                rate = self._fetch_fx_rate_from_yfinance(
                    from_currency=from_currency,
                    to_currency=base_currency,
                    as_of_date=as_of_date,
                )
                if rate is not None and rate > 0:
                    self.repo.save_fx_rate(
                        from_currency=from_currency,
                        to_currency=base_currency,
                        rate_date=as_of_date,
                        rate=rate,
                        source="yfinance",
                        is_stale=False,
                    )
                    summary["updated_count"] += 1
                    continue
            except Exception as exc:
                logger.warning(
                    "FX online fetch failed for %s/%s on %s: %s",
                    from_currency,
                    base_currency,
                    as_of_date.isoformat(),
                    exc,
                )

            fallback = self.repo.get_latest_fx_rate(
                from_currency=from_currency,
                to_currency=base_currency,
                as_of=as_of_date,
            )
            if fallback is not None and float(fallback.rate or 0.0) > 0:
                self.repo.save_fx_rate(
                    from_currency=from_currency,
                    to_currency=base_currency,
                    rate_date=as_of_date,
                    rate=float(fallback.rate),
                    source=(fallback.source or "cache_fallback"),
                    is_stale=True,
                )
                summary["stale_count"] += 1
            else:
                summary["error_count"] += 1
        return summary

    @staticmethod
    def _fetch_fx_rate_from_yfinance(
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Optional[float]:
        """Fetch latest available FX close rate around as_of date."""
        if yf is None:
            return None
        symbol = f"{from_currency}{to_currency}=X"
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            start=(as_of_date - timedelta(days=7)).isoformat(),
            end=(as_of_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        if history is None or history.empty or "Close" not in history:
            return None
        close = history["Close"].dropna()
        if close.empty:
            return None
        value = float(close.iloc[-1])
        if value <= 0:
            return None
        return value

    def _require_active_account(self, account_id: int) -> Any:
        account = self.repo.get_account(account_id, include_inactive=False)
        if account is None:
            raise ValueError(f"Active account not found: {account_id}")
        return account

    def _require_active_account_in_session(self, *, session: Any, account_id: int) -> Any:
        account = self.repo.get_account_in_session(
            session=session,
            account_id=account_id,
            include_inactive=False,
        )
        if account is None:
            raise ValueError(f"Active account not found: {account_id}")
        return account

    def _has_trade_uid(self, *, account_id: int, trade_uid: str, session: Optional[Any] = None) -> bool:
        if session is None:
            return self.repo.has_trade_uid(account_id, trade_uid)
        return self.repo.has_trade_uid_in_session(session=session, account_id=account_id, trade_uid=trade_uid)

    def _has_trade_dedup_hash(
        self,
        *,
        account_id: int,
        dedup_hash: str,
        session: Optional[Any] = None,
    ) -> bool:
        if session is None:
            return self.repo.has_trade_dedup_hash(account_id, dedup_hash)
        return self.repo.has_trade_dedup_hash_in_session(
            session=session,
            account_id=account_id,
            dedup_hash=dedup_hash,
        )

    @staticmethod
    def _account_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": row.id,
            "owner_id": row.owner_id,
            "name": row.name,
            "broker": row.broker,
            "market": row.market,
            "base_currency": row.base_currency,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _trade_row_to_dict(
        row: Any,
        *,
        source_link: Optional[Any] = None,
    ) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "trade_uid": row.trade_uid,
            "symbol": row.symbol,
            "market": row.market,
            "currency": row.currency,
            "trade_date": row.trade_date.isoformat() if row.trade_date else "",
            "side": row.side,
            "quantity": float(row.quantity),
            "price": float(row.price),
            "fee": float(row.fee),
            "tax": float(row.tax),
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "source_decision_signal_id": (
                int(source_link.signal_id) if source_link is not None else None
            ),
            "link_type": (
                str(source_link.link_type) if source_link is not None else None
            ),
        }

    def _validate_source_decision_signal(
        self,
        *,
        session: Any,
        source_decision_signal_id: Optional[int],
        trade_side: str,
        trade_symbol: str,
        trade_market: str,
    ) -> Optional[Any]:
        if source_decision_signal_id is None:
            return None
        if trade_side != "buy":
            raise ValueError(
                "source_decision_signal_id is only valid for buy trades"
            )
        signal = self.signal_trade_link_repo.get_signal_in_session(
            session=session,
            signal_id=int(source_decision_signal_id),
        )
        if signal is None:
            raise ValueError(
                f"Source DecisionSignal not found: {source_decision_signal_id}"
            )
        if str(signal.market or "").strip().lower() != trade_market:
            raise ValueError(
                "Source DecisionSignal market does not match the trade market"
            )
        signal_symbol = canonical_stock_code(
            normalize_stock_code(str(signal.stock_code or ""))
        )
        trade_signal_symbol = canonical_stock_code(
            normalize_stock_code(trade_symbol)
        )
        if not signal_symbol or signal_symbol != trade_signal_symbol:
            raise ValueError(
                "Source DecisionSignal symbol does not match the trade symbol"
            )
        if str(signal.action or "").strip().lower() not in {"buy", "add"}:
            raise ValueError(
                "Source DecisionSignal must be an entry recommendation (buy or add)"
            )
        if str(signal.status or "").strip().lower() != "active":
            raise ValueError(
                "Source DecisionSignal must be active when the trade is recorded"
            )
        return signal

    @staticmethod
    def _cash_ledger_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "event_date": row.event_date.isoformat() if row.event_date else "",
            "direction": row.direction,
            "amount": float(row.amount),
            "currency": row.currency,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _corporate_action_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "symbol": row.symbol,
            "market": row.market,
            "currency": row.currency,
            "effective_date": row.effective_date.isoformat() if row.effective_date else "",
            "action_type": row.action_type,
            "cash_dividend_per_share": (
                float(row.cash_dividend_per_share) if row.cash_dividend_per_share is not None else None
            ),
            "split_ratio": float(row.split_ratio) if row.split_ratio is not None else None,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _validate_paging(*, page: int, page_size: int) -> Tuple[int, int]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be in [1, 100]")
        return page, page_size

    @staticmethod
    def _normalize_market(value: str) -> str:
        market = (value or "").strip().lower()
        if market not in VALID_MARKETS:
            raise ValueError("market must be one of: cn, hk, us, jp, kr, tw, vn")
        return market

    @staticmethod
    def _normalize_currency(value: str) -> str:
        currency = (value or "").strip().upper()
        if not currency:
            raise ValueError("currency is required")
        return currency

    @staticmethod
    def _normalize_cost_method(value: str) -> str:
        method = (value or "").strip().lower()
        if method not in VALID_COST_METHODS:
            raise ValueError("cost_method must be fifo or avg")
        return method

    @staticmethod
    def _default_currency_for_market(market: str) -> str:
        if market == "vn":
            return "VND"
        if market == "hk":
            return "HKD"
        if market == "us":
            return "USD"
        return "CNY"
