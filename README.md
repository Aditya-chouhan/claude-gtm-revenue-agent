# Claude GTM Revenue Agent

**A production-style revenue agent that turns real public market signals into evidence-grounded, human-reviewable GTM actions.**

This repository closes a specific gap in my GTM engineering portfolio: it calls a real LLM API, uses strict tool schemas and structured outputs, persists an audit trail, exposes an operational service, and defines guarded boundaries to the systems a revenue team actually uses.

The default run is intentionally safe and free: it loads a dated snapshot of real openFDA enforcement reports, applies deterministic enrichment and scoring, and uses a labelled offline mock in place of Claude. Live Claude mode requires your own `ANTHROPIC_API_KEY`. External CRM/enrichment writes are disabled by default.

> No campaign was run through this project. No pipeline, meeting, conversion, or revenue result is claimed.

## Why this is a GTM system

```text
real public signal                       controlled activation boundary
openFDA enforcement API                         Salesforce
        │                                        HubSpot
        ▼                                          Clay
ingest + deduplicate                                ▲
        │                                           │ preview by default
        ▼                                           │
Postgres audit store ──► enrich ──► score ──► Claude revenue agent
        ▲                                      │
        │                                      ├─ strict client tools
        │                                      ├─ structured JSON brief
        └──── tokens, cost, latency, trace ◄────┴─ grounding evaluation
```

The deterministic layer decides what the source data supports. Claude turns that evidence into a structured account brief; it cannot silently change the score. Every observation must point back to a stored signal ID and its openFDA URL.

## What is implemented

- Live openFDA ingestion with a committed real-data fixture for offline reproduction
- Idempotent account and signal persistence in Postgres via SQLAlchemy and Alembic
- Source-derived enrichment and a disclosed 0–100 trigger score
- Claude Messages API agent loop with strict tool use and JSON-schema output
- Retry with exponential backoff, `retry-after` support, process-local rate limiting, and a five-turn safety limit
- Per-run token usage, configurable cost estimation, latency, tool trace, prompt version, and monthly budget guard
- FastAPI service with health, readiness, OpenAPI, account, pipeline, analysis, integration-preview, and Prometheus endpoints
- Salesforce, HubSpot, and Clay payload boundaries with fail-closed live-write switches
- Importable n8n workflow for scheduling the FastAPI pipeline and polling run output
- Deterministic mock mode, an adversarial evaluation harness (seven deliberately corrupted briefs the grounding checks must reject — the mock mode alone cannot fail by construction, see [Evaluation](docs/EVALUATION.md)), tests, Docker Compose, and GitHub Actions
- Public evidence console and scheduled live-source smoke receipt

## Data and result boundaries

| Artifact | Classification | What it establishes |
|---|---|---|
| `data/real/openfda_snapshot.json` | **Real public data** | 11 openFDA enforcement records for 5 recalling firms, fetched 2026-07-16 |
| `data/real/live_ingestion_receipt_2026-08-27.json` | **Real live-run receipt** | The first real live run, 2026-08-27: 25 records received, 24 persisted across 10 accounts; 1 record failed the identity guard because `recall_number` was empty. Kept as-is; not refreshed. |
| `data/real/live_ingestion_receipt_latest.json` | **Real live-run receipt, auto-refreshed weekly** | Overwritten and committed by the scheduled `live-signal-smoke.yml` run below — reflects the most recent real ingestion against openFDA, not a fixed point in time |
| `source_mode=live` | **Real public data at runtime** | Fresh records returned by openFDA; counts can change |
| `agent_mode=mock` | **Simulated agent output** | Offline plumbing, schemas, persistence, guards, and deterministic evaluation |
| `agent_mode=live` | **Real Claude API output** | Only when the operator supplies an API key; usage and estimated cost are stored |
| Integration previews | **Simulated boundary payloads** | Field mapping only; no Salesforce, HubSpot, or Clay write occurred |

The fixture is small by design: it lets a reviewer reproduce the full pipeline without a network call. It is not a representative market sample and says nothing about real purchase intent.

The dated live receipt came from the implemented network path. It ran with `agent_mode=none`, so it proves signal ingestion without being misrepresented as a Claude execution.

## Live evidence console

