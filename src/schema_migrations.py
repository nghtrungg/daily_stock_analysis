"""Small ordered schema migration runner for the local SQLAlchemy database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


MigrationUpgrade = Callable[[Connection, Any], None]


@dataclass(frozen=True)
class SchemaMigration:
    """One deterministic, idempotent schema upgrade."""

    version: str
    description: str
    upgrade: MigrationUpgrade


class SchemaMigrationError(RuntimeError):
    """Raised when a required schema migration cannot be completed."""


def validate_migrations(migrations: Iterable[SchemaMigration]) -> tuple[SchemaMigration, ...]:
    """Return migrations as a validated, strictly ordered tuple."""
    ordered = tuple(migrations)
    versions = [migration.version for migration in ordered]
    if versions != sorted(versions):
        raise ValueError("Schema migrations must be declared in ascending version order")
    if len(versions) != len(set(versions)):
        raise ValueError("Schema migration versions must be unique")
    for migration in ordered:
        if not migration.version.strip() or not migration.description.strip():
            raise ValueError("Schema migration version and description are required")
    return ordered


def run_ordered_migrations(
    engine: Engine,
    *,
    migration_table: str,
    migrations: Sequence[SchemaMigration],
    context: Any = None,
) -> None:
    """Apply unapplied migrations and record each version atomically.

    SQLite uses ``BEGIN IMMEDIATE`` so concurrent initializers serialize before
    checking the applied-version table. Other SQLAlchemy backends use the
    dialect's normal transaction handling.
    """
    ordered = validate_migrations(migrations)
    for migration in ordered:
        connection = engine.connect()
        transaction = None
        try:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                transaction = connection.begin()

            already_applied = connection.execute(
                text(
                    f'SELECT 1 FROM "{migration_table}" '
                    "WHERE version = :version LIMIT 1"
                ),
                {"version": migration.version},
            ).scalar()
            if already_applied:
                if transaction is not None:
                    transaction.commit()
                else:
                    connection.commit()
                continue

            migration.upgrade(connection, context)
            connection.execute(
                text(
                    f'INSERT INTO "{migration_table}" '
                    "(version, description, applied_at) "
                    "VALUES (:version, :description, CURRENT_TIMESTAMP)"
                ),
                {
                    "version": migration.version,
                    "description": migration.description,
                },
            )
            if transaction is not None:
                transaction.commit()
            else:
                connection.commit()
        except Exception as exc:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            else:
                connection.rollback()
            raise SchemaMigrationError(
                "Database migration "
                f"{migration.version!r} ({migration.description}) failed. "
                "The database was not reset; restore the original schema or "
                "fix the migration error before restarting."
            ) from exc
        finally:
            connection.close()
