"""Regression coverage for the local shared-schema ownership guard."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_schema_ownership_contract.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("schema_ownership_checker", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_checker_accepts_registered_local_contract() -> None:
    checker = _load_checker()

    errors = checker.validate_contract(
        ROOT / "docs" / "migration" / "schema-ownership-register.json",
        ROOT / "src" / "storage.py",
    )

    assert errors == []


def test_contract_checker_rejects_duplicate_object_ownership(tmp_path: Path) -> None:
    checker = _load_checker()
    contract = json.loads(
        (ROOT / "docs" / "migration" / "schema-ownership-register.json").read_text(encoding="utf-8")
    )
    contract["objects"].append(
        {
            "object_type": "table",
            "names": ["public.analysis_runs"],
            "owner": "daily_stock_analysis",
            "migration_path": "invalid",
        }
    )
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    errors = checker.validate_contract(contract_path, ROOT / "src" / "storage.py")

    assert any("duplicate owner" in error for error in errors)
