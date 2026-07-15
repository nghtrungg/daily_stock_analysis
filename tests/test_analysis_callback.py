"""Regression coverage for the GitHub Actions to Supabase callback contract."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "callback_analysis_run.py"
SPEC = importlib.util.spec_from_file_location("callback_analysis_run", SCRIPT_PATH)
assert SPEC and SPEC.loader
callback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(callback)


RUN_ID = "a59a1476-2ea4-4c86-9a3c-d0df438e8102"


def test_success_callback_uses_a_signed_minimal_payload() -> None:
    body = callback.encode_callback_payload(RUN_ID, "succeeded")

    assert json.loads(body) == {
        "runId": RUN_ID,
        "status": "succeeded",
        "summary": "GitHub Actions completed the requested Vietnam stock analysis. Check your configured report delivery channel for the generated report.",
    }
    assert callback.sign_payload("callback-secret", body) == hmac.new(
        b"callback-secret", body.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def test_callback_configuration_rejects_non_https_endpoints() -> None:
    assert callback.is_safe_callback_url("https://project.supabase.co/functions/v1/analysis-callback")
    assert not callback.is_safe_callback_url("http://localhost:54321/functions/v1/analysis-callback")
