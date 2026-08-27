from __future__ import annotations

import argparse
import json

import uvicorn

from revenue_agent.config import get_settings
from revenue_agent.db import Base, build_engine, build_session_factory
from revenue_agent.evaluation import evaluate_completed_runs
from revenue_agent.pipeline import PipelineService
from revenue_agent.schemas import EvaluationReport, PipelineRequest, PipelineResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="revenue-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the FastAPI service")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    pipeline = subparsers.add_parser("pipeline", help="Run ingestion, scoring, and analysis")
    pipeline.add_argument("--source-mode", choices=["fixture", "live"], default="fixture")
    pipeline.add_argument("--agent-mode", choices=["none", "mock", "live"], default="mock")
    pipeline.add_argument("--limit", type=int, default=100)
    pipeline.add_argument("--analyze-top", type=int, default=3)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate stored mock or live runs")
    evaluate.add_argument("--mode", choices=["mock", "live"], default="mock")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        uvicorn.run("revenue_agent.main:app", host=args.host, port=args.port)
        return

    settings = get_settings()
    engine = build_engine(settings.database_url)
    if settings.auto_create_schema:
        Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        result: PipelineResult | EvaluationReport
        if args.command == "pipeline":
            result = PipelineService(session, settings).run(
                PipelineRequest(
                    limit=args.limit,
                    source_mode=args.source_mode,
                    agent_mode=args.agent_mode,
                    analyze_top=args.analyze_top,
                )
            )
        else:
            result = evaluate_completed_runs(session, args.mode)
        print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
