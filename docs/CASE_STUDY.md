# Case study — from public signal to governed revenue action

## Problem

Most GTM-agent demos begin with a clean lead and end with generated copy. They skip the hard operating questions: where the signal came from, whether the same event is processed twice, which facts the model actually saw, what one call cost, what happens on a 429, and whether a generated recommendation can write into the CRM.

I built this system to make those questions the product.

## System

The pipeline ingests real drug-enforcement reports from openFDA, rolls recall lines into account records, derives public-source enrichment, and applies a disclosed trigger-intensity score. A Claude agent must use strict client tools to inspect the account evidence and scoring policy before returning a structured brief.

The service then validates that the account name and deterministic score are unchanged and that every observation cites a stored signal ID and matching URL. The result, token usage, estimated cost, latency, tool trace, prompt version, and errors persist in Postgres.

Salesforce, HubSpot, and Clay adapters translate the result into realistic field contracts. The public API only previews those payloads. No external write happens in the default or portfolio run.

## Reproducible evidence

- Real public fixture: 11 openFDA enforcement records across 5 recalling firms
- Dated live-source run: 25 records received, 24 persisted across 10 accounts, 1 rejected for a missing external identity
- Offline pipeline: idempotent ingest, enrichment, score, 5 simulated briefs, evaluation report
- Automated verification: 14 passing tests and 84% statement coverage on 2026-08-27
- Live Claude interface: strict tools, JSON Schema output, retries, rate limiting, budget and cost tracking
- Operational surface: Postgres migration, FastAPI health/readiness/OpenAPI, Prometheus metrics, structured JSON logs, Docker Compose, and GitHub Actions

These are engineering results. They are not campaign or revenue results.

## Decisions that matter

**Deterministic score, probabilistic narrative.** A model is useful for synthesis and action framing; it should not be allowed to quietly rewrite a disclosed qualification rule.

**Evidence IDs, not “grounded” as a prompt adjective.** A post-generation validator checks the exact signal ID and source URL for every observation.

**Two explicit modes.** `mock` is reproducible and free; `live` is a real API call. The database and documentation keep the boundary visible.

**Preview before activation.** Portfolio code should prove that it understands enterprise integration contracts without pretending it owns a Salesforce org, HubSpot portal, Clay table, or contact database.

**Store operational truth.** Token usage and cost estimates belong beside the result, not in an anecdotal README claim.

## Limitations

- openFDA recalls are one type of public market trigger and are not a universal intent source.
- Source-derived location and product metadata are not a complete firmographic profile.
- A recall-trigger score does not establish propensity, budget, or willingness to buy.
- The process-local rate limiter does not coordinate multiple replicas.
- Live integration delivery is implemented behind guards but not exposed or claimed as executed.
- No campaign passed through the system, so there are no meeting, opportunity, pipeline, or revenue metrics.

## What I would add with a real customer

I would connect consented CRM outcomes, define human-labelled acceptance criteria with sales, measure precision and downstream conversion by score band, calibrate cost/latency budgets, and introduce a champion/challenger prompt rollout. Only then would I publish commercial lift.
