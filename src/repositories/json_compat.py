# -*- coding: utf-8 -*-
"""Field-aware compatibility for legacy JSON text and PostgreSQL JSONB."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Iterable, Type

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class InvalidLegacyJSON(ValueError):
    """Raised when an imported JSON field cannot be decoded safely."""


def normalize_json_value(
    value: Any,
    *,
    field_name: str,
    expected_types: Iterable[Type[Any]] = (dict, list),
    sql_null_value: Any = None,
    json_null_value: Any = None,
) -> Any:
    """Return a fresh native JSON value without silently coercing invalid data.

    ``None`` is SQL NULL. A legacy string containing ``null`` is JSON null.
    Callers can preserve or distinguish those states through the two explicit
    replacement values.
    """
    if value is None:
        return deepcopy(sql_null_value)

    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            if str in tuple(expected_types):
                return str(value)
            raise InvalidLegacyJSON(
                f"Invalid legacy JSON in {field_name}."
            ) from exc
        if decoded is None:
            return deepcopy(json_null_value)

    allowed = tuple(expected_types)
    if not isinstance(decoded, allowed):
        names = ", ".join(item.__name__ for item in allowed)
        raise InvalidLegacyJSON(
            f"{field_name} must contain one of: {names}."
        )
    return deepcopy(decoded)


class LegacyJSONB(TypeDecorator[Any]):
    """JSONB on PostgreSQL and legacy JSON text on SQLite.

    PostgreSQL-facing repositories receive native values. SQLite continues to
    expose strings during the importer/test transition so existing local
    contracts remain stable until the cutover.
    """

    impl = Text
    cache_ok = True

    def __init__(
        self,
        *,
        field_name: str,
        expected_types: Iterable[Type[Any]] = (dict, list),
    ) -> None:
        super().__init__()
        self.field_name = field_name
        self.expected_types = tuple(expected_types)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name != "postgresql":
            if isinstance(value, str):
                return value
            return json.dumps(value, ensure_ascii=False, default=str)
        native = normalize_json_value(
            value,
            field_name=self.field_name,
            expected_types=self.expected_types,
        )
        return native

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)
