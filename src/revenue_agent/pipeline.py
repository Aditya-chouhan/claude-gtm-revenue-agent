from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.agent.claude import ClaudeRevenueAgent, MockRevenueAgent
from revenue_agent.config import Settings
from revenue_agent.ingest.openfda import OpenFDASource
from revenue_agent.ingest.service import IngestionService
from revenue_agent.models import Account
from revenue_agent.schemas import PipelineRequest, PipelineResult


class PipelineService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def run(self, request: PipelineRequest) -> PipelineResult:
        source = OpenFDASource(
            api_key=(
                self.settings.openfda_api_key.get_secret_value()
                if self.settings.openfda_api_key
                else None
            ),
            timeout_seconds=self.settings.openfda_timeout_seconds,
        )
        try:
            ingestion = IngestionService(self.session, source).run(
                limit=request.limit, source_mode=request.source_mode
            )
        finally:
            source.close()

        accounts = list(
            self.session.scalars(
                select(Account)
                .where(Account.score > 0)
                .order_by(Account.score.desc(), Account.name)
            )
        )
        run_ids: list[str] = []
        if request.agent_mode != "none" and request.analyze_top:
            agent = (
                ClaudeRevenueAgent(self.settings)
                if request.agent_mode == "live"
                else MockRevenueAgent()
            )
            for account in accounts[: request.analyze_top]:
                run = agent.analyze(self.session, account)
                run_ids.append(run.id)
        return PipelineResult(
            ingestion=ingestion,
            scored_accounts=len(accounts),
            analyzed_accounts=len(run_ids),
            agent_run_ids=run_ids,
        )
