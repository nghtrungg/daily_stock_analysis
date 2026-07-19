#!/usr/bin/env python3
"""Validate the PR0 schema ownership register and an available peer copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTER = ROOT / "docs" / "migration" / "schema-ownership-register.json"
DEFAULT_INVENTORY = ROOT / "docs" / "migration" / "pr0-schema-inventory.json"
DEFAULT_PEER = (
    ROOT.parent
    / "personal-stock-tracking"
    / "docs"
    / "migration"
    / "schema-ownership-register.json"
)
REPOSITORIES = {"daily_stock_analysis", "personal_stock_tracking"}
REQUIRED_TYPES = {
    "schema",
    "table",
    "view",
    "function",
    "trigger",
    "rls_policy",
    "enum",
    "production_migration_workflow",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_register(
    register: dict[str, Any],
    inventory: dict[str, Any],
    *,
    peer: dict[str, Any] | None = None,
) -> None:
    assert register["contract_version"] >= 3
    assert register["status"] == "active"
    assert set(register["repositories"]) == REPOSITORIES
    assert register["rules"]["ddl_owner_count_per_object"] == 1
    assert register["rules"]["dml_access_does_not_imply_ddl_ownership"] is True

    current_names: list[str] = []
    for item in register["objects"]:
        owner = item["owner"]
        if owner in REPOSITORIES:
            current_names.extend(item.get("names", []))
            if owner == "personal_stock_tracking" and item["object_type"] in REQUIRED_TYPES - {
                "production_migration_workflow"
            }:
                assert item["migration_path"] == "owner-relative:supabase/migrations"
        else:
            assert owner == "none at baseline"
            assert item["names"] == [], "a current object cannot be unowned"
    assert len(current_names) == len(set(current_names)), "object has multiple owners"

    legacy_sets = [
        item
        for item in register["objects"]
        if item.get("names_from") == "docs/migration/pr0-schema-inventory.json#tables"
    ]
    assert len(legacy_sets) == 1
    assert legacy_sets[0]["owner"] == "daily_stock_analysis"
    assert len(inventory["tables"]) == inventory["table_count"]

    gate = register["review_gate"]
    assert gate["duplicate_owner_count"] == 0
    assert gate["unowned_current_object_count"] == 0
    assert gate["joint_contract_recorded"] is True
    assert gate["external_confirmation_required_before_pr1"] is False
    assert set(gate["required_object_types_reviewed"]) == REQUIRED_TYPES

    if peer is not None:
        assert peer == register, "peer schema ownership register has drifted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--peer", type=Path, default=DEFAULT_PEER)
    parser.add_argument("--require-peer", action="store_true")
    args = parser.parse_args()

    peer = load_json(args.peer) if args.peer.exists() else None
    if args.require_peer and peer is None:
        raise FileNotFoundError(f"Peer ownership register not found: {args.peer}")

    validate_register(load_json(args.register), load_json(args.inventory), peer=peer)
    suffix = f" and peer {args.peer}" if peer is not None else ""
    print(f"Schema ownership contract is valid: {args.register}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
