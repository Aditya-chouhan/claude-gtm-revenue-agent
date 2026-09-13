from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from revenue_agent.config import get_settings
from revenue_agent.db import build_engine, build_session_factory
from revenue_agent.models import AgentRun
from revenue_agent.receipts import build_live_receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--include-output", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    factory = build_session_factory(build_engine(settings.database_url))
    with factory() as session:
        if args.run_id:
            run = session.get(AgentRun, args.run_id)
        else:
            run = session.scalar(
                select(AgentRun)
                .where(AgentRun.mode == "live")
                .order_by(AgentRun.created_at.desc())
            )
        if run is None:
            raise SystemExit("No live AgentRun found. Execute an authorized live pipeline first.")
        receipt = build_live_receipt(run, include_output=args.include_output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"wrote sanitized live receipt to {args.output}")


if __name__ == "__main__":
    main()
