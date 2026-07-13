#!/usr/bin/env python3
"""Generate the bundled Vietnam-only autocomplete index from vnstock listings.

The generated tuple format remains wire-compatible with the existing Web and
backend loaders. Field 2 is now a general display name; the historical
``nameZh`` TypeScript property is retained temporarily for API compatibility.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUTS = (
    REPO_ROOT / "apps" / "dsa-web" / "public" / "stocks.index.json",
    REPO_ROOT / "static" / "stocks.index.json",
)
SUPPORTED_EXCHANGES = {"HOSE", "HNX", "UPCOM"}
POPULAR_SYMBOLS = {
    "VNM": 100,
    "MBB": 99,
    "FPT": 98,
    "VCB": 97,
    "HPG": 96,
    "VIC": 95,
    "VHM": 94,
    "SSI": 93,
}


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def build_vietnam_index(active_symbols: pd.DataFrame, listings: pd.DataFrame) -> list[list[Any]]:
    """Build deterministic compressed index rows from vnstock DataFrames."""
    required_active = {"symbol"}
    required_listing = {"symbol", "organ_name", "en_organ_name", "exchange", "type"}
    if not required_active.issubset(active_symbols.columns):
        raise ValueError("active-symbol payload is missing the symbol column")
    if not required_listing.issubset(listings.columns):
        missing = sorted(required_listing - set(listings.columns))
        raise ValueError(f"exchange listing payload is missing columns: {', '.join(missing)}")

    active = {
        _clean_text(symbol).upper()
        for symbol in active_symbols["symbol"].tolist()
        if _clean_text(symbol)
    }
    rows: list[list[Any]] = []
    seen: set[str] = set()

    for record in listings.to_dict(orient="records"):
        symbol = _clean_text(record.get("symbol")).upper()
        exchange = _clean_text(record.get("exchange")).upper()
        security_type = _clean_text(record.get("type")).lower()
        if (
            not symbol
            or symbol in seen
            or symbol not in active
            or exchange not in SUPPORTED_EXCHANGES
            or security_type != "stock"
        ):
            continue

        english_name = _clean_text(record.get("en_organ_name"))
        vietnamese_name = _clean_text(record.get("organ_name"))
        display_name = english_name or vietnamese_name or symbol
        aliases = [name for name in (vietnamese_name, english_name, exchange) if name and name != display_name]
        rows.append([
            f"{symbol}.VN",
            symbol,
            display_name,
            "",
            "",
            aliases,
            "VN",
            "stock",
            True,
            POPULAR_SYMBOLS.get(symbol, 1),
        ])
        seen.add(symbol)

    rows.sort(key=lambda item: (-int(item[9]), item[1]))
    if len(rows) < 1000:
        raise ValueError(f"Vietnam stock index is unexpectedly small: {len(rows)}")
    return rows


def fetch_vietnam_listings() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch the active list and exchange metadata through the pinned adapter."""
    from vnstock import Listing

    listing = Listing(source="kbs", show_log=False)
    return listing.all_symbols(), listing.symbols_by_exchange()


def write_index(rows: list[list[Any]], outputs: tuple[Path, ...] = DEFAULT_OUTPUTS) -> None:
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n"
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", action="append", type=Path, help="Override output path (repeatable)")
    args = parser.parse_args()

    active, listings = fetch_vietnam_listings()
    rows = build_vietnam_index(active, listings)
    outputs = tuple(args.output) if args.output else DEFAULT_OUTPUTS
    write_index(rows, outputs)
    print(f"Generated {len(rows)} Vietnam stock entries in {len(outputs)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
