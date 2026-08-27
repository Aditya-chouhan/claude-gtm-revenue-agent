# Architecture

## Design objective

Build the smallest public system that proves end-to-end GTM engineering depth: signal acquisition, identity and persistence, deterministic decision logic, model orchestration, activation contracts, operational controls, and evaluation.

## Components

```text
openFDA adapter
    │ real public enforcement records
    ▼
IngestionService ── idempotency: source + recall_number
    │
    ├── accounts
    └── signals ───────────────┐
           Postgres            │ strict tool result
              │                ▼
              ├── deterministic enrichment + scoring
              │                │ immutable input
              │                ▼
              └────────► ClaudeRevenueAgent
                            │
                            ├── Pydantic/JSON Schema brief
                            ├── evidence-provenance guard
                            └── AgentRun audit record
                                      │
                                      ▼
                         Salesforce / HubSpot / Clay
                              preview-only API surface
```

## Trust boundaries

1. **Public source boundary.** `OpenFDASource` is the only network-facing signal adapter. Raw response fields are stored before model analysis.
2. **Decision boundary.** Scoring is deterministic and versioned. Claude can explain the score but a post-generation guard rejects any changed value.
3. **Model boundary.** Claude sees only the requested account's stored signals and disclosed policy through client tools. Strict schemas constrain tool inputs and the final output.
4. **Activation boundary.** The public service exposes integration previews, not delivery. Provider adapters fail closed unless both levels of write switches and credentials exist.
5. **Audit boundary.** Each agent run stores mode, model, prompt version, structured output, tool trace, token counts, estimated cost, latency, status, and sanitized error detail.

## Persistence model

- `accounts`: normalized public firm identity, source-derived enrichment, score, score policy breakdown
- `signals`: immutable external key, source evidence, source URL, raw public payload, fetch time
- `agent_runs`: one mock or live analysis attempt and its operational receipt
- `deliveries`: reserved audit table for an explicitly authorized future delivery surface

`source + external_id` is unique on signals. Re-ingestion updates the public record and re-scores the affected account without creating duplicates.

## Failure behavior

- An empty or malformed provider response fails the ingestion request.
- Connection, timeout, 429, and 5xx model failures retry; `retry-after` overrides local backoff.
- The Claude loop stops after five turns even if the model continues requesting tools.
- Schema, account, score, signal ID, or source URL mismatch fails the agent run and persists the error.
- Budget exhaustion prevents a new live call before it starts.
- Integration previews cannot write. Live adapters fail closed on missing switches or secrets.

## Scale path

The code uses synchronous FastAPI/SQLAlchemy deliberately so a reviewer can understand and run it quickly. A real high-volume deployment would move pipeline execution to a queue, apply a distributed token bucket, use per-tenant secrets, add row-level access control, and batch low-priority model evaluations. Those are scale changes, not hidden claims about the current demo.
