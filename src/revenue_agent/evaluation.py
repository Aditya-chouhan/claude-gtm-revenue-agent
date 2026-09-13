from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
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
WORD = re.compile(r"[a-z0-9]+")
NUMBER = re.compile(
    r"(?<![a-z0-9])[$€£]?\d[\d,]*(?:\.\d+)?%?(?:\s*(?:thousand|million|billion|[kmb]))?",
    re.IGNORECASE,
)
RECENCY_WORDS = {"current", "currently", "latest", "now", "recent", "recently", "today"}
NEGATION_WORDS = {"no", "not", "never", "neither", "without"}
FRAMING_WORDS = {
    "a",
    "according",
    "action",
    "an",
    "and",
    "as",
    "at",
    "by",
    "company",
    "evidence",
    "enforcement",
    "fda",
    "firm",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "openfda",
    "public",
    "recall",
    "record",
    "report",
    "reported",
    "reports",
    "source",
    "states",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


def _tokens(value: str) -> set[str]:
    return set(WORD.findall(value.casefold()))


def _numbers(value: str) -> set[str]:
    return {
        re.sub(r"[\s,$€£]", "", item.casefold())
        for item in NUMBER.findall(value)
    }


def _signal_corpus(account: Account, signal: Signal) -> str:
    fields = [
        account.name,
        signal.source,
        signal.external_id,
        signal.signal_type,
        signal.classification or "",
        signal.status or "",
        signal.occurred_on.isoformat() if signal.occurred_on else "",
        signal.title,
        signal.evidence,
        str(signal.source_url),
        str(signal.raw_payload),
    ]
    return " ".join(fields)


def observation_support_failures(
    account: Account,
    signal: Signal,
    fact: str,
    *,
    known_account_names: set[str] | None = None,
    as_of: date | None = None,
) -> list[str]:
    """Return deterministic reasons a cited fact is not supported by its evidence.

    This deliberately enforces an extractive observation contract. It does not claim
    to solve semantic entailment: if Claude wants to infer beyond the stored source,
    that statement belongs in `hypotheses`, not in an evidence-backed observation.
    """
    failures: list[str] = []
    corpus = _signal_corpus(account, signal)
    claim_tokens = _tokens(fact)
    corpus_tokens = _tokens(corpus)

    unsupported_numbers = sorted(_numbers(fact) - _numbers(corpus))
    if unsupported_numbers:
        failures.append(f"unsupported numeric claim(s): {', '.join(unsupported_numbers)}")

    unsupported_negation = sorted((claim_tokens & NEGATION_WORDS) - corpus_tokens)
    if unsupported_negation:
        failures.append(
            f"claim introduces unsupported negation: {', '.join(unsupported_negation)}"
        )

    today = as_of or date.today()
    recency = claim_tokens & RECENCY_WORDS
    if "today" in recency and signal.occurred_on != today:
        failures.append("claim says today but the stored signal has a different or missing date")
    elif recency:
        terminal = (signal.status or "").casefold() in {"closed", "completed", "terminated"}
        stale = signal.occurred_on is None or not (
            today - timedelta(days=90) <= signal.occurred_on <= today
        )
        if terminal or stale:
            failures.append("claim presents stale or terminal evidence as current")

    current_name = account.name.casefold()
    for name in known_account_names or set():
        folded = name.casefold()
        if folded != current_name and len(folded) >= 4 and folded in fact.casefold():
            failures.append(f"claim references another stored account: {name}")

    unsupported_tokens = sorted(
        token
        for token in claim_tokens - corpus_tokens - FRAMING_WORDS - RECENCY_WORDS
        if len(token) > 1 and not token.isdigit()
    )
    if unsupported_tokens:
        failures.append(
            "unsupported evidence token(s): " + ", ".join(unsupported_tokens[:12])
        )
    return failures


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
            semantic_support=0,
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
    semantically_supported = 0
    known_account_names = set(session.scalars(select(Account.name)))
    for index, observation in enumerate(brief.observations, start=1):
        signal = signals.get(observation.signal_id)
        if signal and signal.source_url == str(observation.source_url):
            valid_citations += 1
            semantic_failures = observation_support_failures(
                account,
                signal,
                observation.fact,
                known_account_names=known_account_names,
            )
            if semantic_failures:
                failures.extend(
                    f"observation {index}: {failure}" for failure in semantic_failures
                )
            else:
                semantically_supported += 1
    citation_validity = valid_citations / len(brief.observations) if brief.observations else 0.0
    semantic_support = (
        semantically_supported / len(brief.observations) if brief.observations else 0.0
    )
    observation_coverage = semantic_support
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
        semantic_support=round(semantic_support, 4),
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


def _adversarial_cases(
    account: Account, signal: Signal, other_account_name: str
) -> list[AdversarialCase]:
    """Twelve ways a brief can lie, and the failure the evaluator must produce for each.

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
    unsupported_fact = {
        **base,
        "observations": [
            {
                **_valid_observation(signal),
                "fact": "The company raised $50 million in new funding.",
            }
        ],
    }
    negated_evidence = {
        **base,
        "observations": [
            {
                **_valid_observation(signal),
                "fact": f"The source states the firm did not report {signal.evidence}",
            }
        ],
    }
    stale_as_current = {
        **base,
        "observations": [
            {
                **_valid_observation(signal),
                "fact": f"Today the source reports {signal.evidence}",
            }
        ],
    }
    wrong_entity = {
        **base,
        "observations": [
            {
                **_valid_observation(signal),
                "fact": f"{other_account_name} is the firm described by {signal.evidence}",
            }
        ],
    }
    invented_person = {
        **base,
        "observations": [
            {
                **_valid_observation(signal),
                "fact": f"Jane Doe, VP Quality, confirmed {signal.evidence}",
            }
        ],
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
        (
            "unsupported_fact_valid_citation",
            "A fabricated funding claim is attached to a real signal ID and URL",
            "unsupported numeric claim",
            unsupported_fact,
        ),
        (
            "negated_evidence",
            "A valid citation is used while reversing the source's meaning",
            "unsupported negation",
            negated_evidence,
        ),
        (
            "stale_as_current",
            "A dated signal is described as happening today",
            "claim says today",
            stale_as_current,
        ),
        (
            "wrong_entity_valid_citation",
            "A valid citation is attributed to a different stored account",
            "references another stored account",
            wrong_entity,
        ),
        (
            "invented_person",
            "An invented named person is attached to otherwise valid evidence",
            "unsupported evidence token",
            invented_person,
        ),
    ]


def run_adversarial_evaluation(session: Session, account: Account) -> AdversarialReport:
    """Prove the evaluator by what it rejects, not by a score it cannot fail to hit.

    `evaluate_completed_runs("mock")` reports 1.0 on every metric because
    `MockRevenueAgent` builds its output by copying the same stored account/signal
    fields the evaluator checks against — that comparison is circular and cannot fail
    by construction. This function instead evaluates deliberately corrupted
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

    other_account_name = session.scalar(
        select(Account.name).where(Account.id != account.id).order_by(Account.name)
    ) or "Unrelated Holdings"
    results: list[AdversarialCaseResult] = []
    for label, corruption, expected_substring, brief_dict in _adversarial_cases(
        account, signal, other_account_name
    ):
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
        dataset="adversarial_fixtures_v2",
        cases=len(results),
        caught=caught_count,
        catch_rate=round(caught_count / len(results), 4) if results else 0.0,
        results=results,
    )
