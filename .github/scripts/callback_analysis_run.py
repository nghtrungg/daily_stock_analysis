"""Post a signed, current-run quote result to Personal Stock Tracking."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


RUN_ID_PATTERN: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
VIETNAM_SYMBOL_PATTERN: Final = re.compile(r"^[A-Z0-9]{1,10}[.]VN$")
SUCCESS_SUMMARY: Final = "Phân tích đã hoàn tất và đã lưu giá tại thời điểm phân tích."
VIETNAM_TIMEZONE: Final = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991
MAX_CALLBACK_ATTEMPTS: Final = 3
MAX_REPORT_BYTES: Final = 40_000


class QuoteUnavailableError(ValueError):
    """The current workflow did not produce one safe quote for the requested symbol."""


def is_safe_callback_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.username is None and parsed.password is None


def parse_timestamp(value: str, *, assume_vietnam_time: bool = False) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        if not assume_vietnam_time:
            raise ValueError("timestamp must include a timezone")
        parsed = parsed.replace(tzinfo=VIETNAM_TIMEZONE)
    return parsed


def normalize_vnd_price(value: object) -> int:
    if isinstance(value, bool):
        raise QuoteUnavailableError("quote price is invalid")
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise QuoteUnavailableError("quote price is invalid") from None
    if not numeric.is_finite() or numeric <= 0:
        raise QuoteUnavailableError("quote price is invalid")
    normalized = int(numeric.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if normalized <= 0 or normalized > MAX_SAFE_INTEGER:
        raise QuoteUnavailableError("quote price is outside the supported VND range")
    return normalized


def _current_run_row(database_path: str, symbol: str, workflow_started_at: str) -> tuple[object, ...]:
    canonical_symbol = symbol.strip().upper()
    if not VIETNAM_SYMBOL_PATTERN.fullmatch(canonical_symbol):
        raise QuoteUnavailableError("requested symbol is invalid")
    try:
        started_at = parse_timestamp(workflow_started_at)
    except (ValueError, TypeError):
        raise QuoteUnavailableError("workflow start time is invalid") from None

    path = Path(database_path).expanduser()
    if not path.is_file():
        raise QuoteUnavailableError("analysis database is unavailable")

    try:
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                """
                select id, code, name, report_type, sentiment_score,
                       operation_advice, trend_prediction, analysis_summary,
                       raw_result, created_at
                from analysis_history
                where code = ?
                order by created_at desc, id desc
                limit 10
                """,
                (canonical_symbol,),
            ).fetchall()
    except (sqlite3.Error, OSError):
        raise QuoteUnavailableError("analysis database could not be read") from None

    current_rows: list[tuple[object, ...]] = []
    for row in rows:
        row_id, code, name, report_type, sentiment_score, operation_advice, trend_prediction, analysis_summary, raw_result, created_at_value = row
        if code != canonical_symbol or not isinstance(created_at_value, str):
            continue
        try:
            created_at = parse_timestamp(created_at_value, assume_vietnam_time=True)
        except ValueError:
            continue
        if created_at >= started_at:
            current_rows.append((
                row_id, code, name, report_type, sentiment_score, operation_advice,
                trend_prediction, analysis_summary, raw_result, created_at,
            ))

    if len(current_rows) != 1:
        raise QuoteUnavailableError("current-run quote record is missing or ambiguous")

    return current_rows[0]


def _required_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise QuoteUnavailableError(f"{label} is invalid")
    return value.strip()


def extract_current_run_analysis(database_path: str, symbol: str, workflow_started_at: str) -> dict[str, object]:
    (
        _, code, name, report_type, sentiment_score, operation_advice,
        trend_prediction, analysis_summary, raw_result_value, created_at,
    ) = _current_run_row(database_path, symbol, workflow_started_at)
    try:
        raw_result = json.loads(raw_result_value)
    except (json.JSONDecodeError, TypeError):
        raise QuoteUnavailableError("analysis quote payload is invalid") from None
    if not isinstance(raw_result, dict):
        raise QuoteUnavailableError("analysis quote payload is invalid")

    price = raw_result.get("current_price")
    if isinstance(price, float) and not math.isfinite(price):
        raise QuoteUnavailableError("quote price is invalid")
    source = raw_result.get("data_sources")
    if not isinstance(source, str) or not source.strip() or len(source) > 120:
        raise QuoteUnavailableError("quote source is invalid")

    if isinstance(sentiment_score, bool) or not isinstance(sentiment_score, int) or not 0 <= sentiment_score <= 100:
        raise QuoteUnavailableError("report sentiment score is invalid")
    dashboard = raw_result.get("dashboard")
    if dashboard is not None and not isinstance(dashboard, dict):
        raise QuoteUnavailableError("report dashboard is invalid")

    report = {
        "code": code,
        "name": _required_text(name, "report name", 120),
        "reportType": _required_text(report_type, "report type", 32),
        "sentimentScore": sentiment_score,
        "operationAdvice": _required_text(operation_advice, "operation advice", 120),
        "trendPrediction": _required_text(trend_prediction, "trend prediction", 120),
        "dashboard": dashboard,
    }
    if len(json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_REPORT_BYTES:
        raise QuoteUnavailableError("report is too large")

    analysis_date = created_at.astimezone(VIETNAM_TIMEZONE).isoformat(timespec="seconds")
    return {
        "summary": _required_text(analysis_summary, "analysis summary", 4_000),
        "analysisDate": analysis_date,
        "report": report,
        "quote": {
            "currentPriceVnd": normalize_vnd_price(price),
            "asOf": analysis_date,
            "source": source.strip(),
        },
    }


def extract_current_run_quote(database_path: str, symbol: str, workflow_started_at: str) -> dict[str, object]:
    """Compatibility helper retained for focused quote callers."""
    return extract_current_run_analysis(database_path, symbol, workflow_started_at)["quote"]  # type: ignore[return-value]


def encode_callback_payload(
    run_id: str,
    status: str,
    quote: dict[str, object] | None = None,
    *,
    analysis_date: str | None = None,
    report: dict[str, object] | None = None,
    summary: str = SUCCESS_SUMMARY,
) -> str:
    if status == "succeeded":
        if quote is None or analysis_date is None or report is None:
            raise ValueError("a successful callback requires a quote and report")
        payload = {
            "runId": run_id,
            "status": status,
            "summary": summary,
            "analysisDate": analysis_date,
            "report": report,
            "quote": quote,
        }
    elif status == "quote-unavailable":
        payload = {"runId": run_id, "status": "failed", "errorCode": "QUOTE_UNAVAILABLE"}
    elif status == "failed":
        payload = {"runId": run_id, "status": status, "errorCode": "PROCESSING_FAILED"}
    else:
        raise ValueError("callback status is invalid")
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def sign_payload(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def send_callback(
    callback_url: str,
    secret: str,
    payload: str,
    *,
    opener: Callable[..., object] = urlopen,
) -> None:
    request = Request(
        callback_url,
        data=payload.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "x-analysis-signature": sign_payload(secret, payload)},
    )
    response_context = opener(request, timeout=15)  # noqa: S310 - validated configured HTTPS endpoint.
    with response_context as response:
        status = getattr(response, "status", 0)
        if not isinstance(status, int) or not 200 <= status < 300:
            raise RuntimeError("callback returned a non-success status")


def delivery_error_category(error: BaseException) -> str:
    if isinstance(error, HTTPError):
        return "http_error"
    if isinstance(error, URLError):
        return "network_error"
    if isinstance(error, RuntimeError):
        return "invalid_response"
    return "request_error"


def deliver_callback(
    run_id: str,
    callback_url: str,
    secret: str,
    payload: str,
    *,
    opener: Callable[..., object] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    attempts: int = MAX_CALLBACK_ATTEMPTS,
) -> bool:
    bounded_attempts = max(1, min(attempts, MAX_CALLBACK_ATTEMPTS))
    for attempt in range(1, bounded_attempts + 1):
        try:
            send_callback(callback_url, secret, payload, opener=opener)
            print(f"analysis_callback run={run_id} attempt={attempt} category=delivered")
            return True
        except (HTTPError, URLError, RuntimeError, OSError) as error:
            print(
                f"analysis_callback run={run_id} attempt={attempt} category={delivery_error_category(error)}",
                file=sys.stderr,
            )
            if attempt < bounded_attempts:
                sleeper(float(2 ** (attempt - 1)))
    return False


def main() -> int:
    run_id = os.environ.get("ANALYSIS_CALLBACK_RUN_ID", "").strip()
    callback_url = os.environ.get("ANALYSIS_CALLBACK_URL", "").strip()
    callback_secret = os.environ.get("ANALYSIS_CALLBACK_SECRET", "")
    status = os.environ.get("ANALYSIS_CALLBACK_STATUS", "").strip()
    symbol = os.environ.get("ANALYSIS_CALLBACK_SYMBOL", "").strip()
    workflow_started_at = os.environ.get("ANALYSIS_CALLBACK_STARTED_AT", "").strip()
    database_path = os.environ.get("DATABASE_PATH", "./data/stock_analysis_vn.db").strip()

    if not RUN_ID_PATTERN.fullmatch(run_id):
        print("Analysis callback run ID is invalid.", file=sys.stderr)
        return 2
    if not is_safe_callback_url(callback_url):
        print("Analysis callback URL must be an HTTPS endpoint.", file=sys.stderr)
        return 2
    if not callback_secret:
        print("Analysis callback secret is not configured.", file=sys.stderr)
        return 2
    if status not in {"succeeded", "failed"}:
        print("Analysis callback status is invalid.", file=sys.stderr)
        return 2

    try:
        if status == "succeeded":
            try:
                projection = extract_current_run_analysis(database_path, symbol, workflow_started_at)
                payload = encode_callback_payload(
                    run_id,
                    "succeeded",
                    projection["quote"],  # type: ignore[arg-type]
                    analysis_date=str(projection["analysisDate"]),
                    report=projection["report"],  # type: ignore[arg-type]
                    summary=str(projection["summary"]),
                )
            except QuoteUnavailableError:
                payload = encode_callback_payload(run_id, "quote-unavailable")
        else:
            payload = encode_callback_payload(run_id, "failed")
    except ValueError:
        print("Analysis callback configuration is invalid.", file=sys.stderr)
        return 2

    if not deliver_callback(run_id, callback_url, callback_secret, payload):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
