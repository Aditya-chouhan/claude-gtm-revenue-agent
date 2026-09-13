from __future__ import annotations

import argparse
import json
from pathlib import Path

from revenue_agent.config import get_settings
from revenue_agent.db import Base, build_engine, build_session_factory
from revenue_agent.human_eval import evaluate_human_labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.labels.read_text(encoding="utf-8").splitlines()]
    settings = get_settings()
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        report = evaluate_human_labels(session, rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote human evaluation report to {args.output}")


if __name__ == "__main__":
    main()
