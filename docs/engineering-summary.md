# Engineering summary

## Objective and what was delivered

Build a URL shortener (create, redirect, look up, analyze) end to end, using
an AI-assisted, spec-first workflow, across three deliberately different
scenarios: greenfield, brownfield (existing code), and an ambiguous
requirement. Sources: docs/requirements.md, docs/plan.md, docs/adr/*,
docs/tasks/*, AI_LOG.md.

- **Greenfield (T-01–T-05b):** project scaffold and quality gates (T-01);
  database layer with a migrated schema (T-02); create a short link, with
  input validation and secure code generation (T-03, FR-1); redirect, link
  details, and 404 handling (T-04, FR-2/FR-3/FR-4); hardening — health/ready
  probes, a consistent JSON error shape, rate limiting on creation, and a
  redirect-latency test (T-05); a pre-baseline cleanup pass raising coverage
  to 100% and reducing pytest warnings from 6 to 1 (T-05b).
- **Brownfield (T-06):** a defect hunt against the existing baseline code
  found and fixed one confirmed defect (host-less URLs were accepted and
  stored, contradicting T-03's own acceptance criterion) using a test-first
  red/green process (Phase A); click analytics and a stats endpoint were
  then added on top of that fixed baseline (Phase B, FR-5/FR-6).
- **Ambiguous (T-07):** FR-7 ("links can expire") left nine open questions
  unanswered. Each was resolved as a decision in ADR-002 before any code was
  written, then implemented: optional creator-set `expires_at`, 410 on an
  expired redirect, details/stats still available after expiry.

## Approach

Spec-first workflow for every task: brief (docs/tasks/T-NN.md) → plan → an
independent review → implementation → verification → an AI_LOG entry.
Tools and roles (as stated in AI_LOG.md's header and used consistently
across entries): **Claude Code** (terminal) plans and implements; **Claude
chat** independently reviews Claude Code's plans (and, for T-07, drafted
the options behind ADR-002); the engineer decides every open question,
approves or rejects proposed changes, and verifies results independently
(a separate terminal, a stashed-fix comparison, or reading a diff directly)
rather than accepting a summary report at face value.

**Manual vs. auto mode:** AI_LOG.md states manual approval mode was used
initially, moving to auto mode later, "with oversight through plan approval
before implementation and verification afterwards." Auto mode is also where
the one unapproved deviation from an approved plan in this project occurred
(T-06 Phase B, see AI oversight below); the corrective action was a standing
instruction, from
that point on, to stop and ask before deviating from an approved plan,
rather than disclosing a deviation only after the fact.

## Traceability

| Requirement | Task | Evidence |
|---|---|---|
| FR-1 Create a short link | T-03 | tests/test_api_links.py, tests/test_validation.py, tests/test_codegen.py, tests/test_service.py |
| FR-2 Redirect | T-04 | tests/test_redirects.py |
| FR-3 404 for unknown codes | T-04 | tests/test_redirects.py, tests/test_api_link_details.py |
| FR-4 Link details | T-04 | tests/test_api_link_details.py |
| FR-5 Record each redirect as a click | T-06 | tests/test_redirect_click_recording.py, tests/test_click_repository.py |
| FR-6 Stats (total, per-day, top referrers) | T-06 | tests/test_api_link_stats.py, tests/test_stats_service.py, tests/test_click_repository.py |
| FR-7 Links can expire | T-07 | tests/test_validation.py, tests/test_service.py, tests/test_api_links.py, tests/test_redirects.py, tests/test_api_link_stats.py |
| NFR Performance (redirect p95 < 50 ms) | T-05 | tests/test_latency.py |
| NFR Security (http/https only, ≤2048 chars, non-guessable codes) | T-02/T-03 | tests/test_validation.py, tests/test_codegen.py |
| NFR Security (rate limiting on creation) | T-05 | tests/test_rate_limit.py, tests/test_api_rate_limit.py |
| NFR Security (no secrets in code) | T-01 (config via env) | src/shortener/config.py, .env.example; pip-audit gate in scripts/check.py |
| NFR Privacy (no raw IP stored) | T-05/T-06 | src/shortener/referrer.py (host only); tests/test_referrer.py, tests/test_redirect_click_recording.py; tests/test_click_repository.py::test_click_table_has_no_ip_user_agent_or_full_referrer_url_column; tests/test_rate_limit.py::test_idle_entries_are_evicted_after_the_window_passes (IP keys held only for the window, then evicted); tests/test_api_errors.py::test_unhandled_exception_returns_500_generic_body_and_logs_traceback (client host absent from logs). Stated design: docs/plan.md — "client IP used transiently, never stored." |
| NFR Reliability (health/ready) | T-05 | tests/test_health.py |
| NFR Reliability (consistent JSON errors) | T-05 | tests/test_errors.py, tests/test_api_errors.py |
| NFR Reliability (link committed before URL returned) | T-03 | tests/test_api_links.py (commit test, AC2) |
| NFR Portability (SQLite local, Postgres in CI) | T-02 | tests/test_migrations.py; .github/workflows/ci.yml |
| NFR Maintainability (layered design; complexity-bounded, fully-typed code) | T-01 | CLAUDE.md (layering, function/class size conventions); pyproject.toml `[tool.ruff.lint]` (C90 max-complexity=10, PLR0912/0913/0915) and `[tool.mypy] strict = true`; scripts/check.py coverage gate (≥85%) |

## Key decisions and trade-offs

Full rationale and rejected alternatives are in ADR-001 (D1 code
generation, D2 duplicate URLs, D3 redirect status, D4 click recording) and
ADR-002 (link expiry, resolving Q-6). In brief: random non-sequential
codes over sequential IDs; a new code per create rather than URL dedup; 302
over 301 so every click reaches the service (complete analytics, immediate
expiry); clicks recorded in a background task rather than synchronously
(the accepted trade-off is a click can be lost on a crash); link expiry is
optional, creator-set, and checked at request time, with expired links kept
(not deleted) so their stats remain queryable.

## Assumptions

- A-1 Reads outnumber writes ~1000:1.
- A-2 Creators are anonymous; production auth is handled by an API gateway.
- A-3 Links are permanent unless given an expiry.
- A-4 Design scale ~10M links; prototype is single-node.

## Risks and mitigations

- **Click loss on process crash** between sending the redirect and writing
  the click (ADR-001 D4). Mitigated by treating click counts as
  analytics, not business-critical data; the stated production path is a
  message queue with a separate consumer.
- **Rate limiter doesn't scale past one instance:** in-memory, per-process
  state means a client's limit resets per instance behind a load balancer.
  Production would use a shared store (e.g. Redis) and per-API-key limits
  at the gateway (README "Known limitations").
- **SQLite write contention under concurrency:** acceptable for local
  development; Postgres is the verified production target (CI runs the
  full suite against it).
- **Latency test measured more than the redirect:** one `scripts/check.py`
  run during T-08 failed only the latency gate (p95 exceeded 50 ms), while
  a rerun immediately after passed cleanly with no code change in between.
  Cause: T-06's click write is a background task the redirect response
  never waits for in production, but FastAPI's `TestClient` runs
  background tasks inline, so the test was timing that DB write too, on
  top of the redirect itself. Fix: `tests/test_latency.py` now overrides
  the `get_session_factory` dependency with a no-op session double for
  this test only, so only the redirect handler is timed; the 50 ms p95
  assertion itself is unchanged, and click recording continues to be
  covered by tests/test_redirect_click_recording.py. Local timings (this
  document's and AI_LOG's) were taken on a Windows laptop also running
  other workloads, not an isolated benchmark host; CI (Postgres, Linux
  runner) is the reference environment for this threshold.
- **Code-space exhaustion:** at 10M links, a collision on any single create
  is ~1 in 350,000 (ADR-001 D1); after 5 retries, exhaustion is surfaced to
  clients as 503 rather than assumed away.
- **Expired-link accumulation:** no cleanup job exists; rows accumulate
  indefinitely and there's no maximum expiry horizon (ADR-002). Revisit if
  storage growth becomes significant.
- **Referrer over-counting "(direct)":** browsers often strip or can fake
  the `Referer` header; accepted as a known limitation of header-based
  attribution, not a security issue (no PII is stored either way).
- **Dependency vulnerabilities:** mitigated by a pip-audit gate that must
  pass locally and in CI before any task is done; currently 0 known
  vulnerabilities.

## Quality evidence

From a `scripts/check.py` run made during this task (Python 3.13.15,
Windows, SQLite):

- ruff check: pass · ruff format --check: pass (76 files) · mypy --strict:
  pass (51 source files) · pip-audit: pass (0 known vulnerabilities)
- pytest: **193/193 passed**, 1 warning (pre-existing
  `StarletteDeprecationWarning` from `httpx`/`starlette.testclient`,
  tracked in README's known limitations)
- Coverage: **100.00%** (required threshold: 85%)

**Redirect latency (p95 < 50 ms, T-05.4):** the latency test (redirect
only, 20 warm-up + 300 samples) passes both locally and in CI. CI
(Postgres, Linux runner) is the reference environment for this threshold,
since local runs were taken on a shared Windows laptop.

**CI:** `.github/workflows/ci.yml` runs the identical gate on Python 3.12
and 3.13 against a Postgres 16 service container, least-privilege
(`permissions: contents: read`), current major versions (v7)
(`actions/checkout@v7`, `actions/setup-python@v7`), `timeout-minutes: 15`.

## AI oversight: notable cases

Each case is drawn from AI_LOG.md and cited by its section.

1. **Rejected — ownership boundary** (AI_LOG.md § T-02, "Changes
   requested"): the AI planned to write AI_LOG.md and the T-02 transcript
   itself. Rejected — the log is the engineer's review record, not AI
   output; this was later promoted into CLAUDE.md as a standing rule.
2. **My hypothesis, disproved by the AI's own experiment** (AI_LOG.md §
   T-03 follow-up): reviewing pyproject.toml, I hypothesized that a
   `fastapi.Depends()` lint exemption was dead config, since bugbear wasn't
   in `extend-select`. Rather than just asserting an answer, the AI ran an
   experiment (removed the exemption, re-ran ruff) and found it was in
   fact suppressing a real finding (B008) — disproving my hypothesis. The
   exemption was kept and made explicit.
3. **Edited — self-contradiction caught by independent review**
   (AI_LOG.md § T-04, "Edited"): the AI's own café/non-ASCII test expected
   byte-exact passthrough, contradicting its own percent-encoding proposal
   for the same code path. Caught by Claude chat's independent review of
   the plan, not by the AI itself; corrected before implementation.
4. **Instruction-following gap** (AI_LOG.md § T-05, "Instruction-following
   gap (main finding)"): after implementation, the AI reported all six
   approved changes as done. Asked for file-and-line confirmation of each
   one individually, two of the six (eviction throttling, log-field
   scoping) had not actually been made. Both were then fixed and
   re-verified. Recorded lesson: verify each approved change against the
   code, not against a summary report.
5. **Corrected factual claim** (AI_LOG.md § T-05b, "Corrected"): the AI
   claimed a specific GitHub Action version introduced Node 24 support,
   used to justify a version bump. Claude chat checked the claim against
   the actual GitHub release pages before it was applied: wrong for
   `actions/checkout` (v5, not v6); the target versions being applied were
   unaffected, but the unverified claim itself was rejected as a basis for
   the change.
6. **Self-found hidden defect, accepted after review** (AI_LOG.md § T-05,
   "Accepted (Claude Code's own work)"): implementing T-05, the AI found
   that Alembic's `fileConfig()` defaulted to `disable_existing_loggers=True`,
   which silently disabled the app's own logger whenever migrations ran
   in-process first — every test session. Left uncaught, this would have
   made error logging, and the test for it (AC4), unreliable. Fixed with
   `disable_existing_loggers=False`; outside the brief's file list, and
   accepted as justified.
7. **Unapproved deviation from an approved plan** (AI_LOG.md § T-06 Phase
   B, "Deviation made by Claude Code without asking"): with auto mode on,
   the AI reversed a previously approved decision (no cascade delete) to
   `ON DELETE CASCADE`, reasoning it was necessary for existing tests
   against Postgres. Accepted on the merits after review, but flagged as a
   process violation — a previously approved decision was changed without
   asking first, only disclosed afterward. This is the case that produced
   the standing instruction (recorded in this same AI_LOG entry) to stop
   and ask before deviating from an approved plan, rather than disclosing
   after the fact.

No contradictions were found between docs/requirements.md, docs/plan.md,
docs/adr/*, docs/tasks/*, AI_LOG.md, and the current code while assembling
this document.

## Limitations and production next steps

See README.md "Known limitations" for the full, current list (rate
limiting scope, latency-test methodology, IDN host encoding, dependency
pinning, the httpx deprecation warning, click-recording durability,
referrer-attribution accuracy, and unbounded expired-link retention).
Production next steps implied by those limitations and by the ADRs'
"Revisit if" triggers: a shared rate-limit store (Redis) behind a load
balancer; a message queue for click recording instead of an in-process
background task; a dependency lock file; and, if link volume or storage
growth warrants it, an archival or cleanup path for expired links.


