from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections import deque
from typing import Any, cast

from anthropic import Anthropic, transform_schema
from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.config import Settings
from revenue_agent.costs import assert_budget_available, estimate_cost_usd
from revenue_agent.models import Account, AgentRun, Signal
from revenue_agent.observability import AGENT_CALLS, AGENT_COST
from revenue_agent.schemas import AccountBrief
from revenue_agent.scoring import scoring_policy

LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "account-brief-v1"

SYSTEM_PROMPT = """You are an evidence-grounded GTM revenue analyst.
Use the supplied tools before reaching a conclusion. Separate sourced observations from
hypotheses. Never invent a person, email, phone number, customer relationship, revenue
impact, or campaign result. A deterministic score measures buying-trigger intensity only;
it is not a quality verdict. Recommend human review before any CRM or outreach action.
Every observation must cite exactly one signal_id and its matching source_url.
"""


class LocalRateLimiter:
    """Process-local request limiter; provider headers remain the global source of truth."""

    def __init__(
        self, requests_per_minute: int, clock: Any = time.monotonic, sleep: Any = time.sleep
    ):
        self.limit = requests_per_minute
        self.clock = clock
        self.sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self.clock()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.limit:
                    self._calls.append(now)
                    return
                delay = max(60 - (now - self._calls[0]), 0.01)
            self.sleep(delay)


