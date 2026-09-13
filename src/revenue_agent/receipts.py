from __future__ import annotations

import hashlib
import json
from typing import Any

from revenue_agent.models import AgentRun


def build_live_receipt(run: AgentRun, *, include_output: bool = False) -> dict[str, Any]:
    if run.mode != "live":
        raise ValueError("a live-inference receipt can only be built from mode=live")
    if run.input_tokens + run.output_tokens <= 0:
        raise ValueError("a live-inference receipt requires non-zero provider token usage")
    serialized = json.dumps(run.output, sort_keys=True, separators=(",", ":")) if run.output else ""
    receipt: dict[str, Any] = {
        "data_classification": "authorized_live_claude_inference",
        "receipt_version": "live-inference-v1",
        "run_id": run.id,
        "account_id": run.account_id,
        "created_at": run.created_at.isoformat(),
        "model": run.model,
        "status": run.status,
        "prompt_version": run.prompt_version,
        "latency_ms": run.latency_ms,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "estimated_cost_usd": run.estimated_cost_usd,
        "error_type": run.error_type,
        "tool_calls": [item.get("tool") for item in run.tool_trace],
        "output_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        if serialized
        else None,
        "notice": "Secrets and raw tool results are excluded from this public receipt.",
    }
    if include_output:
        receipt["output"] = run.output
    return receipt
