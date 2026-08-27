from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.agent.claude import ClaudeRevenueAgent, MockRevenueAgent
from revenue_agent.config import Settings
from revenue_agent.evaluation import evaluate_run
from revenue_agent.models import Account, Signal


class FakeMessages:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = FakeMessages(responses)


def response(content: list[dict[str, Any]], input_tokens: int, output_tokens: int) -> Any:
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason="tool_use"
        if any(item["type"] == "tool_use" for item in content)
        else "end_turn",
    )


def test_mock_run_is_labelled_and_passes_evaluation(seeded_session: Session) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.name))
    run = MockRevenueAgent().analyze(seeded_session, account)  # type: ignore[arg-type]
    result = evaluate_run(seeded_session, run)

    assert run.mode == "mock"
    assert run.model == "deterministic-mock-v1"
    assert run.estimated_cost_usd == 0
    assert result.passed
    assert result.citation_validity == 1


def test_live_agent_uses_strict_tools_and_structured_output(
    seeded_session: Session, settings: Settings
) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.name))
    assert account is not None
    signal = seeded_session.scalar(select(Signal).where(Signal.account_id == account.id))
    assert signal is not None
    brief = {
        "account_name": account.name,
        "qualification": "warm",
        "deterministic_score": account.score,
        "score_summary": "The disclosed deterministic trigger score is unchanged.",
        "observations": [
            {"fact": signal.evidence, "signal_id": signal.id, "source_url": signal.source_url}
        ],
        "hypotheses": ["Hypothesis—not a fact: a quality leader may value faster monitoring."],
        "recommended_action": "human_review",
        "role_target": "VP Quality",
        "outreach_angle": "Ask a human reviewer whether the public enforcement signal is relevant.",
        "risks": ["A public trigger does not prove purchase intent."],
        "confidence": 0.65,
    }
    fake = FakeClient(
        [
            response(
                [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "get_account_signals",
                        "input": {"account_id": account.id},
                    },
                    {
                        "type": "tool_use",
                        "id": "tool-2",
                        "name": "get_scoring_policy",
                        "input": {},
                    },
                ],
                120,
                20,
            ),
            response([{"type": "text", "text": json.dumps(brief)}], 200, 90),
        ]
    )
    live_settings = settings.model_copy(
        update={
            "anthropic_api_key": SecretStr("test-key"),
            "claude_input_usd_per_million": 2.0,
            "claude_output_usd_per_million": 10.0,
        }
    )
    run = ClaudeRevenueAgent(live_settings, client=fake, sleep=lambda _: None).analyze(
        seeded_session, account
    )

    assert run.status == "completed"
    assert run.input_tokens == 320
    assert run.output_tokens == 110
    assert run.estimated_cost_usd == 0.00174
    assert [item["tool"] for item in run.tool_trace] == [
        "get_account_signals",
        "get_scoring_policy",
    ]
    first_call = fake.messages.calls[0]
    assert all(tool["strict"] is True for tool in first_call["tools"])
    assert first_call["output_config"]["format"]["type"] == "json_schema"


def test_retry_honors_retry_after(seeded_session: Session, settings: Settings) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.name))
    assert account is not None

    class RateLimitedMessages:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                error = RuntimeError("rate limited")
                error.status_code = 429  # type: ignore[attr-defined]
                error.response = SimpleNamespace(headers={"retry-after": "2.5"})  # type: ignore[attr-defined]
                raise error
            raise RuntimeError("stop test after retry")

    waits: list[float] = []
    fake = SimpleNamespace(messages=RateLimitedMessages())
    agent = ClaudeRevenueAgent(
        settings.model_copy(
            update={"anthropic_api_key": SecretStr("test-key"), "claude_max_retries": 1}
        ),
        client=fake,
        sleep=waits.append,
    )
    run = agent.analyze(seeded_session, account)
    assert run.status == "failed"
    assert waits == [2.5]
