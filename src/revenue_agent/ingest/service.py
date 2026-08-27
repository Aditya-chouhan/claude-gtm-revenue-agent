from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.ingest.openfda import (
    OPENFDA_ENDPOINT,
    OpenFDASource,
    evidence_url,
    normalize_company_name,
    parse_openfda_date,
)
from revenue_agent.models import Account, Signal, stable_id
from revenue_agent.schemas import IngestResult
from revenue_agent.scoring import enrich_and_score_account


class IngestionService:
    def __init__(self, session: Session, source: OpenFDASource) -> None:
        self.session = session
        self.source = source

    def run(self, *, limit: int, source_mode: str) -> IngestResult:
        if source_mode == "fixture":
            records, fetched_at = self.source.fetch_fixture()
            records = records[:limit]
        elif source_mode == "live":
            records, fetched_at = self.source.fetch_live(limit)
        else:
            raise ValueError(f"Unsupported source mode: {source_mode}")
        return self._persist(records, fetched_at=fetched_at, source_mode=source_mode)

    def _persist(
        self, records: list[dict[str, Any]], *, fetched_at: datetime, source_mode: str
    ) -> IngestResult:
        inserted = 0
        updated = 0
        skipped_missing_identity = 0
        touched: dict[str, Account] = {}
        for record in records:
            firm = str(record.get("recalling_firm") or "").strip()
            recall_number = str(record.get("recall_number") or "").strip()
            if not firm or not recall_number:
                skipped_missing_identity += 1
                continue
            normalized = normalize_company_name(firm)
            account = self.session.scalar(
                select(Account).where(Account.normalized_name == normalized)
            )
            if account is None:
                account = Account(
                    id=stable_id("account", f"openfda:{normalized}"),
                    name=firm,
                    normalized_name=normalized,
                    country=record.get("country"),
                    state=record.get("state"),
                    city=record.get("city"),
                )
                self.session.add(account)
                self.session.flush()
            touched[account.id] = account

            signal = self.session.scalar(
                select(Signal).where(
                    Signal.source == "openfda", Signal.external_id == recall_number
                )
            )
            report_date = parse_openfda_date(record.get("report_date"))
            classification = record.get("classification", "Unclassified")
            values = {
                "account_id": account.id,
                "signal_type": "drug_enforcement_recall",
                "classification": record.get("classification"),
                "status": record.get("status"),
                "occurred_on": report_date.date() if report_date else None,
                "title": f"{classification} enforcement report {recall_number}",
                "evidence": str(record.get("reason_for_recall") or "Reason not supplied"),
                "source_url": evidence_url(recall_number),
                "raw_payload": record,
                "fetched_at": fetched_at,
            }
            if signal is None:
                signal = Signal(
                    id=stable_id("signal", f"openfda:{recall_number}"),
                    source="openfda",
                    external_id=recall_number,
                    **values,
                )
                self.session.add(signal)
                inserted += 1
            else:
                for key, value in values.items():
                    setattr(signal, key, value)
                updated += 1

        self.session.flush()
        for account in touched.values():
            enrich_and_score_account(self.session, account, as_of=fetched_at.date())
        self.session.commit()
        return IngestResult(
            source_mode=source_mode,
            raw_records=len(records),
            inserted_signals=inserted,
            updated_signals=updated,
            skipped_records=skipped_missing_identity,
            skip_reasons={"missing_recalling_firm_or_recall_number": skipped_missing_identity},
            accounts_touched=len(touched),
            source_url=OPENFDA_ENDPOINT,
            fetched_at=fetched_at,
        )
