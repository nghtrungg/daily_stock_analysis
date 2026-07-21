# -*- coding: utf-8 -*-
"""Vietnam-localized numeric display helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def format_vnd_amount(value: Any, *, include_currency: bool = True) -> str:
    """Format an actual-VND amount with dots as thousands separators."""

    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)

    if not amount.is_finite():
        return str(value)

    sign = "-" if amount < 0 else ""
    absolute = abs(amount)
    raw = format(absolute, "f")
    integer_part, _, fractional_part = raw.partition(".")
    grouped = f"{int(integer_part):,}".replace(",", ".")
    fractional_part = fractional_part.rstrip("0")
    rendered = f"{sign}{grouped}"
    if fractional_part:
        rendered += f",{fractional_part}"
    return f"{rendered} VND" if include_currency else rendered
