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

## T-02 — Database layer

### Plan review
Prompt: Implement @docs/tasks/T-02.md (plan-first via CLAUDE.md)
Assumptions accepted: 1 sync SQLAlchemy, 2 integer PK, 5 alembic/ at root,
7 placeholder local DB credentials, 8 no FastAPI wiring yet, 9 no mypy plugin
Changes requested:
 - REJECTED: AI planned to write AI_LOG.md and T-02 transcript — ownership
   boundary; the log is my review record
 - SQLite drops tzinfo → required tz-aware UTC round-trip on both DBs + test
 - Session must stay usable after CodeCollisionError → required reuse test
 - Migration test must also run on Postgres (CI); render_as_batch for SQLite
   so future ALTER migrations (T-06/T-07) work

### Review of output
- ACCEPTED (AI-initiated): mypy coverage extended to alembic/ — consistent
  with "all code passes mypy" convention
- ACCEPTED: migration test restores schema in `finally`, protecting the
  shared Postgres DB used by other tests in CI
- AI flagged: Postgres path unverified locally (no Docker) — deferred to CI

### Verification (by me)
- check.py: all gates pass; 12 tests; coverage 96%
- Assertion check: every test file has assertions (repository: 13)
- Mutation check: swallowed CodeCollisionError → 2 tests failed
  (duplicate-code, session-reuse) ✔; restored → all pass
- CI on Postgres (3.12, 3.13): PASSED

Duration: 1 hour

## T-03 — Create short link

