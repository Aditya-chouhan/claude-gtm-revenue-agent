from __future__ import annotations

import re
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.models import AgentRun, Signal
from revenue_agent.schemas import AccountBrief, EvaluationCaseResult, EvaluationReport

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")


def evaluate_run(session: Session, run: AgentRun) -> EvaluationCaseResult:
    failures: list[str] = []
    try:
        brief = AccountBrief.model_validate(run.output)
        schema_valid = True
    except Exception as exc:
        return EvaluationCaseResult(
            case_id=run.id,
            passed=False,
            schema_valid=False,
            citation_validity=0,
            observation_coverage=0,
            no_fabricated_contact=False,
            score_consistent=False,
            failures=[f"schema: {exc}"],
        )

    account = run.account
    signals = {
        item.id: item
        for item in session.scalars(select(Signal).where(Signal.account_id == run.account_id))
    }
    valid_citations = 0
    for observation in brief.observations:
        signal = signals.get(observation.signal_id)
        if signal and signal.source_url == str(observation.source_url):
            valid_citations += 1
    citation_validity = valid_citations / len(brief.observations) if brief.observations else 0.0
    observation_coverage = citation_validity
    if citation_validity < 1:
        failures.append("one or more observations did not map to stored source evidence")

    contact_surface = " ".join([brief.role_target, brief.outreach_angle, *brief.hypotheses])
    no_fabricated_contact = not EMAIL.search(contact_surface) and not PHONE.search(contact_surface)
    if not no_fabricated_contact:
        failures.append("output contains a person-like email or phone contact")

    score_consistent = account.score == brief.deterministic_score
    if not score_consistent:
        failures.append("model changed the deterministic score")

    if brief.account_name.casefold() != account.name.casefold():
        failures.append("account name mismatch")
    if any(not hypothesis.lower().startswith("hypothesis") for hypothesis in brief.hypotheses):
        failures.append("hypothesis not explicitly labelled")

    return EvaluationCaseResult(
        case_id=run.id,
        passed=not failures,
        schema_valid=schema_valid,
        citation_validity=round(citation_validity, 4),
        observation_coverage=round(observation_coverage, 4),
        no_fabricated_contact=no_fabricated_contact,
        score_consistent=score_consistent,
        failures=failures,
    )


def evaluate_completed_runs(session: Session, mode: Literal["mock", "live"]) -> EvaluationReport:
    runs = list(
        session.scalars(
            select(AgentRun)
            .where(AgentRun.mode == mode, AgentRun.status == "completed")
            .order_by(AgentRun.created_at)
        )
    )
    results = [evaluate_run(session, run) for run in runs]
    passed = sum(result.passed for result in results)
    return EvaluationReport(
        mode=mode,
        dataset="stored_agent_runs_v1",
        cases=len(results),
        passed=passed,
        pass_rate=round(passed / len(results), 4) if results else 0,
        results=results,
    )
