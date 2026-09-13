from __future__ import annotations

import argparse
import json
from pathlib import Path

from revenue_agent.config import get_settings
from revenue_agent.db import Base, build_engine, build_session_factory
from revenue_agent.human_eval import build_human_label_queue
from revenue_agent.ingest.openfda import OpenFDASource
from revenue_agent.ingest.service import IngestionService


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
        rows = build_human_label_queue(session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    print(f"wrote {len(rows)} unlabelled rows to {args.output}")


if __name__ == "__main__":
    main()
