#!/usr/bin/env python3
"""Generate or verify the PR0 SQLAlchemy schema contract snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import Date, DateTime, UniqueConstraint

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage import Base, CURRENT_SCHEMA_VERSION  # noqa: E402


DEFAULT_OUTPUT = ROOT / "docs" / "migration" / "pr0-schema-inventory.json"
BASELINE_COMMIT = "2966d4a53608aa0bc1f7bc714b68ac13939192b0"

# These are structured values serialized into SQLite TEXT today. Ordinary prose
# TEXT columns are intentionally absent.
JSON_FIELD_CONTRACTS: dict[str, dict[str, str]] = {
    "agent_provider_turns.messages_json": {"empty": "[]", "null": "not allowed"},
    "alert_notifications.diagnostics": {"empty": "{}", "null": "allowed"},
    "alert_rules.cooldown_policy": {"empty": "{}", "null": "allowed"},
    "alert_rules.notification_policy": {"empty": "{}", "null": "allowed"},
    "alert_rules.parameters": {"empty": "{}", "null": "not allowed"},
    "alert_triggers.diagnostics": {"empty": "{}", "null": "allowed"},
    "analysis_history.context_snapshot": {
        "empty": "{}",
        "null": "allowed",
        "sensitivity": "sanitized analysis_context_pack_overview only",
    },
    "analysis_history.raw_result": {"empty": "{}", "null": "allowed"},
    "backtest_summaries.advice_breakdown_json": {"empty": "{}", "null": "allowed"},
    "backtest_summaries.diagnostics_json": {"empty": "{}", "null": "allowed"},
    "decision_signals.data_quality_summary_json": {"empty": "{}", "null": "allowed"},
    "decision_signals.evidence_json": {"empty": "[]", "null": "allowed"},
    "decision_signals.metadata_json": {"empty": "{}", "null": "allowed"},
    "fundamental_snapshot.coverage": {"empty": "{}", "null": "allowed"},
    "fundamental_snapshot.payload": {"empty": "{}", "null": "not allowed"},
    "fundamental_snapshot.source_chain": {"empty": "[]", "null": "allowed"},
    "intelligence_items.raw_payload": {"empty": "{}", "null": "allowed"},
    "llm_usage.known_dynamic_marker_positions": {"empty": "[]", "null": "allowed"},
    "llm_usage.provider_usage_json": {"empty": "{}", "null": "allowed"},
    "portfolio_daily_snapshots.payload": {"empty": "{}", "null": "allowed"},
    "portfolio_trade_settlements.warnings_json": {"empty": "[]", "null": "not allowed"},
    "settlement_outcomes.ambiguity_flags_json": {"empty": "[]", "null": "not allowed"},
}


def _column_contract(table_name: str, column: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": column.name,
        "type": str(column.type),
        "nullable": bool(column.nullable),
        "primary_key": bool(column.primary_key),
        "foreign_keys": sorted(foreign_key.target_fullname for foreign_key in column.foreign_keys),
    }
    if isinstance(column.type, DateTime):
        result["timestamp_semantic"] = {
            "legacy_sqlite": "naive DATETIME; timezone meaning requires per-column import review",
            "postgres_target": "TIMESTAMP WITH TIME ZONE stored in UTC",
            "presentation": "Asia/Ho_Chi_Minh at user-visible boundaries",
        }
    elif isinstance(column.type, Date):
        result["date_semantic"] = (
            "Vietnam trading/calendar date; remains DATE unless the domain contract says otherwise"
        )

    json_contract = JSON_FIELD_CONTRACTS.get(f"{table_name}.{column.name}")
    if json_contract:
        result["json_contract"] = json_contract
    return result


def build_inventory() -> dict[str, Any]:
    tables: dict[str, Any] = {}
    seen_json_fields: set[str] = set()

    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        columns = [_column_contract(table.name, column) for column in table.columns]
        for column in columns:
            if "json_contract" in column:
                seen_json_fields.add(f"{table.name}.{column['name']}")

        unique_constraints = sorted(
            (
                {
                    "name": constraint.name,
                    "columns": [column.name for column in constraint.columns],
                }
                for constraint in table.constraints
                if isinstance(constraint, UniqueConstraint)
            ),
            key=lambda item: (item["name"] or "", item["columns"]),
        )
        indexes = sorted(
            (
                {
                    "name": index.name,
                    "unique": bool(index.unique),
                    "columns": [column.name for column in index.columns],
                }
                for index in table.indexes
            ),
            key=lambda item: item["name"] or "",
        )
        tables[table.name] = {
            "columns": columns,
            "unique_constraints": unique_constraints,
            "indexes": indexes,
        }

    missing_json_fields = sorted(set(JSON_FIELD_CONTRACTS) - seen_json_fields)
    if missing_json_fields:
        raise RuntimeError(f"JSON contract fields missing from ORM metadata: {missing_json_fields}")

    return {
        "contract_version": 1,
        "baseline": {
            "commit": BASELINE_COMMIT,
            "capture_basis": (
                "HEAD plus the intentionally preserved active settlement/portfolio working baseline"
            ),
            "runtime_schema_version": CURRENT_SCHEMA_VERSION,
        },
        "table_count": len(tables),
        "tables": tables,
    }


def _render(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = _render(build_inventory())
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            print(f"PR0 schema inventory is stale: {output}")
            return 1
        print(f"PR0 schema inventory is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote PR0 schema inventory: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
