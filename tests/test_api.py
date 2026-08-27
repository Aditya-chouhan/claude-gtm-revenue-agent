from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from revenue_agent.config import Settings
from revenue_agent.main import create_app


def test_pipeline_and_preview_api() -> None:
    settings = Settings(app_env="test", database_url="sqlite://", auto_create_schema=True)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").status_code == 200
        run = client.post(
            "/v1/pipeline/run",
            json={
                "limit": 11,
                "source_mode": "fixture",
                "agent_mode": "mock",
                "analyze_top": 2,
            },
        )
        assert run.status_code == 200, run.text
        body = run.json()
        assert body["ingestion"]["raw_records"] == 11
        assert body["analyzed_accounts"] == 2

        accounts = client.get("/v1/accounts").json()
        assert len(accounts) == 5
        account_id = accounts[0]["id"]
        preview = client.get(f"/v1/integrations/salesforce/accounts/{account_id}/preview")
        assert preview.status_code == 200
        assert preview.json()["would_write"] is False
        assert client.get("/metrics").status_code == 200


def test_cost_bearing_endpoints_can_require_api_key() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        auto_create_schema=True,
        workflow_api_key=SecretStr("workflow-secret"),
    )
    payload = {
        "limit": 11,
        "source_mode": "fixture",
        "agent_mode": "none",
        "analyze_top": 0,
    }
    with TestClient(create_app(settings)) as client:
        assert client.post("/v1/pipeline/run", json=payload).status_code == 401
        assert (
            client.post(
                "/v1/pipeline/run",
                json=payload,
                headers={"x-api-key": "wrong"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/v1/pipeline/run",
                json=payload,
                headers={"x-api-key": "workflow-secret"},
            ).status_code
            == 200
        )
