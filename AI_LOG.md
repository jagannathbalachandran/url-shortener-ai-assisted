# AI Log
Primary tool: Claude Code (terminal, manual approval mode)

## T-01 — Project scaffold and quality gates

### Plan review
Prompt: Implement @docs/tasks/T-01.md; list files + assumptions, wait for go-ahead.
Output: plan covering pyproject.toml, scripts/check.py, ci.yml, smoke test,
CLAUDE.md, README setup; 8 assumptions.
Assumptions accepted:
 1. setuptools build backend (most standard)
 2. static __version__ (no release process yet)
 3. CI on Linux only (Windows covered by local dev)
 4. ruff defaults + S security rules
 5. pip-audit needs network (tool constraint)
 6. coverage on app code only
 7. no LICENSE (out of scope)
 8. AI_LOG and transcript left for me
Changes requested:
 - Minimum version bounds on all deps (reproducibility; lock file deferred)
 - CI hardening: read-only permissions, pinned actions, timeout
 - mypy to cover scripts/ too
 - Promoted these into standing CLAUDE.md conventions

### File-level review
- pyproject.toml — EDITED: S101 (assert) would fail every pytest test;
  added per-file ignore for tests/ only, keeping S rules active on app code
- ci.yml — EDITED: added pip upgrade step (pip-audit flags outdated runner pip) (confirm)
- CLAUDE.md — EDITED:
  - plan-first rule lacked "wait for go-ahead", so it wasn't a real checkpoint; added
  - added Code design section (my standard): single responsibility, size targets
    (fn ≤20 lines/≤4 params, class ≤200 lines, exceptions justified), DI,
    pure core, specific exceptions, no magic values, docstrings
  - enforced measurable parts via ruff: C90 (max 10), PLR0912/0913/0915
- check.py — ACCEPTED: gates in order, stops on first failure, names failing gate,
  targeted `# noqa: S603` with justification on subprocess call
- test_smoke.py, __init__.py — ACCEPTED
- README.md — EDITED: added PowerShell execution-policy note after hitting it
  during my own verification (confirm)

### AI self-corrections (observed, accepted)
- Removed a stale `# noqa: S404`: rule not in installed ruff, flagged as unused (RUF100)
- pip-audit flagged known vulns in venv pip 26.0.1 → upgraded pip, re-ran gates.
  Confirms the CI pip-upgrade step was necessary.

### Verification (by me, separate terminal)
- pip install -e ".[dev]": succeeded
- python scripts/check.py: all 5 gates passed — ruff check ✔, ruff format ✔,
  mypy --strict (4 files) ✔, pytest 1/1 with 100% coverage (threshold 85%) ✔,
  pip-audit 0 known vulns ✔
- Lint-error test (AC5): added `import os` → failed at ruff (F401), exit code 1,
  later gates skipped; removed → all passed ✔
- Fail-closed: running without venv active → failed at first gate
  ("No module named ruff") rather than skipping ✔
- CI on GitHub (3.12, 3.13): <result after push>


### Summary
Decisions: 8 assumptions accepted; 4 plan changes; 3 file-level edits; 0 rejections
Duration: ~1h 30m (incl. ~30m one-time environment setup)
Commit: "T-01: scaffold, quality gates, CI, conventions" (see git log)