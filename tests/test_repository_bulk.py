# -*- coding: utf-8 -*-
"""Contracts for bounded repository batch construction."""

from types import SimpleNamespace

from src.repositories.bulk import (
    chunk_mappings,
    is_transient_postgres_error,
    model_to_mapping,
)
from src.repositories.models import BacktestSummary


def test_chunk_mappings_respects_bind_parameter_budget() -> None:
    rows = [
        {"code": "VNM.VN", "date": f"2026-07-{day:02d}", "close": day}
        for day in range(1, 6)
    ]

    chunks = list(
        chunk_mappings(rows, max_bind_parameters=7, max_payload_bytes=10_000)
    )

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert [row for chunk in chunks for row in chunk] == rows


def test_chunk_mappings_respects_utf8_payload_budget() -> None:
    rows = [
        {"title": "Tin Việt Nam", "summary": "ổn định"},
        {"title": "Thị trường", "summary": "tăng trưởng"},
    ]

    one_row_size = len(
        '{"title":"Tin Việt Nam","summary":"ổn định"}'.encode("utf-8")
    )
    chunks = list(
        chunk_mappings(
            rows,
            max_bind_parameters=100,
            max_payload_bytes=one_row_size + 1,
        )
    )

    assert chunks == [[rows[0]], [rows[1]]]


def test_chunk_mappings_keeps_oversized_single_row_progressing() -> None:
    oversized = {"raw_payload": {"body": "x" * 200}}

    assert list(
        chunk_mappings(
            [oversized],
            max_bind_parameters=1,
            max_payload_bytes=10,
        )
    ) == [[oversized]]


def test_model_to_mapping_excludes_identity_and_keeps_native_json() -> None:
    summary = BacktestSummary(
        id=42,
        scope="stock",
        code="VNM.VN",
        eval_window_days=10,
        engine_version="v1",
        advice_breakdown_json={"MUA": 2},
        diagnostics_json={"quality": "đạt"},
    )

    mapping = model_to_mapping(summary)

    assert "id" not in mapping
    assert mapping["code"] == "VNM.VN"
    assert mapping["advice_breakdown_json"] == {"MUA": 2}
    assert mapping["diagnostics_json"] == {"quality": "đạt"}


def test_transient_postgres_error_classification_is_bounded_to_retryable_codes() -> None:
    assert is_transient_postgres_error(
        SimpleNamespace(orig=SimpleNamespace(pgcode="40001"))
    )
    assert is_transient_postgres_error(
        SimpleNamespace(orig=SimpleNamespace(pgcode="40P01"))
    )
    assert is_transient_postgres_error(
        SimpleNamespace(orig=SimpleNamespace(pgcode="08006"))
    )
    assert not is_transient_postgres_error(
        SimpleNamespace(orig=SimpleNamespace(pgcode="23505"))
    )
