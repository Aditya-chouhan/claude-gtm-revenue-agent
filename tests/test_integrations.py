from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from revenue_agent.config import Settings
from revenue_agent.gateways.base import LiveWriteDisabled
from revenue_agent.gateways.providers import gateway_for
from revenue_agent.models import Account


@pytest.mark.parametrize("provider", ["salesforce", "hubspot", "clay"])
def test_preview_never_writes_and_declares_missing_config(
    provider: str, seeded_session: Session, settings: Settings
) -> None:
    account = seeded_session.scalar(select(Account).order_by(Account.name))
    gateway = gateway_for(provider, settings)
    preview = gateway.preview(seeded_session, account)  # type: ignore[arg-type]

    assert preview.mode == "preview"
    assert preview.would_write is False
    assert preview.payload
    assert preview.missing_configuration
    with pytest.raises(LiveWriteDisabled):
        gateway.deliver(seeded_session, account)  # type: ignore[arg-type]


def test_unknown_provider_is_rejected(settings: Settings) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        gateway_for("made-up-crm", settings)