The recruiter-facing [evidence console](https://aditya-chouhan.github.io/claude-gtm-revenue-agent/) turns the repository's committed proof into an inspectable review experience. It shows the real public-data receipt, recomputes the disclosed score from the committed snapshot, renders the labelled mock brief, and exposes preview-only Salesforce, HubSpot, and Clay payloads.

The **Verify with openFDA now** control performs a read-only browser request to the public API and recomputes account scores locally. That result is not persisted and is never described as a backend deployment, Claude execution, CRM sync, or revenue outcome.

GitHub Actions also runs a weekly live public-signal smoke test (`.github/workflows/live-signal-smoke.yml`) with `agent_mode=none`. It validates that records were actually received, publishes the JSON receipt as a 30-day workflow artifact, **and commits the reshaped receipt back to `data/real/live_ingestion_receipt_latest.json`** — so the repository itself, not just an ephemeral Actions log, shows an ongoing trail of real scheduled runs. Each fresh commit triggers an immediate redeploy of the evidence console below, so the console's numbers track the most recent real run rather than a single snapshot. No secret or paid API is required; `workflow_dispatch` lets anyone re-run it on demand.

Adding `ANTHROPIC_API_KEY` as a repository secret and pointing this same workflow at `--agent-mode live` (currently `none` by design, since this runs unattended and unreviewed on a schedule) would turn it into a genuinely live, scheduled, secret-managed Claude execution — the natural next step, deliberately not taken without the operator's key and explicit go-ahead on the recurring spend.

Local console preview:

```bash
make demo
# open http://localhost:4173
```

## Quick start — no API keys

```bash
cp .env.example .env
docker compose up --build -d

curl -s http://localhost:8000/health/ready
curl -s -X POST http://localhost:8000/v1/pipeline/run \
  -H 'content-type: application/json' \
  -d '{"limit":11,"source_mode":"fixture","agent_mode":"mock","analyze_top":3}'
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API. Prometheus metrics are at `/metrics`.

Local Python alternative:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent pipeline --source-mode fixture --agent-mode mock
```

## Run the real Claude path

```bash
export ANTHROPIC_API_KEY='set-this-locally-never-commit-it'
export DATABASE_URL='sqlite:///./revenue_agent.db'
export AUTO_CREATE_SCHEMA=true

.venv/bin/revenue-agent pipeline \
  --source-mode live \
  --agent-mode live \
  --limit 25 \
  --analyze-top 3

.venv/bin/revenue-agent evaluate --mode live
```

The Claude path uses:

- `get_account_signals` — only the requested account's stored evidence
- `get_scoring_policy` — the disclosed deterministic rubric
- `get_integration_capabilities` — preview/write guardrails
- `output_config.format` — a JSON Schema derived from the `AccountBrief` Pydantic model

Strict tool input validation follows Anthropic's [strict tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use) interface, and the final brief follows the [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) interface.

## Scoring policy

The maximum is 100:

- severity: up to 35
- recency: up to 25
- distinct enforcement events: up to 20
- ongoing status: 10
- disclosed quality-system keyword match: 10

The score measures **trigger intensity**, not company quality, propensity, account value, or expected revenue. Claude receives the score and breakdown but the service rejects a brief that changes it.

## API surface

- `POST /v1/pipeline/run` — ingest, score, and optionally analyze top accounts
- `GET /v1/accounts` — ranked account list
- `GET /v1/accounts/{id}` — stored signals and agent runs
- `POST /v1/accounts/{id}/analyze` — run `mock` or `live` analysis
- `GET /v1/integrations/{provider}/accounts/{id}/preview` — inspect a Salesforce, HubSpot, or Clay payload without writing
- `GET /health/live`, `GET /health/ready`, `GET /metrics`

Set `WORKFLOW_API_KEY` to require an `x-api-key` header on the two cost-bearing POST endpoints. It is optional for local evaluation and should be set for any shared deployment. The n8n template reads the matching secret from `REVENUE_AGENT_API_KEY`; it defaults to live Claude mode, so provide an Anthropic key or change `agent_mode` to `mock` before an offline demonstration.

## Reliability and cost controls

The Anthropic SDK's implicit retries are disabled so the repository's retry behavior is visible and testable. Retryable connection, timeout, 429, and 5xx failures use provider `retry-after` when available or capped exponential backoff with jitter. A local limiter smooths calls inside one process; Anthropic's organization-level limits remain authoritative.

Each agent run stores input/output tokens and an estimated cost using environment-configured prices. The defaults in `.env.example` were checked against Claude Sonnet 5 **introductory** API pricing on 2026-08-27 and are deliberately configuration—not immutable truth. **That introductory pricing ends 2026-08-31**; from 2026-09-01 the standard rate is $3.00 / $15.00 per MTok, and every `estimated_cost_usd` recorded under the old defaults understates real spend by roughly a third on input and half on output. Update `CLAUDE_INPUT_USD_PER_MILLION` / `CLAUDE_OUTPUT_USD_PER_MILLION` on that date. The budget guard closes new live runs when stored month-to-date estimated cost reaches `CLAUDE_MONTHLY_BUDGET_USD`.

## Integration safety

The public API exposes preview endpoints only. A provider adapter's `deliver()` method still fails unless all of the following are true:

1. `LIVE_INTEGRATIONS_ENABLED=true`
2. the provider-specific live switch is true
3. the provider endpoint/token/secret is present
4. application code explicitly invokes `deliver()`

No private credential, guessed token, fabricated contact, or claimed sync result is committed.

## Verify

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest --cov=src/revenue_agent --cov-report=term-missing
docker compose config --quiet

# Prove the grounding checks reject bad output — not just that a well-behaved
# mock agent passes them:
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent pipeline --source-mode fixture --agent-mode none --analyze-top 0
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent evaluate --mode adversarial
```

Committed, unedited command output for both the test suite and the adversarial evaluation is in [`evidence/`](evidence/README.md) — see it for what each file proves and which environment produced it.

See [Architecture](docs/ARCHITECTURE.md), [Evaluation](docs/EVALUATION.md), [Integration contracts](docs/INTEGRATIONS.md), and the [portfolio case study](docs/CASE_STUDY.md).

## Public sources

- [openFDA Drug Enforcement API](https://open.fda.gov/apis/drug/enforcement/)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/python/messages/create)
- [Anthropic rate limits](https://platform.claude.com/docs/en/api/rate-limits)

---

Built by [Aditya Chouhan](https://aditya-chouhan.github.io/) · [GitHub](https://github.com/Aditya-chouhan)
