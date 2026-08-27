# Evidence

Committed, unedited command output — not hand-transcribed into docs. Each file exists because a
number that was previously typed by hand into `docs/CASE_STUDY.md` (14 passing tests) didn't
match what CI actually produced (15). These files close that gap by making the source of truth
the artifact itself.

| File | Produced by | Notes |
|---|---|---|
| `adversarial_report_2026-08-27.json` | `revenue-agent evaluate --mode adversarial` | Seven deliberately corrupted `AccountBrief` payloads fed to `evaluate_run`. Unlike the mock-mode evaluation, this can fail — a `caught: false` on any case is a real defect. |
| `pytest_2026-08-27.txt` | `pytest --cov=src/revenue_agent --cov-report=term-missing` | Local run against SQLite on Python 3.11. **GitHub Actions is authoritative** (real Postgres, Python 3.12, regenerates every push) — this file is a point-in-time local reproduction, not a substitute for the Actions log. |

Regenerate either file with the commands above; don't hand-edit the committed copies.