def _block_value(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _serialize_block(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return dict(block)
    if hasattr(block, "model_dump"):
        return cast(dict[str, Any], block.model_dump(exclude_none=True))
    raise TypeError(f"Unsupported Claude content block: {type(block)!r}")


def _usage(response: Any, key: str) -> int:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(key, 0))
    return int(getattr(usage, key, 0))


class ClaudeRevenueAgent:
    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        sleep: Any = time.sleep,
        random_source: Any = random.random,
    ) -> None:
        self.settings = settings
        api_key = (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        if client is None and not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for live agent mode")
        self.client = client or Anthropic(api_key=api_key, max_retries=0)
        self.sleep = sleep
        self.random_source = random_source
        self.rate_limiter = LocalRateLimiter(settings.claude_requests_per_minute, sleep=sleep)

    def analyze(self, session: Session, account: Account) -> AgentRun:
        assert_budget_available(session, self.settings.claude_monthly_budget_usd)
        started = time.perf_counter()
        run = AgentRun(
            account_id=account.id,
            mode="live",
            model=self.settings.claude_model,
            status="running",
            prompt_version=PROMPT_VERSION,
        )
        session.add(run)
        session.flush()
        try:
            output, trace, input_tokens, output_tokens = self._run_loop(session, account)
            self._validate_grounding(session, account, output)
            run.output = output.model_dump(mode="json")
            run.tool_trace = json.loads(json.dumps(trace, default=str))
            run.input_tokens = input_tokens
            run.output_tokens = output_tokens
            run.estimated_cost_usd = estimate_cost_usd(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_usd_per_million=self.settings.claude_input_usd_per_million,
                output_usd_per_million=self.settings.claude_output_usd_per_million,
            )
            run.status = "completed"
            AGENT_CALLS.labels("live", "completed").inc()
            AGENT_COST.labels(self.settings.claude_model).inc(run.estimated_cost_usd)
        except Exception as exc:
            run.status = "failed"
            run.error_type = type(exc).__name__
            run.error_message = str(exc)[:2000]
            AGENT_CALLS.labels("live", "failed").inc()
            LOGGER.exception(
                "claude_agent_failed", extra={"account_id": account.id, "run_id": run.id}
            )
        finally:
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            session.commit()
        return run

    def _run_loop(
        self, session: Session, account: Account
    ) -> tuple[AccountBrief, list[dict[str, Any]], int, int]:
        tools = self._tools()
        output_schema = transform_schema(AccountBrief.model_json_schema())
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Analyze account_id={account.id}. First inspect its stored signals and the "
                    "deterministic scoring policy. Return a concise, source-grounded account brief."
                ),
            }
        ]
        trace: list[dict[str, Any]] = []
        input_tokens = 0
        output_tokens = 0

        for iteration in range(5):
            response = self._create_message(
                model=self.settings.claude_model,
                max_tokens=self.settings.claude_max_tokens,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
                tool_choice={"type": "any"} if iteration == 0 else {"type": "auto"},
                output_config={"format": {"type": "json_schema", "schema": output_schema}},
            )
            input_tokens += _usage(response, "input_tokens")
            output_tokens += _usage(response, "output_tokens")
            blocks = list(response.content)
            tool_blocks = [block for block in blocks if _block_value(block, "type") == "tool_use"]
            if not tool_blocks:
                text_blocks = [
                    _block_value(block, "text", "")
                    for block in blocks
                    if _block_value(block, "type") == "text"
                ]
                raw = "".join(text_blocks).strip()
                if not raw:
                    raise RuntimeError(
                        f"Claude returned no final JSON; stop_reason={response.stop_reason}"
                    )
                return AccountBrief.model_validate_json(raw), trace, input_tokens, output_tokens

            messages.append(
                {"role": "assistant", "content": [_serialize_block(block) for block in blocks]}
            )
            results: list[dict[str, Any]] = []
            for block in tool_blocks:
                name = str(_block_value(block, "name"))
                arguments = dict(_block_value(block, "input", {}))
                result = self._execute_tool(session, account, name, arguments)
                trace.append({"tool": name, "input": arguments, "result": result})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": str(_block_value(block, "id")),
                        "content": json.dumps(result, default=str),
                    }
                )
            messages.append({"role": "user", "content": results})

        raise RuntimeError("Claude exceeded the five-turn tool-use safety limit")

    def _create_message(self, **kwargs: Any) -> Any:
        for attempt in range(self.settings.claude_max_retries + 1):
            self.rate_limiter.acquire()
            try:
                return self.client.messages.create(**kwargs)
            except Exception as exc:
                if attempt >= self.settings.claude_max_retries or not self._is_retryable(exc):
                    raise
                retry_after = self._retry_after(exc)
                exponential = min(2**attempt, 30)
                delay = (
                    retry_after if retry_after is not None else exponential + self.random_source()
                )
                LOGGER.warning(
                    "claude_retry",
                    extra={
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                        "error": type(exc).__name__,
                    },
                )
                self.sleep(delay)
        raise AssertionError("retry loop exhausted")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        return (
            status == 429
            or (isinstance(status, int) and status >= 500)
            or type(exc).__name__
            in {
                "APIConnectionError",
                "APITimeoutError",
                "RateLimitError",
                "InternalServerError",
            }
        )

    @staticmethod
    def _retry_after(exc: Exception) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) if response is not None else {}
        value = headers.get("retry-after") if headers else None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        account_schema = {
            "type": "object",
            "properties": {"account_id": {"type": "string"}},
            "required": ["account_id"],
            "additionalProperties": False,
        }
        return [
            {
                "name": "get_account_signals",
                "description": "Return stored public-source evidence for one account.",
                "strict": True,
                "input_schema": account_schema,
            },
            {
                "name": "get_scoring_policy",
                "description": "Return the disclosed deterministic buying-trigger scoring rubric.",
                "strict": True,
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "get_integration_capabilities",
                "description": (
                    "Explain available CRM/enrichment preview boundaries and write guardrails."
                ),
                "strict": True,
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        ]

    @staticmethod
    def _execute_tool(
        session: Session, account: Account, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if name == "get_account_signals":
            if arguments.get("account_id") != account.id:
                return {"error": "account_id outside the authorized run scope"}
            signals = list(
                session.scalars(
                    select(Signal)
                    .where(Signal.account_id == account.id)
                    .order_by(Signal.occurred_on.desc())
                )
            )
            return {
                "account": {
                    "id": account.id,
                    "name": account.name,
                    "score": account.score,
                    "score_breakdown": account.score_breakdown,
                    "enrichment": account.enrichment,
                },
                "signals": [
                    {
                        "signal_id": item.id,
                        "external_id": item.external_id,
                        "classification": item.classification,
                        "status": item.status,
                        "occurred_on": item.occurred_on,
                        "evidence": item.evidence,
                        "source_url": item.source_url,
                    }
                    for item in signals
                ],
            }
        if name == "get_scoring_policy":
            return scoring_policy()
        if name == "get_integration_capabilities":
            return {
                "providers": ["salesforce", "hubspot", "clay"],
                "default_mode": "preview_only",
                "writes_enabled": False,
                "guardrail": (
                    "No provider write occurs without two explicit environment switches "
                    "and credentials."
                ),
            }
        return {"error": f"unknown tool: {name}"}

    @staticmethod
    def _validate_grounding(session: Session, account: Account, brief: AccountBrief) -> None:
        if brief.account_name.casefold() != account.name.casefold():
            raise ValueError("Claude account_name did not match the requested account")
        if brief.deterministic_score != account.score:
            raise ValueError("Claude changed the deterministic score")
        signals = {
            item.id: item
            for item in session.scalars(select(Signal).where(Signal.account_id == account.id))
        }
        for observation in brief.observations:
            signal = signals.get(observation.signal_id)
            if signal is None or str(observation.source_url) != signal.source_url:
                raise ValueError("Claude returned an observation with invalid evidence provenance")
        if "@" in brief.role_target:
            raise ValueError("role_target must be a role, not an email address")


class MockRevenueAgent:
    """Deterministic offline stand-in. Its outputs are simulations, never Claude results."""

    def analyze(self, session: Session, account: Account) -> AgentRun:
        started = time.perf_counter()
        signals = list(
            session.scalars(
                select(Signal)
                .where(Signal.account_id == account.id)
                .order_by(Signal.occurred_on.desc())
                .limit(3)
            )
        )
        if not signals:
            raise ValueError("Cannot analyze an account with no stored signals")
        qualification = "hot" if account.score >= 75 else "warm" if account.score >= 60 else "watch"
        brief = AccountBrief.model_validate(
            {
                "account_name": account.name,
                "qualification": qualification,
                "deterministic_score": account.score,
                "score_summary": (
                    "Offline simulation mirrors deterministic policy "
                    f"{account.score_breakdown.get('policy_version')}; "
                    "it is not a model judgment or business outcome."
                ),
                "observations": [
                    {
                        "fact": (
                            f"{item.classification or 'Unclassified'} report "
                            f"{item.external_id}: {item.evidence}"
                        ),
                        "signal_id": item.id,
                        "source_url": item.source_url,
                    }
                    for item in signals
                ],
                "hypotheses": [
                    "Hypothesis—not a fact: a quality leader may value faster "
                    "enforcement monitoring."
                ],
                "recommended_action": "human_review" if account.score >= 60 else "no_action",
                "role_target": "VP Quality / Chief Quality Officer",
                "outreach_angle": (
                    "Human-review draft: reference the public enforcement event and ask "
                    "whether a faster monitoring workflow would be useful. Do not imply a "
                    "private relationship or send automatically."
                ),
                "risks": [
                    "The source covers drug enforcement recalls, not every FDA "
                    "enforcement channel.",
                    "A trigger score is not evidence of purchase intent.",
                ],
                "confidence": 0.7,
            }
        )
        run = AgentRun(
            account_id=account.id,
            mode="mock",
            model="deterministic-mock-v1",
            status="completed",
            prompt_version=PROMPT_VERSION,
            output=brief.model_dump(mode="json"),
            tool_trace=[
                {
                    "tool": "get_account_signals",
                    "input": {"account_id": account.id},
                    "simulated": True,
                },
                {"tool": "get_scoring_policy", "input": {}, "simulated": True},
            ],
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        session.add(run)
        session.commit()
        AGENT_CALLS.labels("mock", "completed").inc()
        return run
