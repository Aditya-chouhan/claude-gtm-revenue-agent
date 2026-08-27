from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from revenue_agent.ingest.openfda import (
    OpenFDASource,
    evidence_url,
    normalize_company_name,
    parse_openfda_date,
)
from revenue_agent.ingest.service import IngestionService
from revenue_agent.models import Account, Signal


def test_openfda_helpers() -> None:
    assert normalize_company_name("  Cipla USA, Inc. ") == "cipla usa inc"
    assert parse_openfda_date("20260708").date().isoformat() == "2026-07-08"  # type: ignore[union-attr]
    assert "D-0661-2026" in evidence_url("D-0661-2026")


def test_fixture_is_declared_real_public_data() -> None:
    records, fetched_at = OpenFDASource.fetch_fixture()
    assert len(records) == 11
    assert fetched_at.isoformat() == "2026-07-16T08:41:00+00:00"
    assert all(record["recall_number"] and record["recalling_firm"] for record in records)


def test_ingestion_is_idempotent_and_scores_accounts(session: Session) -> None:
    service = IngestionService(session, OpenFDASource())
    first = service.run(limit=100, source_mode="fixture")
    second = service.run(limit=100, source_mode="fixture")

    assert first.inserted_signals == 11
    assert first.skipped_records == 0
    assert first.accounts_touched == 5
    assert second.inserted_signals == 0
    assert second.updated_signals == 11
    assert session.scalar(select(func.count()).select_from(Account)) == 5
    assert session.scalar(select(func.count()).select_from(Signal)) == 11
    accounts = list(session.scalars(select(Account)))
    assert all(account.score > 0 for account in accounts)
    assert all(
        account.enrichment["provenance"] == "derived_only_from_stored_openfda_signals"
        for account in accounts
    )
