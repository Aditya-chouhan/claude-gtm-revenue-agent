from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.config import Settings
from revenue_agent.models import Account, AgentRun
from revenue_agent.schemas import IntegrationPreview


class Gateway(Protocol):
    provider: str

    def preview(self, session: Session, account: Account) -> IntegrationPreview: ...

    def deliver(self, session: Session, account: Account) -> dict[str, Any]: ...


class LiveWriteDisabled(RuntimeError):
    pass


class BaseGateway:
    provider = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def preview(self, session: Session, account: Account) -> IntegrationPreview:
        return IntegrationPreview(
            provider=self.provider,
            payload=self.build_payload(session, account),
            missing_configuration=self.missing_configuration(),
            notice=(
                "Payload preview only. No external request was made. Live writes require the "
                "global switch, the provider switch, credentials, and an explicit deliver call."
            ),
        )

    def build_payload(self, session: Session, account: Account) -> dict[str, Any]:
        raise NotImplementedError

    def missing_configuration(self) -> list[str]:
        raise NotImplementedError

    def assert_live_write_enabled(self) -> None:
        if not self.settings.live_integrations_enabled:
            raise LiveWriteDisabled("LIVE_INTEGRATIONS_ENABLED is false")
        missing = self.missing_configuration()
        if missing:
            raise LiveWriteDisabled("Missing live integration configuration: " + ", ".join(missing))

    @staticmethod
    def latest_brief(session: Session, account: Account) -> dict[str, Any] | None:
        run = session.scalar(
            select(AgentRun)
            .where(AgentRun.account_id == account.id, AgentRun.status == "completed")
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        return run.output if run else None
