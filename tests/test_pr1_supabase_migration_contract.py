from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib

import yaml

from scripts.generate_pr0_schema_inventory import JSON_FIELD_CONTRACTS
from scripts.generate_pr1_supabase_migration import (
    CURRENCY_COLUMNS,
    LEGACY_ONLY_TABLES,
    SYMBOL_COLUMNS,
    render_migration,
)


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "migration" / "pr0-schema-inventory.json"
MIGRATIONS_PATH = ROOT / "supabase" / "migrations"
CONFIG_PATH = ROOT / "supabase" / "config.toml"
SECURITY_TEST_PATH = (
    ROOT / "supabase" / "tests" / "database" / "private_dsa_security.test.sql"
)
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"


def test_private_compute_migration_covers_the_frozen_table_inventory():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    sql = render_migration()
    expected_tables = set(inventory["tables"]) - LEGACY_ONLY_TABLES

    assert len(expected_tables) == 31
    assert {
        line.removeprefix("create table dsa.").split(" ", 1)[0]
        for line in sql.splitlines()
        if line.startswith("create table dsa.")
    } == expected_tables
    assert "create table dsa.schema_migrations" not in sql
    assert "create table public." not in sql
    assert "alter table public." not in sql


def test_postgres_native_json_and_timestamp_types_are_rendered():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    sql = render_migration()

    for qualified_name in JSON_FIELD_CONTRACTS:
        table_name, column_name = qualified_name.split(".", 1)
        assert f"create table dsa.{table_name} (" in sql
        assert f"\n  {column_name} jsonb" in sql

    timestamp_count = sum(
        "timestamp_semantic" in column
        for table in inventory["tables"].values()
        for column in table["columns"]
        if table is not inventory["tables"]["schema_migrations"]
    )
    assert sql.count(" timestamptz") == timestamp_count
    assert (
        "trade_id bigint primary key references dsa.portfolio_trades(id) "
        "on delete cascade"
    ) in sql
    assert "estimated_sellable_at timestamptz not null default" not in sql


def test_vietnam_symbol_currency_and_nonnegative_constraints_are_explicit():
    sql = render_migration()

    for qualified_name in SYMBOL_COLUMNS:
        table_name, column_name = qualified_name.split(".", 1)
        assert f"constraint ck_{table_name}_{column_name}_vn" in sql
    for qualified_name in CURRENCY_COLUMNS:
        table_name, column_name = qualified_name.split(".", 1)
        assert f"constraint ck_{table_name}_{column_name}_vnd" in sql
    assert "[.]VN$" in sql
    assert " = 'VND'" in sql
    assert "_nonnegative check (" in sql


def test_worker_role_is_least_privilege_and_private_tables_use_rls():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    sql = render_migration()
    private_table_count = len(set(inventory["tables"]) - LEGACY_ONLY_TABLES)

    assert "create role dsa_worker login noinherit nobypassrls" in sql
    assert "alter role dsa_worker login noinherit nobypassrls" in sql
    assert "bypassrls;" not in sql.lower().replace("nobypassrls;", "")
    assert "grant usage on schema dsa to dsa_worker;" in sql
    assert "grant select, insert, update, delete on all tables" in sql
    assert "grant all" not in sql.lower()
    assert "grant " not in "\n".join(
        line
        for line in sql.lower().splitlines()
        if (" anon" in line or " authenticated" in line)
    )
    assert sql.count(" enable row level security;") == private_table_count
    assert sql.count("\n  to dsa_worker\n") == private_table_count
    assert sql.count("\n  with check (true);") == private_table_count
    assert "authenticated, service_role" in sql


def test_postgres_index_names_do_not_collide_after_identifier_truncation():
    index_names = re.findall(r"^create (?:unique )?index (\S+) ", render_migration(), re.MULTILINE)
    truncated_names = [name.encode("utf-8")[:63] for name in index_names]

    assert len(truncated_names) == len(set(truncated_names))


def test_dashboard_owned_ddl_is_not_duplicated():
    sql = render_migration()

    for object_name in (
        "analysis_runs",
        "portfolio_cash_entries",
        "portfolio_transactions",
        "portfolio_wallets",
        "watchlist_symbols",
        "enforce_analysis_cooldown",
    ):
        assert object_name not in sql


def test_cli_generated_migration_is_the_current_rendered_contract():
    migrations = list(MIGRATIONS_PATH.glob("*_create_private_dsa_schema.sql"))

    assert len(migrations) == 1
    assert migrations[0].read_text(encoding="utf-8") == render_migration()


def test_private_schema_is_not_exposed_through_the_local_data_api():
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["project_id"] == "daily_stock_analysis"
    assert config["db"]["major_version"] == 17
    assert config["db"]["seed"]["enabled"] is False
    assert "dsa" not in config["api"]["schemas"]
    assert "dsa" not in config["api"]["extra_search_path"]


def test_database_security_suite_covers_required_pr1_principals():
    sql = SECURITY_TEST_PATH.read_text(encoding="utf-8")

    assert "select plan(28);" in sql
    assert "set local role anon;" in sql
    assert sql.count("set local role authenticated;") == 2
    assert "set local role dsa_worker;" in sql
    assert "service-role Data API requests cannot use dsa" in sql
    assert "rolbypassrls" in sql
    assert "rolsuper" in sql
    assert "RLS is enabled on every private table" in sql
    assert "symbols must use canonical uppercase .VN form" in sql
    assert "portfolio currency must be VND" in sql


def test_ci_runs_the_disposable_migration_chain_twice():
    workflow = CI_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)

    assert "database-gate" in parsed["jobs"]
    assert "database-gate:" in workflow
    assert "version: 2.101.0" in workflow
    assert workflow.count("supabase db reset --local") == 2
    assert workflow.count("supabase test db") == 2
    assert "supabase db lint --local --level warning" in workflow
    assert "permissions:\n  contents: read" in workflow
