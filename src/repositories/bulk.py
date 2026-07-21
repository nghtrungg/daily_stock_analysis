# -*- coding: utf-8 -*-
"""Shared bounded-batch helpers for repository writes."""

from __future__ import annotations

import json
from typing import Any, Iterable, Iterator, Mapping, Sequence

from sqlalchemy import inspect as sqlalchemy_inspect


DEFAULT_MAX_BIND_PARAMETERS = 30_000
DEFAULT_MAX_PAYLOAD_BYTES = 1_000_000


def _mapping_payload_bytes(mapping: Mapping[str, Any]) -> int:
    return len(
        json.dumps(
            mapping,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def chunk_mappings(
    mappings: Iterable[Mapping[str, Any]],
    *,
    max_bind_parameters: int = DEFAULT_MAX_BIND_PARAMETERS,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> Iterator[list[dict[str, Any]]]:
    """Yield batches bounded by both bind count and serialized payload bytes."""
    if max_bind_parameters < 1 or max_payload_bytes < 1:
        raise ValueError("Batch limits must be positive.")

    chunk: list[dict[str, Any]] = []
    bind_count = 0
    payload_bytes = 0
    for source in mappings:
        row = dict(source)
        row_bind_count = len(row)
        row_payload_bytes = _mapping_payload_bytes(row)
        exceeds_current = chunk and (
            bind_count + row_bind_count > max_bind_parameters
            or payload_bytes + row_payload_bytes > max_payload_bytes
        )
        if exceeds_current:
            yield chunk
            chunk = []
            bind_count = 0
            payload_bytes = 0

        chunk.append(row)
        bind_count += row_bind_count
        payload_bytes += row_payload_bytes

    if chunk:
        yield chunk


def model_to_mapping(instance: Any, *, exclude: Sequence[str] = ("id",)) -> dict[str, Any]:
    """Convert one mapped ORM object to native column values for bulk DML."""
    excluded = set(exclude)
    mapper = sqlalchemy_inspect(type(instance))
    state_values = sqlalchemy_inspect(instance).dict
    return {
        column.key: state_values[column.key]
        for column in mapper.columns
        if column.key not in excluded and column.key in state_values
    }


def is_transient_postgres_error(exc: BaseException) -> bool:
    """Return whether a PostgreSQL failure is safe for bounded transaction retry."""
    if bool(getattr(exc, "connection_invalidated", False)):
        return True
    original = getattr(exc, "orig", exc)
    sqlstate = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    if not sqlstate:
        return False
    return str(sqlstate).startswith("08") or str(sqlstate) in {"40001", "40P01"}
