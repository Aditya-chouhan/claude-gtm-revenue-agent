from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./revenue_agent.db"
    auto_create_schema: bool = True
    public_base_url: str = "http://localhost:8000"
    workflow_api_key: SecretStr | None = None

    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-sonnet-5"
    claude_max_tokens: int = Field(default=1800, ge=256, le=8192)
    claude_requests_per_minute: int = Field(default=20, ge=1, le=10_000)
    claude_max_retries: int = Field(default=4, ge=0, le=10)
    claude_monthly_budget_usd: float = Field(default=10.0, ge=0)
    claude_input_usd_per_million: float = Field(default=2.0, ge=0)
    claude_output_usd_per_million: float = Field(default=10.0, ge=0)

    openfda_api_key: SecretStr | None = None
    openfda_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    live_integrations_enabled: bool = False
    salesforce_live_enabled: bool = False
    salesforce_instance_url: str | None = None
    salesforce_access_token: SecretStr | None = None
    hubspot_live_enabled: bool = False
    hubspot_access_token: SecretStr | None = None
    clay_live_enabled: bool = False
    clay_webhook_url: str | None = None
    clay_webhook_secret: SecretStr | None = None

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
