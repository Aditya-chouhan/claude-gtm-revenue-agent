# Evaluation

## What is evaluated

Every completed stored run is checked for:

- full `AccountBrief` schema validity
- 100% observation-to-signal ID and source URL validity
- extractive semantic support for evidence terms, numbers, polarity, recency, and account/entity identity
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

The adversarial harness feeds `evaluate_run` 12 deliberately corrupted `AccountBrief` payloads that no agent in this repo produces. Seven cover score, signal ID, source URL, account identity, fabricated contact details, and unlabelled speculation. Five use valid citation IDs and URLs but corrupt the cited meaning: an unsupported fact, negated evidence, stale evidence described as current, a wrong entity, and an invented person. Unlike the mock receipt above, this **can** fail: a `caught: false` on any case is a real defect. The committed `evidence/adversarial_report_2026-09-12.json` is machine-generated output.

Reproduce:

```bash
DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/revenue-agent pipeline --source-mode fixture --agent-mode none --analyze-top 0

DATABASE_URL=sqlite:///./revenue_agent.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/python scripts/generate_adversarial_report.py \
  --output evidence/adversarial_report_$(date +%F).json
```

The same 12 corruption types are unit-tested against `evaluate_run`, with agent-boundary coverage in `tests/test_agent.py`, so a regression fails CI rather than only a manually re-run report.

## Human-labelled evaluation

`evaluation/human_label_queue_2026-09-12.jsonl` contains 40 claim/evidence pairs derived from ten real fixture signals. Labels, reviewer names, and notes are null by design. This prevents generated expectations from being misrepresented as independent human judgment.

A reviewer should fill `human_label` with `supported`, `unsupported`, or `ambiguous`, add a non-empty `reviewer`, and optionally explain the decision in `notes`. The evaluator refuses fewer than 30 reviewer-attributed rows. Ambiguous rows are reported but excluded from binary precision, recall, and F1.

```bash
DATABASE_URL=sqlite:///./human_eval.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/python scripts/build_human_label_queue.py \
  --output evaluation/human_label_queue_$(date +%F).jsonl

# Edit the queue through an independent human review, then run:
DATABASE_URL=sqlite:///./human_eval.db AUTO_CREATE_SCHEMA=true \
  .venv/bin/python scripts/evaluate_human_labels.py \
  --labels evaluation/human_label_queue_$(date +%F).jsonl \
  --output evidence/human_evaluation_$(date +%F).json
```

## AI review — separate from human evaluation

All 40 pairs were reviewed by the OpenAI assistant on 2026-09-13. Per-row `ai_label`, `ai_rationale`, and reviewer provenance are in `evaluation/ai_review_2026-09-13.jsonl`; the scope and limitations are in `evidence/ai_review_2026-09-13.md`. Ten claims were judged supported and 30 unsupported by their cited sources.

These AI fields do not replace `human_label` or count toward the human evaluator's minimum. The first queue row has one user confirmation, explicitly marked AI-assisted because the assistant suggested the answer first. The remaining human fields stay null. The four repeated templates and concentrated source sample are diagnostic, not a representative held-out benchmark; no independent human or live-model quality claim follows from this review.

## Live-model evaluation

Set `ANTHROPIC_API_KEY`, run the same pipeline with `--agent-mode live`, then evaluate `--mode live`. Store the generated JSON only if you intend to publish the actual model output and its dated cost receipt.

**No live-model run has been committed to this repository as of 2026-09-12.** The Claude agent loop, strict tool use, structured output handling, retry behavior, semantic validation, and failed-attempt token accounting are unit-tested against a fake client (`tests/test_agent.py`) — that proves the code is wired correctly, not that it has executed against the real API. After an authorized run, `scripts/export_live_receipt.py` creates a sanitized receipt with model, status, prompt version, latency, token counts, estimated cost, error category, tool names, and an output hash while omitting raw tool data.

## Current automated verification

The committed `evidence/pytest_2026-09-12.xml` and `evidence/coverage_2026-09-12.xml` are machine-generated local artifacts. They record 29 passing tests and 85.56% line coverage in the local SQLite environment. **GitHub Actions is authoritative** — it uses real Postgres on Python 3.12 and regenerates on every push. If the two disagree, trust Actions.

```bash
.venv/bin/pytest --junitxml=evidence/pytest_$(date +%F).xml \
  --cov=src/revenue_agent --cov-report=xml:evidence/coverage_$(date +%F).xml \
  --cov-report=term-missing
```
