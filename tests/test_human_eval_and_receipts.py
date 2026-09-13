from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.human_eval import build_human_label_queue, evaluate_human_labels
from revenue_agent.models import Account, AgentRun
from revenue_agent.receipts import build_live_receipt


def test_human_label_queue_is_unlabelled_and_has_40_cases(seeded_session: Session) -> None:
    rows = build_human_label_queue(seeded_session)
    assert len(rows) == 40
    assert all(row["human_label"] is None for row in rows)
    assert all(row["reviewer"] is None for row in rows)


def test_human_evaluation_requires_real_reviewer_attribution(
    seeded_session: Session,
) -> None:
    rows = build_human_label_queue(seeded_session)
    for row in rows[:30]:
        row["human_label"] = "supported" if row["claim_id"].endswith("-1") else "unsupported"
        row["reviewer"] = "test-reviewer"
    report = evaluate_human_labels(seeded_session, rows)
    assert report["labelled_rows"] == 30
    assert report["agreement_rate"] == 1.0
    assert report["precision_supported"] == 1.0
    assert report["recall_supported"] == 1.0


def test_live_receipt_excludes_raw_trace_and_can_include_output(
    seeded_session: Session,
) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.name))
    assert account is not None
    run = AgentRun(
        account_id=account.id,
        mode="live",
        model="claude-test",
        status="failed",
        prompt_version="test-v1",
        output={"account_name": account.name},
        tool_trace=[{"tool": "get_account_signals", "result": {"private": "omitted"}}],
        input_tokens=100,
        output_tokens=20,
        estimated_cost_usd=0.0004,
        latency_ms=150,
        error_type="grounding_rejected",
    )
    seeded_session.add(run)
    seeded_session.commit()

    public = build_live_receipt(run)
    assert public["tool_calls"] == ["get_account_signals"]
    assert "private" not in str(public)
    assert "output" not in public
    assert public["output_sha256"]
    assert build_live_receipt(run, include_output=True)["output"] == run.output
