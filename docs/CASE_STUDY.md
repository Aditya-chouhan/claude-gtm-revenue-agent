# Case study — from public signal to governed revenue action

## Problem

Most GTM-agent demos begin with a clean lead and end with generated copy. They skip the hard operating questions: where the signal came from, whether the same event is processed twice, which facts the model actually saw, what one call cost, what happens on a 429, and whether a generated recommendation can write into the CRM.

I built this system to make those questions the product.

## System

The pipeline ingests real drug-enforcement reports from openFDA, rolls recall lines into account records, derives public-source enrichment, and applies a disclosed trigger-intensity score. A Claude agent must use strict client tools to inspect the account evidence and scoring policy before returning a structured brief.

The service then validates that the account name and deterministic score are unchanged, every observation cites a stored signal ID and matching URL, and factual meaning is extractively supported by the cited signal. The result, token usage, estimated cost, latency, tool trace, prompt version, and errors persist in Postgres. Usage and cost survive malformed or grounding-rejected paid responses.

Salesforce, HubSpot, and Clay adapters translate the result into realistic field contracts. The public API only previews those payloads. No external write happens in the default or portfolio run.

## Reproducible evidence

- Real public fixture: 11 openFDA enforcement records across 5 recalling firms
- Dated live-source run: 25 records received, 24 persisted across 10 accounts, 1 rejected for a missing external identity
- Offline pipeline: idempotent ingest, enrichment, score, 5 simulated briefs, evaluation report
- Adversarial evaluation: 12 deliberately corrupted briefs covering structural and semantic failures, including unsupported facts behind valid citations, negation, stale-as-current evidence, wrong entities, and invented people — see `evidence/adversarial_report_<date>.json`
- Human-review queue: 40 claim/evidence pairs are committed unlabelled under `evaluation/`; this is review infrastructure, not a quality result
- Automated verification: see `evidence/pytest_<date>.xml` and `evidence/coverage_<date>.xml` for machine-generated local artifacts on that commit
- Operational surface: Postgres migration, FastAPI health/readiness/OpenAPI, Prometheus metrics, structured JSON logs, Docker Compose, and GitHub Actions

These are engineering results. They are not campaign or revenue results.

## Implemented but not yet executed

- **Live Claude interface** — strict tools, JSON Schema output, retries, rate limiting, budget and attempt-level cost tracking are implemented and unit-tested against a fake client (see `tests/test_agent.py`). It has not been exercised against the real service. No run receipt with real token counts, latency, or cost exists in this repo until an authorized operator executes it; until then, treat the live path as reviewed code, not reproducible evidence.
- **Human-labelled quality result** — the repository contains an unlabelled 40-row queue and an evaluator that requires at least 30 reviewer-attributed labels. No human-agreement, precision, recall, or F1 claim is made yet.

## Decisions that matter

**Deterministic score, probabilistic narrative.** A model is useful for synthesis and action framing; it should not be allowed to quietly rewrite a disclosed qualification rule.

**A valid citation is necessary, not sufficient.** A post-generation validator checks signal ID and source URL, then rejects unsupported numbers, polarity, recency, entities, and evidence terms attached to otherwise valid citations.

**Two explicit modes.** `mock` is reproducible and free; `live` is a real API call. The database and documentation keep the boundary visible.

**Preview before activation.** Portfolio code should prove that it understands enterprise integration contracts without pretending it owns a Salesforce org, HubSpot portal, Clay table, or contact database.

**Store every paid attempt.** Token usage and cost estimates belong beside completed, malformed, and grounding-rejected results, not only successful output.

## Limitations

- openFDA recalls are one type of public market trigger and are not a universal intent source.
- Source-derived location and product metadata are not a complete firmographic profile.
- A recall-trigger score does not establish propensity, budget, or willingness to buy.
- The process-local rate limiter does not coordinate multiple replicas.
- Semantic support uses a deterministic extractive contract, not a general-purpose natural-language entailment model; the human-labelled queue is intended to measure where that contract disagrees with reviewers.
- Live integration delivery is implemented behind guards but not exposed or claimed as executed.
- No campaign passed through the system, so there are no meeting, opportunity, pipeline, or revenue metrics.

## What I would add with a real customer

I would connect consented CRM outcomes, define human-labelled acceptance criteria with sales, measure precision and downstream conversion by score band, calibrate cost/latency budgets, and introduce a champion/challenger prompt rollout. Only then would I publish commercial lift.
