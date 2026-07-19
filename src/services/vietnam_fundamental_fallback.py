"""Deterministic stale-data fallback for Vietnam fundamental report inputs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
from typing import Any, Dict, Iterable, List, Optional


_VALUATION_KEYS = ("pe_ratio", "pb_ratio")
_ACTIVE_FLOW_KEYS = (
    "active_buy_volume",
    "active_sell_volume",
    "active_unknown_volume",
    "active_net_volume",
    "active_buy_ratio",
    "active_sell_ratio",
    "active_imbalance",
)
_INVESTOR_FLOW_KEYS = {
    "foreign_flow": (
        "foreign_buy_volume",
        "foreign_sell_volume",
        "foreign_net_volume",
        "foreign_buy_value",
        "foreign_sell_value",
        "foreign_net_value",
    ),
    "proprietary_flow": (
        "proprietary_buy_volume",
        "proprietary_sell_volume",
        "proprietary_net_volume",
        "proprietary_buy_value",
        "proprietary_sell_value",
        "proprietary_net_value",
    ),
}


def _finite_positive(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _snapshot_payload(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    payload = entry.get("payload", entry)
    return payload if isinstance(payload, dict) else None


def _snapshot_as_of(entry: Dict[str, Any], payload: Dict[str, Any]) -> str:
    capital_flow = payload.get("capital_flow")
    capital_data = capital_flow.get("data") if isinstance(capital_flow, dict) else None
    candidates = (
        capital_data.get("as_of") if isinstance(capital_data, dict) else None,
        entry.get("created_at"),
    )
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _session_key(as_of: str, fallback_index: int) -> str:
    text = str(as_of or "").strip()
    if text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return text[:10] or f"snapshot-{fallback_index}"
    return f"snapshot-{fallback_index}"


def _recent_snapshots(
    entries: Iterable[Any],
) -> List[Dict[str, Any]]:
    snapshots: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        payload = _snapshot_payload(entry)
        if payload is None:
            continue
        as_of = _snapshot_as_of(entry, payload)
        session = _session_key(as_of, index)
        snapshots.append({"payload": payload, "as_of": as_of, "session": session})
    return snapshots


def _block_data(context: Dict[str, Any], key: str) -> Dict[str, Any]:
    block = context.get(key)
    if not isinstance(block, dict):
        return {}
    data = block.get("data")
    return data if isinstance(data, dict) else {}


def apply_vietnam_fundamental_fallback(
    current: Dict[str, Any],
    recent_snapshots: Iterable[Any],
    *,
    session_limit: int = 5,
) -> Dict[str, Any]:
    """Fill missing VN valuation and order-flow fields from recent sessions.

    Valuation uses the mean of up to five distinct stored sessions. Order flow
    uses the most recent session with coverage for each feed. Every fallback is
    marked as partial/stale so downstream confidence checks cannot treat it as
    realtime evidence.
    """

    if not isinstance(current, dict):
        return current
    session_limit = max(1, int(session_limit))
    snapshots = _recent_snapshots(
        recent_snapshots if isinstance(recent_snapshots, (list, tuple)) else [],
    )
    if not snapshots:
        return current

    result = deepcopy(current)
    coverage = dict(result.get("coverage") or {})

    valuation = dict(result.get("valuation") or {})
    valuation_data = dict(valuation.get("data") or {})
    valuation_filled: List[str] = []
    valuation_as_of: List[str] = []
    valuation_session_counts: Dict[str, int] = {}
    for key in _VALUATION_KEYS:
        if _finite_positive(valuation_data.get(key)) is not None:
            continue
        values: List[float] = []
        seen_sessions = set()
        for snapshot in snapshots:
            if snapshot["session"] in seen_sessions:
                continue
            historical = _block_data(snapshot["payload"], "valuation")
            number = _finite_positive(historical.get(key))
            if number is None:
                continue
            seen_sessions.add(snapshot["session"])
            values.append(number)
            if snapshot["as_of"]:
                valuation_as_of.append(snapshot["as_of"])
            if len(values) >= session_limit:
                break
        if values:
            valuation_data[key] = round(sum(values) / len(values), 4)
            valuation_filled.append(key)
            valuation_session_counts[key] = len(values)
    if valuation_filled:
        valuation["data"] = valuation_data
        valuation["status"] = "partial"
        valuation["fallback"] = {
            "method": "recent_session_average",
            "fields": valuation_filled,
            "session_count": max(valuation_session_counts.values()),
            "session_counts": valuation_session_counts,
            "latest_as_of": valuation_as_of[0] if valuation_as_of else None,
        }
        source_chain = list(valuation.get("source_chain") or [])
        source_chain.append({
            "provider": "fundamental_snapshot_5_session_average",
            "result": "fallback",
            "duration_ms": 0,
        })
        valuation["source_chain"] = source_chain
        result["valuation"] = valuation
        coverage["valuation"] = "partial"

    capital_flow = dict(result.get("capital_flow") or {})
    flow_data = dict(capital_flow.get("data") or {})
    flow_coverage = dict(flow_data.get("coverage") or {})
    stock_flow = dict(flow_data.get("stock_flow") or {})
    fallback_feeds: List[str] = []
    fallback_as_of: List[str] = []

    feed_keys = {"active_order_flow": _ACTIVE_FLOW_KEYS, **_INVESTOR_FLOW_KEYS}
    for feed_name, keys in feed_keys.items():
        if flow_coverage.get(feed_name) == "ok":
            continue
        for snapshot in snapshots:
            historical_data = _block_data(snapshot["payload"], "capital_flow")
            historical_coverage = historical_data.get("coverage")
            historical_flow = historical_data.get("stock_flow")
            if not isinstance(historical_coverage, dict) or historical_coverage.get(feed_name) != "ok":
                continue
            if not isinstance(historical_flow, dict):
                continue
            copied = False
            for key in keys:
                if historical_flow.get(key) is not None:
                    stock_flow[key] = historical_flow[key]
                    copied = True
            if copied:
                flow_coverage[feed_name] = "fallback"
                fallback_feeds.append(feed_name)
                if snapshot["as_of"]:
                    fallback_as_of.append(snapshot["as_of"])
                break

    if fallback_feeds:
        flow_data["stock_flow"] = stock_flow
        flow_data["coverage"] = flow_coverage
        flow_data["fallback_feeds"] = fallback_feeds
        flow_data["fallback_as_of"] = fallback_as_of[0] if fallback_as_of else None
        capital_flow["data"] = flow_data
        capital_flow["status"] = "partial"
        source_chain = list(capital_flow.get("source_chain") or [])
        source_chain.append({
            "provider": "fundamental_snapshot_latest_session",
            "result": "fallback",
            "duration_ms": 0,
        })
        capital_flow["source_chain"] = source_chain
        result["capital_flow"] = capital_flow
        coverage["capital_flow"] = "partial"

    result["coverage"] = coverage
    return result
