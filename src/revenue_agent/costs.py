from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from revenue_agent.models import AgentRun


def estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    value = (
        input_tokens * input_usd_per_million + output_tokens * output_usd_per_million
    ) / 1_000_000
    return round(value, 8)


def month_to_date_cost(session: Session, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    value = session.scalar(
        select(func.coalesce(func.sum(AgentRun.estimated_cost_usd), 0.0)).where(
            AgentRun.created_at >= start
        )
    )
    return float(value or 0.0)


def assert_budget_available(session: Session, monthly_budget_usd: float) -> None:
    spent = month_to_date_cost(session)
    if spent >= monthly_budget_usd:
        raise RuntimeError(
            f"Claude monthly budget guard is closed: ${spent:.4f} spent of "
            f"${monthly_budget_usd:.2f} configured"
        )
