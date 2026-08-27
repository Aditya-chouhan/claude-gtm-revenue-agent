from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Qualification(StrEnum):
    hot = "hot"
    warm = "warm"
    watch = "watch"
    skip = "skip"


class RecommendedAction(StrEnum):
    human_review = "human_review"
    export_to_crm = "export_to_crm"
    no_action = "no_action"


class EvidenceObservation(BaseModel):
    fact: str = Field(min_length=1, max_length=700)
    signal_id: str = Field(min_length=1, max_length=80)
    source_url: HttpUrl


class AccountBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_name: str = Field(min_length=1, max_length=300)
    qualification: Qualification
    deterministic_score: int = Field(ge=0, le=100)
    score_summary: str = Field(min_length=1, max_length=600)
    observations: list[EvidenceObservation] = Field(min_length=1, max_length=8)
    hypotheses: list[str] = Field(max_length=5)
    recommended_action: RecommendedAction
    role_target: str = Field(min_length=1, max_length=180)
    outreach_angle: str = Field(min_length=1, max_length=900)
    risks: list[str] = Field(max_length=5)
    confidence: float = Field(ge=0, le=1)


class SignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    external_id: str
    signal_type: str
    classification: str | None
    status: str | None
    occurred_on: date | None
    title: str
    evidence: str
    source_url: str
    fetched_at: datetime


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    model: str
    status: str
    prompt_version: str
    output: dict[str, Any] | None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    error_type: str | None
    created_at: datetime


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country: str | None
    state: str | None
    city: str | None
    enrichment: dict[str, Any]
    score: int
    score_breakdown: dict[str, Any]
    scored_at: datetime | None


class AccountDetail(AccountRead):
    signals: list[SignalRead]
    agent_runs: list[AgentRunRead]


class AnalyzeRequest(BaseModel):
    mode: Literal["live", "mock"] = "mock"


class IngestRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
    source_mode: Literal["live", "fixture"] = "fixture"


class IngestResult(BaseModel):
    source_mode: str
    raw_records: int
    inserted_signals: int
    updated_signals: int
    skipped_records: int
    skip_reasons: dict[str, int]
    accounts_touched: int
    source_url: str
    fetched_at: datetime


class PipelineRequest(IngestRequest):
    agent_mode: Literal["none", "live", "mock"] = "mock"
    analyze_top: int = Field(default=3, ge=0, le=25)


class PipelineResult(BaseModel):
    ingestion: IngestResult
    scored_accounts: int
    analyzed_accounts: int
    agent_run_ids: list[str]
    integration_mode: Literal["none", "preview_only"] = "preview_only"


class IntegrationPreview(BaseModel):
    provider: Literal["salesforce", "hubspot", "clay"]
    mode: Literal["preview"] = "preview"
    would_write: bool = False
    payload: dict[str, Any]
    missing_configuration: list[str]
    notice: str


class EvaluationCaseResult(BaseModel):
    case_id: str
    passed: bool
    schema_valid: bool
    citation_validity: float
    observation_coverage: float
    no_fabricated_contact: bool
    score_consistent: bool
    failures: list[str]


class EvaluationReport(BaseModel):
    mode: Literal["mock", "live"]
    dataset: str
    cases: int
    passed: int
    pass_rate: float
    results: list[EvaluationCaseResult]
