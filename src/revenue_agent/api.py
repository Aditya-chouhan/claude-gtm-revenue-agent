from __future__ import annotations

import hmac
from collections.abc import Generator

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from revenue_agent.agent.claude import ClaudeRevenueAgent, MockRevenueAgent
from revenue_agent.config import Settings
from revenue_agent.gateways.providers import gateway_for
from revenue_agent.models import Account, AgentRun
from revenue_agent.observability import metrics_response
from revenue_agent.pipeline import PipelineService
from revenue_agent.schemas import (
    AccountDetail,
    AccountRead,
    AgentRunRead,
    AnalyzeRequest,
    IntegrationPreview,
    PipelineRequest,
    PipelineResult,
)


def build_router(settings: Settings, factory: sessionmaker[Session]) -> APIRouter:
    router = APIRouter()

    def get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def require_api_key(
        x_api_key: str | None = Header(default=None, alias="x-api-key"),  # noqa: B008
    ) -> None:
        configured = settings.workflow_api_key
        if configured is None:
            return
        supplied = x_api_key or ""
        if not hmac.compare_digest(supplied, configured.get_secret_value()):
            raise HTTPException(status_code=401, detail="Invalid or missing workflow API key")

    @router.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready", tags=["health"])
    def ready(session: Session = Depends(get_db)) -> dict[str, str]:  # noqa: B008
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @router.get("/metrics", include_in_schema=False)
    def metrics():  # type: ignore[no-untyped-def]
        return metrics_response()

    @router.get("/v1/accounts", response_model=list[AccountRead], tags=["accounts"])
    def list_accounts(
        min_score: int = 0,
        session: Session = Depends(get_db),  # noqa: B008
    ) -> list[Account]:
        return list(
            session.scalars(
                select(Account)
                .where(Account.score >= min_score)
                .order_by(Account.score.desc(), Account.name)
            )
        )

    @router.get("/v1/accounts/{account_id}", response_model=AccountDetail, tags=["accounts"])
    def get_account(
        account_id: str,
        session: Session = Depends(get_db),  # noqa: B008
    ) -> Account:
        account = session.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        _ = account.signals, account.agent_runs
        return account

    @router.post("/v1/accounts/{account_id}/analyze", response_model=AgentRunRead, tags=["agent"])
    def analyze_account(
        account_id: str,
        request: AnalyzeRequest,
        _authorized: None = Depends(require_api_key),  # noqa: B008
        session: Session = Depends(get_db),  # noqa: B008
    ) -> AgentRun:
        account = session.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        try:
            agent = ClaudeRevenueAgent(settings) if request.mode == "live" else MockRevenueAgent()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        run = agent.analyze(session, account)
        if run.status == "failed":
            raise HTTPException(
                status_code=502, detail={"run_id": run.id, "error": run.error_message}
            )
        return run

    @router.post("/v1/pipeline/run", response_model=PipelineResult, tags=["pipeline"])
    def run_pipeline(
        request: PipelineRequest,
        _authorized: None = Depends(require_api_key),  # noqa: B008
        session: Session = Depends(get_db),  # noqa: B008
    ) -> PipelineResult:
        try:
            return PipelineService(session, settings).run(request)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get(
        "/v1/integrations/{provider}/accounts/{account_id}/preview",
        response_model=IntegrationPreview,
        tags=["integrations"],
    )
    def integration_preview(
        provider: str,
        account_id: str,
        session: Session = Depends(get_db),  # noqa: B008
    ) -> IntegrationPreview:
        account = session.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        try:
            return gateway_for(provider, settings).preview(session, account)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
