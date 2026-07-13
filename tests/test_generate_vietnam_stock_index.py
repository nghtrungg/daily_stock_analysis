"""Tests for the deterministic Vietnam autocomplete-index generator."""

import pandas as pd
import pytest

from scripts.generate_vietnam_stock_index import build_vietnam_index


def _frames(count: int = 1001) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = [f"S{i:04d}" for i in range(count)]
    active = pd.DataFrame({"symbol": symbols})
    listings = pd.DataFrame({
        "symbol": symbols + ["AAPL", "600519"],
        "organ_name": [f"Công ty {symbol}" for symbol in symbols] + ["Apple", "Kweichow"],
        "en_organ_name": [f"Company {symbol}" for symbol in symbols] + ["Apple", "Kweichow"],
        "exchange": ["HOSE"] * count + ["NASDAQ", "SSE"],
        "type": ["stock"] * (count + 2),
    })
    return active, listings


def test_generator_emits_only_explicit_vietnam_symbols() -> None:
    active, listings = _frames()
    rows = build_vietnam_index(active, listings)

    assert len(rows) == 1001
    assert all(row[0].endswith(".VN") for row in rows)
    assert all(row[6] == "VN" for row in rows)
    assert {row[1] for row in rows}.isdisjoint({"AAPL", "600519"})


def test_generator_rejects_unexpectedly_small_provider_payload() -> None:
    active, listings = _frames(2)

    with pytest.raises(ValueError, match="unexpectedly small"):
        build_vietnam_index(active, listings)
