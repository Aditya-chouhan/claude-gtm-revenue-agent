from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from revenue_agent.config import get_settings
from revenue_agent.db import Base, build_engine, build_session_factory
from revenue_agent.evaluation import run_adversarial_evaluation
from revenue_agent.ingest.openfda import OpenFDASource
from revenue_agent.ingest.service import IngestionService
from revenue_agent.models import Account


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        IngestionService(session, OpenFDASource()).run(limit=100, source_mode="fixture")
        account = session.scalar(select(Account).order_by(Account.score.desc()))
        if account is None:
            raise SystemExit("fixture produced no account")
        report = run_adversarial_evaluation(session, account)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {report.caught}/{report.cases} caught cases to {args.output}")


if __name__ == "__main__":
    main()
