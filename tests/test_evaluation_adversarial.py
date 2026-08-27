from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.evaluation import _valid_brief_dict, evaluate_run, run_adversarial_evaluation
from revenue_agent.models import Account, AgentRun, Signal

# This module exists because the mock-mode evaluation cannot fail by construction:
# MockRevenueAgent builds its brief by copying the same account/signal fields
# evaluate_run checks against, so every metric in an all-mock EvaluationReport is 1.0
# regardless of whether the grounding logic actually works. These tests instead feed
# evaluate_run seven deliberately corrupted briefs it never produced itself, and prove
# each one is rejected for the *specific reason* it should be. A case that silently
# passes here is a real defect in evaluate_run, not a score to round away.


def test_adversarial_report_catches_every_corruption(seeded_session: Session) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.score.desc()))
    assert account is not None

    report = run_adversarial_evaluation(seeded_session, account)

    assert report.cases == 7
    assert report.caught == report.cases
    assert report.catch_rate == 1.0
    for case in report.results:
        assert case.caught, f"{case.label} was not caught: {case.failures}"


def test_mutated_score_is_rejected(seeded_session: Session) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.score.desc()))
    assert account is not None
    report = run_adversarial_evaluation(seeded_session, account)
    case = next(c for c in report.results if c.label == "mutated_score")
    assert case.caught
    assert any("changed the deterministic score" in failure for failure in case.failures)


def test_fabricated_contact_is_rejected(seeded_session: Session) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.score.desc()))
    assert account is not None
    report = run_adversarial_evaluation(seeded_session, account)
    email_case = next(c for c in report.results if c.label == "fabricated_email")
    phone_case = next(c for c in report.results if c.label == "fabricated_phone")
    assert email_case.caught
    assert phone_case.caught


def test_wrong_signal_id_and_source_url_are_rejected(seeded_session: Session) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.score.desc()))
    assert account is not None
    report = run_adversarial_evaluation(seeded_session, account)
    for label in ("wrong_signal_id", "wrong_source_url"):
        case = next(c for c in report.results if c.label == label)
        assert case.caught, f"{label} was not caught: {case.failures}"


def test_a_correct_brief_still_passes(seeded_session: Session) -> None:
    """The adversarial suite must have discriminating power, not just reject everything."""
    account = seeded_session.scalar(select(Account).order_by(Account.score.desc()))
    assert account is not None
    real_signal = seeded_session.scalar(select(Signal).where(Signal.account_id == account.id))
    assert real_signal is not None

    run = AgentRun(
        id=str(uuid.uuid4()),
        account_id=account.id,
        mode="adversarial",
        model="adversarial-fixture",
        status="completed",
        prompt_version="adversarial-v1",
        output=_valid_brief_dict(account, real_signal),
    )
    run.account = account
    result = evaluate_run(seeded_session, run)
    assert result.passed
    assert not result.failures
