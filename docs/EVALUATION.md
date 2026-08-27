# Evaluation

## What is evaluated

Every completed stored run is checked for:

- full `AccountBrief` schema validity
- 100% observation-to-signal ID and source URL validity
- deterministic score consistency
- exact account identity consistency
- explicit `Hypothesis` labelling
- no email or phone-like contact in the activation surface

A case passes only when every check passes. The evaluator reports per-case failures and the aggregate pass rate; it does not collapse undefined or missing evidence into a misleading success number.

## Offline evaluation receipt

The committed default evaluation uses `deterministic-mock-v1`. It proves that ingestion, tool-result shape, persistence, integration contracts, and evaluation logic work without an API key. It is **not a measure of Claude quality**.

Reproduce:

```bash
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent pipeline --source-mode fixture --agent-mode mock --analyze-top 5

DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent evaluate --mode mock
```

## Live-model evaluation

Set `ANTHROPIC_API_KEY`, run the same pipeline with `--agent-mode live`, then evaluate `--mode live`. Store the generated JSON only if you intend to publish the actual model output and its dated cost receipt.

No live-model score is claimed in this repository until such a run is committed. API-unit tests use a fake client to test strict tool use, structured output handling, token accounting, and retry behavior without mislabelling fake responses as Claude output.

## Current automated verification

On 2026-08-27, the local suite completed **15/15 tests** with **84% statement coverage**. This is software verification, not a GTM outcome. The exact result can change as the suite grows; GitHub Actions regenerates it on every push.
