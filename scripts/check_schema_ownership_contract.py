#!/usr/bin/env python3
"""Validate the local half of the shared Supabase schema-ownership contract."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "docs" / "migration" / "schema-ownership-register.json"
STORAGE_PATH = ROOT / "src" / "storage.py"
TABLE_NAME_PATTERN = re.compile(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]")
REQUIRED_OBJECT_TYPES = {
    "schema", "table", "function", "trigger", "rls_policy", "view", "enum", "production_migration_workflow",
}
KNOWN_OWNERS = {"daily_stock_analysis", "personal_stock_tracking", "none", "none at baseline"}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"contract root must be an object: {path}")
    return value


def _registered_names(item: dict[str, Any]) -> list[str]:
    names = item.get("names")
    if not isinstance(names, list):
        return []
    return [name for name in names if isinstance(name, str) and name.strip()]


def validate_contract(contract_path: Path, storage_path: Path, sibling_root: Path | None = None) -> list[str]:
    """Return deterministic, user-actionable validation errors."""

    errors: list[str] = []
    try:
        contract = _load_json(contract_path)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(contract.get("contract_id"), str) or not contract["contract_id"].strip():
        errors.append("contract_id is missing")
    if not isinstance(contract.get("contract_version"), int) or contract["contract_version"] < 1:
        errors.append("contract_version must be a positive integer")

    repositories = contract.get("repositories")
    expected_repositories = {"daily_stock_analysis", "personal_stock_tracking"}
    if not isinstance(repositories, dict) or set(repositories) != expected_repositories:
        errors.append("repositories must register daily_stock_analysis and personal_stock_tracking")

    objects = contract.get("objects")
    if not isinstance(objects, list):
        return errors + ["objects must be a list"]
    present_types: set[str] = set()
    named_owners: dict[str, str] = {}
    has_local_table_inventory = False
    for item in objects:
        if not isinstance(item, dict):
            errors.append("objects contains a non-object entry")
            continue
        object_type = item.get("object_type")
        owner = item.get("owner")
        if isinstance(object_type, str):
            present_types.add(object_type)
        if owner not in KNOWN_OWNERS:
            errors.append(f"invalid owner for {object_type!r}: {owner!r}")
            continue
        for name in _registered_names(item):
            existing_owner = named_owners.get(name)
            if existing_owner and existing_owner != owner:
                errors.append(f"duplicate owner for {name}: {existing_owner} and {owner}")
            named_owners[name] = owner
        if object_type == "table_set":
            has_local_table_inventory = item.get("names_from") == "src/storage.py#__tablename__"

    missing_types = REQUIRED_OBJECT_TYPES - present_types
    if missing_types:
        errors.append(f"missing required object types: {', '.join(sorted(missing_types))}")
    if not has_local_table_inventory:
        errors.append("table_set must reference src/storage.py#__tablename__")
    if not storage_path.exists() or not TABLE_NAME_PATTERN.findall(storage_path.read_text(encoding="utf-8")):
        errors.append("src/storage.py has no discoverable SQLite table inventory")

    if sibling_root is not None:
        sibling_contract = sibling_root / "docs" / "migration" / "schema-ownership-register.json"
        if not sibling_contract.exists():
            errors.append(f"sibling contract is missing: {sibling_contract}")
        else:
            try:
                if _load_json(sibling_contract) != contract:
                    errors.append("sibling contract JSON differs from the local contract")
            except ValueError as exc:
                errors.append(str(exc))
    return errors


def main() -> int:
    sibling_value = os.environ.get("PERSONAL_STOCK_TRACKING_ROOT", "").strip()
    sibling_root = Path(sibling_value) if sibling_value else None
    errors = validate_contract(CONTRACT_PATH, STORAGE_PATH, sibling_root)
    if errors:
        for error in errors:
            print(f"[schema-ownership] ERROR: {error}", file=sys.stderr)
        return 1
    print("[schema-ownership] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
