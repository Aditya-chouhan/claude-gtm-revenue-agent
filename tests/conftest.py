from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from revenue_agent.config import Settings
from revenue_agent.db import Base, build_engine, build_session_factory
from revenue_agent.ingest.openfda import OpenFDASource
from revenue_agent.ingest.service import IngestionService


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="sqlite://",
        auto_create_schema=True,
        claude_monthly_budget_usd=10,
    )


@pytest.fixture
def session(settings: Settings):
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as value:
        yield value
    engine.dispose()


@pytest.fixture
def seeded_session(session: Session) -> Session:
    IngestionService(session, OpenFDASource()).run(limit=100, source_mode="fixture")
    return session
