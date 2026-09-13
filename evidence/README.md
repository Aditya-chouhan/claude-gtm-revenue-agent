# Evidence

Committed, unedited command output — not hand-transcribed into docs. Each file exists because a
number that was previously typed by hand into `docs/CASE_STUDY.md` (14 passing tests) didn't
match what CI actually produced (15). These files close that gap by making the source of truth
the artifact itself.

| File | Produced by | Notes |
|---|---|---|
| `adversarial_report_2026-08-27.json` | `revenue-agent evaluate --mode adversarial` | Seven deliberately corrupted `AccountBrief` payloads fed to `evaluate_run`. Unlike the mock-mode evaluation, this can fail — a `caught: false` on any case is a real defect. |
| `pytest_2026-08-27.txt` | `pytest --cov=src/revenue_agent --cov-report=term-missing` | Local run against SQLite on Python 3.11. **GitHub Actions is authoritative** (real Postgres, Python 3.12, regenerates every push) — this file is a point-in-time local reproduction, not a substitute for the Actions log. |
| `adversarial_report_2026-09-12.json` | `scripts/generate_adversarial_report.py` | Twelve structural and semantic corruptions; all 12 were caught. This checks deterministic guard behavior, not live-model quality. |
| `pytest_2026-09-12.xml` | `pytest --junitxml=...` | Machine-readable local result: 29 passed against SQLite. |
| `coverage_2026-09-12.xml` | `pytest --cov-report=xml:...` | Machine-readable local line coverage: 85.56%. |

Regenerate these artifacts with the documented commands; don't hand-edit the committed copies.

The 40-row file under `evaluation/` began as an intentionally unlabelled human-review queue. Its first row now has one AI-assisted user confirmation; the other human fields remain null. No independent human-evaluation report or live Claude inference receipt is claimed.

`ai_review_2026-09-13.md` summarizes the assistant's review of all 40 pairs: 10 supported and 30 unsupported by their cited sources. The per-row AI judgments are in `evaluation/ai_review_2026-09-13.jsonl`, in separate fields that do not count as human labels. This AI-authored diagnostic review is not a machine-generated test report or a representative quality benchmark.
