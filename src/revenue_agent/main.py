from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from revenue_agent.api import build_router
from revenue_agent.config import Settings, get_settings
from revenue_agent.db import Base, build_engine, build_session_factory
from revenue_agent.observability import RequestTelemetryMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_schema:
            Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Claude GTM Revenue Agent",
        version="0.1.0",
        description=(
            "Evidence-grounded public-signal ingestion, deterministic scoring, Claude analysis, "
            "and guarded CRM/enrichment boundaries."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = factory
    app.add_middleware(RequestTelemetryMiddleware)
    app.include_router(build_router(settings, factory))
    return app


app = create_app()