### Plan review
Prompt: Implement @docs/tasks/T-03.md (plan-first via CLAUDE.md)
Plan: codegen, validation, service (with LinkWriter protocol), schemas,
dependencies, routes, app factory; unit + integration tests
Assumptions accepted: 1 no new deps, 2 plain {"detail"} errors (custom format
is T-05), 4 AI won't touch AI_LOG/transcripts, 5 exact route path
Changes requested:
 - BASE_URL trailing slash would produce "//" in short URLs → strip on load + test
 - Commit point not stated → required it documented; test must prove the link
   is committed before the response (AC2)
 - validate_url: accept uppercase schemes; reject whitespace/control chars
   rather than trimming (preserves "store exactly what was submitted")
 - Promoted log boundary into CLAUDE.md as a standing rule (AI respected it
   unprompted; made it explicit so it doesn't depend on session context)

### Review of output
- ACCEPTED: whitespace check runs on raw input before parsing — urlsplit silently
  strips some control chars, so a post-parse check would have cleaned bad input
  instead of rejecting it. Real library pitfall surfaced by the review point.
- ACCEPTED: commit test uses a separate DB connection, proving a real commit
  rather than same-session visibility
- ACCEPTED: settings stored on app.state so tests use a consistent BASE_URL
- CHALLENGED: B008 exemption looked like dead config (B not in extend-select).
  AI verified empirically: removed the block, B008 still fired — ruff 0.16.9
  enables B008 by default. Exemption was valid.
- DECIDED: made "B" (bugbear) explicit in extend-select so gates don't depend on
  ruff's implicit defaults across versions; no new findings

### Verification (by me)
- check.py: all gates pass; 56 tests; coverage 97%
- Manual API check via Swagger: 201 + 7-char code, correct short_url; same URL
  twice → different codes; javascript:/ftp:/no host/space/empty → 422;
  HTTPS:// accepted; BASE_URL trailing slash → no "//" <✔/✘ per item>
- CI (3.12, 3.13, Postgres): <result>
- Manual API check via Swagger: pending

## T-03 follow-up / #<n> — Lint config: bugbear selection and gate-tool pins — 2026-09-29 <HH:MM>

Tool: Claude Code (terminal, manual approval mode)
Related: T-03 (Depends() in route handlers), CLAUDE.md quality gates, scripts/check.py
Transcript: <transcripts-folder>/T-03-followup-lint-config.md

### Why this came up
While reviewing pyproject.toml after T-03, I noticed a
[tool.ruff.lint.flake8-bugbear] block (extend-immutable-calls =
["fastapi.Depends"]) even though "B" was not in extend-select. My hypothesis
was that bugbear rules weren't enabled, so the block was dead config.

### Prompt summary
1. Check whether the bugbear block has any effect, before changing anything.
2. Make bugbear selection explicit.
3. Pin the quality-gate dev dependencies to exactly the versions installed in
   the venv (read via `pip show`, not chosen by the AI); don't touch runtime
   dependencies; check whether CI installs any tool separately; show the
   version list and diff before applying.

### What the AI did
- Ran an experiment before editing: removed the bugbear block with "B" still
  absent from extend-select, then re-ran ruff check.
- Result: B008 (function-call-in-default-argument) still fired, 4 errors on
  the Depends() default arguments, the same ones as originally.
- Explanation: ruff 0.16.9's default rule set already includes B008
  (`ruff check --isolated --show-settings` lists 413 rules enabled with no
  config), so the exemption was doing real work.
- Restored the block, added "B" to extend-select, and ran scripts/check.py:
  no new B findings (exception re-raises already use `raise ... from exc`).
- Listed the installed versions of the five gate tools check.py relies on:
  ruff check, ruff format --check, mypy --strict, pytest, pip-audit, plus
  pytest-cov via pytest's --cov addopt.
- Checked .github/workflows/ci.yml: CI installs via `pip install -e ".[dev]"`
  with no separate tool installs, so pyproject.toml is the only place to pin.
- Proposed the pin diff (applied after my review):

  | Tool       | Before    | After    |
  |------------|-----------|----------|
  | ruff       | >=0.6.0   | ==0.16.9 |
  | mypy       | >=1.11.0  | ==2.3.1  |
  | pytest     | >=8.3.0   | ==9.1.1  |
  | pytest-cov | >=5.0.0   | ==7.1.0  |
  | pip-audit  | >=2.7.0   | ==2.10.1 |
  | httpx      | >=0.27.0  | unchanged (test client, not a gate) |

### Verification (done by me, independently)
- `ruff check --isolated --show-settings | Select-String "B008"` lists
  function-call-in-default-argument (B008) with config ignored, so it is a
  default rule in ruff 0.16.9. The AI's explanation is confirmed.
- Pins verified via `pip install -e ".[dev]" --dry-run`: all five tools
  "already satisfied" at the pinned versions; only the project itself would
  reinstall (normal for an editable install).
- `git diff pyproject.toml`: changes confined to the dev dependency list; no
  runtime dependency lines touched.
- B008 probe (throwaway file, deleted afterwards): a datetime.now() default
  was flagged; a Depends() default was not. The rule is active and the
  exemption is scoped to Depends only.
- scripts/check.py passes locally; CI green; CI log shows ruff 0.16.9
  installed.

### Verdict: EDITED
- Rejected (my hypothesis, disproved by experiment): "the bugbear block is
  dead config." It was actively suppressing B008 on FastAPI Depends().
  Removing it would have broken the lint gate.
- Accepted: add "B" to extend-select explicitly and keep the Depends
  exemption. The lint gate should not depend on ruff's implicit defaults,
  which can change between versions.
- Accepted: the AI scoped the pins to exactly the five gate tools check.py
  uses, left httpx as a range because it isn't a gate, and confirmed CI
  installs via .[dev] before proposing changes, so no workflow edit was needed.
- Edited (my direction): widened the change from "select B" to "pin all gate
  tools exactly", using installed versions only. The old ranges were loose
  (e.g. ruff>=0.6.0 while 0.16.9 was actually installed), so CI and a local
  machine could already run different rule sets and checker versions.

Tool: Claude Code (plan + implementation); Claude chat (independent review of
Claude Code's plan)

### Verdict: EDITED
Review process: I passed Claude Code's plans to Claude chat for a second
review, read its findings, and sent the corrections I agreed with back to
Claude Code. The analysis below credits whichever tool raised each point.

Accepted (Claude Code's proposals, kept as is):
- Not using Starlette's RedirectResponse, since it re-quotes URLs; the
  Location header is set directly.
- Route-shadowing analysis: /{code} matches single-segment paths only;
  registered last anyway, and tested by AC6.
- Format check in the service with unconstrained path parameters, so
  malformed codes return 404, not 422.
- Checking validation.py before proposing: CR/LF already rejected at creation;
  non-ASCII accepted in path and host.
- Latin-1 header analysis (non-ASCII above U+00FF → 500) and the quote()
  fix that percent-encodes only non-ASCII characters.
- Complete test-to-acceptance-criteria mapping.

Edited (raised by Claude chat's review; I agreed and directed the change):
- Café test: Claude Code expected byte-exact passthrough, contradicting its
  own quote() proposal (é becomes caf%C3%A9). Both non-ASCII tests now assert
  ASCII-only Location, UTF-8 percent-encoding, unquote(Location) == stored
  URL, and 302 (never 500).
- Brief updated with the non-ASCII Location exception, so the brief matches
  the implementation.

Rejected:
- Protocol rename LinkWriter → LinkStore (Claude Code's first plan): an
  unnecessary change to T-03 code. Replaced by a separate LinkReader protocol,
  as suggested in Claude chat's review.
- Optional reader plus a RuntimeError guard (Claude Code's second plan): it
  moved a wiring error from mypy (construction time) to runtime, and added a
  path that existed only for coverage. Claude chat pointed out this was a
  side effect of its own earlier suggestion not to touch the T-03 test
  doubles. Changed to a required parameter; the existing tests pass a minimal
  fake reader.