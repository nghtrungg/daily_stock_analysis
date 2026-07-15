"""Workflow contract tests for Personal Stock Tracking dispatches."""

from pathlib import Path

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "00-daily-analysis.yml"


def test_personal_tracking_dispatch_inputs_override_only_the_current_run() -> None:
    workflow = yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]

    assert inputs["stock_symbols"]["type"] == "string"
    assert inputs["tracking_run_id"]["type"] == "string"

    steps = workflow["jobs"]["analyze"]["steps"]
    analysis_step = next(step for step in steps if step.get("id") == "analysis")
    callback_step = next(step for step in steps if step["name"] == "Signal Personal Stock Tracking")

    assert "TRACKING_STOCK_SYMBOLS" in analysis_step["env"]
    assert "export STOCK_LIST=\"$TRACKING_STOCK_SYMBOLS\"" in analysis_step["run"]
    assert "MODE=\"stocks-only\"" in analysis_step["run"]
    assert callback_step["if"] == "always() && inputs.tracking_run_id != ''"
