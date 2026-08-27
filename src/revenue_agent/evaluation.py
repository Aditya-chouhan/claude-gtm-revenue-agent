from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.models import Account, AgentRun, Signal
from revenue_agent.schemas import (
    AccountBrief,
    AdversarialCaseResult,
    AdversarialReport,
    EvaluationCaseResult,
    EvaluationReport,
)

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


def _valid_observation(signal: Signal) -> dict[str, Any]:
    classification = signal.classification or "Unclassified"
    return {
        "fact": f"{classification} report {signal.external_id}: {signal.evidence}",
        "signal_id": signal.id,
        "source_url": signal.source_url,
    }


def _valid_brief_dict(account: Account, signal: Signal) -> dict[str, Any]:
    return {
        "account_name": account.name,
        "qualification": "warm",
        "deterministic_score": account.score,
        "score_summary": "The disclosed deterministic trigger score is unchanged.",
        "observations": [_valid_observation(signal)],
        "hypotheses": ["Hypothesis—not a fact: a quality leader may value faster monitoring."],
        "recommended_action": "human_review",
        "role_target": "VP Quality",
        "outreach_angle": "Ask a human reviewer whether the public enforcement signal is relevant.",
        "risks": ["A public trigger does not prove purchase intent."],
        "confidence": 0.6,
    }


AdversarialCase = tuple[str, str, str, dict[str, Any]]


def _adversarial_cases(account: Account, signal: Signal) -> list[AdversarialCase]:
    """Seven ways a brief can lie, and the exact failure `evaluate_run` must produce for each.

    None of these dicts are produced by `MockRevenueAgent` or `ClaudeRevenueAgent` — they are
    built here specifically to be rejected. A case the evaluator does not catch is a real gap
    in the grounding checks, not a number to round away.
    """
    base = _valid_brief_dict(account, signal)

    mutated_score = {**base, "deterministic_score": (account.score + 5) % 101}
    wrong_signal_id = {
        **base,
        "observations": [{**_valid_observation(signal), "signal_id": "not-a-real-signal-id"}],
    }
    wrong_source_url = {
        **base,
        "observations": [
            {**_valid_observation(signal), "source_url": "https://example.com/fabricated"}
        ],
    }
    wrong_account_name = {**base, "account_name": f"{account.name} Holdings (fabricated)"}
    fabricated_email = {**base, "role_target": "Jane Doe <jane.doe@example.com>"}
    fabricated_phone = {
        **base,
        "outreach_angle": "Call the VP directly at +1 415 555 0134 to pitch.",
    }
    unlabeled_hypothesis = {
        **base,
        "hypotheses": ["A quality leader will definitely buy this quarter."],
    }

    return [
        (
            "mutated_score",
            "Claude changes the disclosed deterministic score",
            "changed the deterministic score",
            mutated_score,
        ),
        (
            "wrong_signal_id",
            "An observation cites a signal_id that does not exist",
            "did not map to stored source evidence",
            wrong_signal_id,
        ),
        (
            "wrong_source_url",
            "An observation cites a real signal_id but a fabricated source_url",
            "did not map to stored source evidence",
            wrong_source_url,
        ),
        (
            "account_name_mismatch",
            "The brief names a different company than the one analyzed",
            "account name mismatch",
            wrong_account_name,
        ),
        (
            "fabricated_email",
            "A person-like email address appears in contact-facing text",
            "person-like email or phone contact",
            fabricated_email,
        ),
        (
            "fabricated_phone",
            "A phone number appears in contact-facing text",
            "person-like email or phone contact",
            fabricated_phone,
        ),
        (
            "unlabeled_hypothesis",
            "A hypothesis is stated as fact instead of being explicitly labelled",
            "hypothesis not explicitly labelled",
            unlabeled_hypothesis,
        ),
    ]


def run_adversarial_evaluation(session: Session, account: Account) -> AdversarialReport:
    """Prove the evaluator by what it rejects, not by a score it cannot fail to hit.

    `evaluate_completed_runs("mock")` reports 1.0 on every metric because
    `MockRevenueAgent` builds its output by copying the same stored account/signal
    fields the evaluator checks against — that comparison is circular and cannot fail
    by construction. This function instead evaluates seven deliberately corrupted
    briefs that no agent in this repo produces. `caught=False` on any case is a real
    defect in `evaluate_run`, not noise.
    """
    signal = session.scalar(
        select(Signal).where(Signal.account_id == account.id).order_by(Signal.occurred_on.desc())
    )
    if signal is None:
        raise ValueError(
            f"account {account.id} has no stored signal to build adversarial cases from"
        )

    results: list[AdversarialCaseResult] = []
    for label, corruption, expected_substring, brief_dict in _adversarial_cases(account, signal):
        run = AgentRun(
            id=str(uuid.uuid4()),
            account_id=account.id,
            mode="adversarial",
            model="adversarial-fixture",
            status="completed",
            prompt_version="adversarial-v1",
            output=brief_dict,
        )
        run.account = account
        result = evaluate_run(session, run)
        caught = (not result.passed) and any(
            expected_substring in failure for failure in result.failures
        )
        results.append(
            AdversarialCaseResult(
                label=label,
                corruption=corruption,
                expected_failure_substring=expected_substring,
                caught=caught,
                failures=result.failures,
            )
        )

    caught_count = sum(result.caught for result in results)
    return AdversarialReport(
        dataset="adversarial_fixtures_v1",
        cases=len(results),
        caught=caught_count,
        catch_rate=round(caught_count / len(results), 4) if results else 0.0,
        results=results,
    )
