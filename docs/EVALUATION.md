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

The committed default evaluation uses `deterministic-mock-v1`. It proves that ingestion, tool-result shape, persistence, integration contracts, and evaluation logic work without an API key. It is **not a measure of Claude quality** — and, more specifically, **its pass rate cannot fail by construction.** `MockRevenueAgent` builds every observation by copying the same stored account and signal fields `evaluate_run` checks the output against, so a 1.0 on citation validity, score consistency, or account-identity consistency in this mode proves the mock agent copies correctly, not that the grounding checks work. See Adversarial evaluation below for the check that actually exercises them.

Reproduce:

```bash
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent pipeline --source-mode fixture --agent-mode mock --analyze-top 5

DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent evaluate --mode mock
```

## Adversarial evaluation

`evaluate --mode adversarial` feeds `evaluate_run` seven deliberately corrupted `AccountBrief` payloads that no agent in this repo produces — a mutated score, a fabricated `signal_id`, a fabricated `source_url`, a mismatched account name, an email and a phone number in contact-facing text, and an unlabelled speculative claim. Unlike the mock receipt above, this **can** fail: a `caught: false` on any case is a real defect in the grounding checks. The committed `evidence/adversarial_report_2026-08-27.json` is the real, run output — not hand-transcribed.

Reproduce:

```bash
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent pipeline --source-mode fixture --agent-mode none --analyze-top 0

DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent evaluate --mode adversarial
```

The same seven corruption types are also unit-tested directly against `evaluate_run` and against `ClaudeRevenueAgent._validate_grounding` in `tests/test_evaluation_adversarial.py` and `tests/test_agent.py`, so a regression fails CI, not just a manually re-run report.

## Live-model evaluation

Set `ANTHROPIC_API_KEY`, run the same pipeline with `--agent-mode live`, then evaluate `--mode live`. Store the generated JSON only if you intend to publish the actual model output and its dated cost receipt.

**No live-model run has been committed to this repository as of 2026-08-27.** The Claude agent loop, strict tool use, structured output handling, retry behavior, and token accounting are unit-tested against a fake client (`tests/test_agent.py`) — that proves the code is wired correctly, not that it has executed against the real API. Treat every claim about the live path as reviewed code until a dated run receipt with real token counts, latency, and cost lands in `evidence/`.

## Current automated verification

The committed `evidence/pytest_2026-08-27.txt` is the real, unedited output of the command below on that date — not a transcribed number, after the case study previously stated 14 passing tests when CI's own log said 15. It was captured locally against SQLite on Python 3.11; **GitHub Actions is the authoritative run** — it uses real Postgres on Python 3.12 and regenerates on every push. If the two ever disagree, trust the Actions log, not this file.

```bash
.venv/bin/pytest --cov=src/revenue_agent --cov-report=term-missing
```
