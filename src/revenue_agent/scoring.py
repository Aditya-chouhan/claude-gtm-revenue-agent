from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.models import Account, Signal

SCORING_POLICY_VERSION = "openfda-v1"
QUALITY_KEYWORDS = (
    "cgmp",
    "sterility",
    "contamination",
    "impurity",
    "foreign substance",
    "subpotent",
    "superpotent",
    "labeling",
)


def scoring_policy() -> dict[str, Any]:
    return {
        "version": SCORING_POLICY_VERSION,
        "maximum": 100,
        "components": {
            "severity": {"Class I": 35, "Class II": 22, "Class III": 10, "unknown": 0},
            "recency": {"0-30_days": 25, "31-90_days": 18, "91-180_days": 10, "older": 3},
            "distinct_events": {"5_plus": 20, "3-4": 14, "2": 8, "1": 4},
            "ongoing": 10,
            "quality_keyword": 10,
        },
        "interpretation": "Buying-trigger intensity, not a quality verdict or business outcome.",
    }


def _recency_points(latest: date | None, as_of: date) -> int:
    if latest is None:
        return 0
    age = max((as_of - latest).days, 0)
    if age <= 30:
        return 25
    if age <= 90:
        return 18
    if age <= 180:
        return 10
    return 3


def score_signals(
    signals: list[Signal], *, as_of: date | None = None
) -> tuple[int, dict[str, Any]]:
    as_of = as_of or datetime.now(UTC).date()
    severities = {"Class I": 35, "Class II": 22, "Class III": 10}
    severity = max((severities.get(item.classification or "", 0) for item in signals), default=0)
    latest = max((item.occurred_on for item in signals if item.occurred_on), default=None)
    recency = _recency_points(latest, as_of)
    events = {str(item.raw_payload.get("event_id", item.external_id)) for item in signals}
    event_count = len(events)
    frequency = 20 if event_count >= 5 else 14 if event_count >= 3 else 8 if event_count == 2 else 4
    ongoing = 10 if any((item.status or "").lower() == "ongoing" for item in signals) else 0
    keyword_matches = sorted(
        {
            keyword
            for item in signals
            for keyword in QUALITY_KEYWORDS
            if keyword in item.evidence.lower()
        }
    )
    quality = 10 if keyword_matches else 0
    total = min(severity + recency + frequency + ongoing + quality, 100)
    breakdown = {
        "policy_version": SCORING_POLICY_VERSION,
        "as_of": as_of.isoformat(),
        "severity": severity,
        "recency": recency,
        "frequency": frequency,
        "ongoing": ongoing,
        "quality_keyword": quality,
        "distinct_events": event_count,
        "latest_signal_date": latest.isoformat() if latest else None,
        "matched_keywords": keyword_matches,
        "total": total,
    }
    return total, breakdown


def enrich_and_score_account(
    session: Session, account: Account, *, as_of: date | None = None
) -> Account:
    signals = list(
        session.scalars(
            select(Signal)
            .where(Signal.account_id == account.id)
            .order_by(Signal.occurred_on.desc())
        )
    )
    score, breakdown = score_signals(signals, as_of=as_of)
    countries = sorted(
        {str(item.raw_payload["country"]) for item in signals if item.raw_payload.get("country")}
    )
    states = sorted(
        {str(item.raw_payload["state"]) for item in signals if item.raw_payload.get("state")}
    )
    product_types = sorted(
        {
            str(item.raw_payload["product_type"])
            for item in signals
            if item.raw_payload.get("product_type")
        }
    )
    classifications = sorted({item.classification for item in signals if item.classification})
    account.enrichment = {
        "provenance": "derived_only_from_stored_openfda_signals",
        "signal_count": len(signals),
        "countries": countries,
        "states": states,
        "product_types": product_types,
        "classifications": classifications,
        "latest_signal_date": breakdown["latest_signal_date"],
        "distinct_events": breakdown["distinct_events"],
    }
    account.score = score
    account.score_breakdown = breakdown
    account.scored_at = datetime.now(UTC)
    return account
