from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.evaluation import observation_support_failures
from revenue_agent.models import Account, Signal

HUMAN_LABELS = {"supported", "unsupported", "ambiguous"}


def build_human_label_queue(session: Session, *, signals_limit: int = 10) -> list[dict[str, Any]]:
    """Build 40 claim/evidence pairs without assigning the human's answer."""
    pairs = list(
        session.execute(
            select(Account, Signal)
            .join(Signal, Signal.account_id == Account.id)
            .order_by(Account.name, Signal.external_id)
            .limit(signals_limit)
        )
    )
    if len(pairs) < signals_limit:
        raise ValueError(f"need {signals_limit} signals; found {len(pairs)}")
    account_names = [item.name for item, _ in pairs]
    rows: list[dict[str, Any]] = []
    for index, (account, signal) in enumerate(pairs, start=1):
        other_name = next(name for name in account_names if name != account.name)
        claims = [
            (
                f"{signal.classification or 'Unclassified'} report "
                f"{signal.external_id}: {signal.evidence}"
            ),
            "The company raised $50 million in new funding.",
            f"The source states the firm did not report {signal.evidence}",
            f"{other_name} is the firm described by {signal.evidence}",
        ]
        for variant, claim in enumerate(claims, start=1):
            rows.append(
                {
                    "claim_id": f"claim-{index:02d}-{variant}",
                    "account_id": account.id,
                    "account_name": account.name,
                    "signal_id": signal.id,
                    "source_url": signal.source_url,
                    "source_excerpt": signal.evidence,
                    "claim": claim,
                    "human_label": None,
                    "reviewer": None,
                    "notes": None,
                }
            )
    return rows


def evaluate_human_labels(
    session: Session, rows: list[dict[str, Any]], *, minimum_labels: int = 30
) -> dict[str, Any]:
    """Compare deterministic decisions with completed human labels.

    `ambiguous` rows are counted in coverage but excluded from binary precision,
    recall and F1 rather than silently forcing them into either class.
    """
    completed = [row for row in rows if row.get("human_label") in HUMAN_LABELS]
    if len(completed) < minimum_labels:
        raise ValueError(
            f"human evaluation requires at least {minimum_labels} labelled rows; "
            f"found {len(completed)}"
        )
    if any(not str(row.get("reviewer") or "").strip() for row in completed):
        raise ValueError("every human-labelled row must identify its reviewer")

    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "ambiguous": 0}
    results: list[dict[str, Any]] = []
    known_names = set(session.scalars(select(Account.name)))
    for row in completed:
        account = session.get(Account, row["account_id"])
        signal = session.get(Signal, row["signal_id"])
        if account is None or signal is None or signal.account_id != account.id:
            raise ValueError(f"unknown or mismatched evidence in {row['claim_id']}")
        machine_failures = observation_support_failures(
            account,
            signal,
            str(row["claim"]),
            known_account_names=known_names,
        )
        machine_label = "unsupported" if machine_failures else "supported"
        human_label = str(row["human_label"])
        if human_label == "ambiguous":
            counts["ambiguous"] += 1
        elif machine_label == "supported" and human_label == "supported":
            counts["tp"] += 1
        elif machine_label == "supported" and human_label == "unsupported":
            counts["fp"] += 1
        elif machine_label == "unsupported" and human_label == "supported":
            counts["fn"] += 1
        else:
            counts["tn"] += 1
        results.append(
            {
                "claim_id": row["claim_id"],
                "human_label": human_label,
                "machine_label": machine_label,
                "machine_failures": machine_failures,
                "agreed": human_label == machine_label if human_label != "ambiguous" else None,
            }
        )

    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    binary = len(completed) - counts["ambiguous"]
    agreements = counts["tp"] + counts["tn"]
    return {
        "dataset": "human_claim_labels_v1",
        "total_rows": len(rows),
        "labelled_rows": len(completed),
        "ambiguous_rows": counts["ambiguous"],
        "binary_rows": binary,
        "agreement_rate": round(agreements / binary, 4) if binary else None,
        "precision_supported": round(precision, 4) if precision is not None else None,
        "recall_supported": round(recall, 4) if recall is not None else None,
        "f1_supported": round(f1, 4) if f1 is not None else None,
        "confusion": counts,
        "results": results,
    }
