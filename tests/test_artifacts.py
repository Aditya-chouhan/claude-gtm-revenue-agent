from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from revenue_agent.models import stable_id

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_n8n_workflow_has_triggers_retries_and_error_branch() -> None:
    workflow = load_json("n8n/claude-gtm-revenue-agent.json")
    nodes = {node["name"]: node for node in workflow["nodes"]}

    assert "Manual Run" in nodes
    assert "Daily 07:00" in nodes
    pipeline = nodes["Run Revenue Agent Pipeline"]
    assert pipeline["retryOnFail"] is True
    assert pipeline["maxTries"] == 3
    outputs = workflow["connections"]["Run Revenue Agent Pipeline"]["main"]
    assert outputs[1][0]["node"] == "Build Failure Alert"


def test_committed_real_and_simulated_data_are_separate() -> None:
    fixture = load_json("data/real/openfda_snapshot.json")
    live_receipt = load_json("data/real/live_ingestion_receipt_2026-08-27.json")
    mock_receipt = load_json("data/simulated/offline_run_receipt_2026-08-27.json")
    mock_brief = load_json("data/simulated/sample_account_brief.json")

    assert fixture["data_classification"] == "real_public_data"
    assert live_receipt["data_classification"] == "real_public_live_run_receipt"
    assert mock_receipt["data_classification"] == "simulated_agent_output_receipt"
    assert mock_brief["data_classification"] == "simulated_agent_output"
    assert mock_receipt["agent"]["claude_api_called"] is False


def test_public_source_identity_is_stable_across_runs() -> None:
    assert stable_id("signal", "openfda:D-0656-2026") == ("2983a782-088f-53ce-86f6-f13b82af2eeb")
