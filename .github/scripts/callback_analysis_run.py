"""Post a signed GitHub Actions analysis result to Personal Stock Tracking."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


RUN_ID_PATTERN: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SUCCESS_SUMMARY: Final = (
    "GitHub Actions completed the requested Vietnam stock analysis. "
    "Check your configured report delivery channel for the generated report."
)


def is_safe_callback_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.username is None and parsed.password is None


def encode_callback_payload(run_id: str, status: str) -> str:
    if status == "succeeded":
        payload = {"runId": run_id, "status": status, "summary": SUCCESS_SUMMARY}
    elif status == "failed":
        payload = {"runId": run_id, "status": status, "errorCode": "PROCESSING_FAILED"}
    else:
        raise ValueError("callback status must be succeeded or failed")

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def sign_payload(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def send_callback(callback_url: str, secret: str, payload: str) -> None:
    request = Request(
        callback_url,
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-analysis-signature": sign_payload(secret, payload),
        },
    )
    with urlopen(request, timeout=15) as response:  # noqa: S310 - URL is validated and comes from repository configuration.
        if not 200 <= response.status < 300:
            raise RuntimeError(f"callback returned HTTP {response.status}")


def main() -> int:
    run_id = os.environ.get("ANALYSIS_CALLBACK_RUN_ID", "").strip()
    callback_url = os.environ.get("ANALYSIS_CALLBACK_URL", "").strip()
    callback_secret = os.environ.get("ANALYSIS_CALLBACK_SECRET", "")
    status = os.environ.get("ANALYSIS_CALLBACK_STATUS", "").strip()

    if not RUN_ID_PATTERN.fullmatch(run_id):
        print("Analysis callback run ID is invalid.", file=sys.stderr)
        return 2
    if not is_safe_callback_url(callback_url):
        print("Analysis callback URL must be an HTTPS endpoint.", file=sys.stderr)
        return 2
    if not callback_secret:
        print("Analysis callback secret is not configured.", file=sys.stderr)
        return 2

    try:
        send_callback(callback_url, callback_secret, encode_callback_payload(run_id, status))
    except (HTTPError, URLError, RuntimeError, ValueError):
        print("Analysis callback request failed.", file=sys.stderr)
        return 1

    print("Analysis callback recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
