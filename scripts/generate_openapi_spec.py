"""Regenerate the checked-in OpenAPI artifact from the FastAPI application."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from api.app import create_app  # noqa: E402


OUTPUT_PATH = REPO_ROOT / "docs" / "architecture" / "api_spec.json"


def main() -> None:
    payload = create_app().openapi()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
