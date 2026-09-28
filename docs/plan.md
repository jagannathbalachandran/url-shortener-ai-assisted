# Plan — URL Shortener

## Task list
| Task | Description | Implements | Depends on | Scenario |
|---|---|---|---|---|
| T-01 | Scaffold, quality gates, CI, conventions | Foundation for all NFRs | — | Setup ✔ |
| ADR-001 | Core design decisions (Q-1, Q-2, Q-4, Q-5) | Q-1, Q-2, Q-4, Q-5 | — | Design |
| T-02 | Database layer: settings, link model, repository, migrations; CI on Postgres | Portability, Security (config via env, no secrets) | T-01, ADR-001 | Greenfield |
| T-03 | Create short link, with input security (see below) | FR-1, Security, Reliability (saved before URL returned) | T-02 | Greenfield |
| T-04 | Redirect, link details, 404 for unknown codes (see below) | FR-2, FR-3, FR-4 | T-03 | Greenfield |
| T-05 | Hardening: health, errors, rate limiting, latency test (see below) | Reliability, Security, Performance | T-04 | Greenfield |
| T-06 | Click analytics + stats endpoint; fix one defect in existing code (test-first) | FR-5, FR-6, Privacy, Performance (click recording must not slow redirects) | T-04 | Brownfield |
| T-07 | Link expiry: clarify Q-6, then implement | FR-7 | T-04 | Ambiguous |
| T-08 | Docs: README, architecture overview, final engineering summary | Deliverables | all | Release |

## Task breakdown

### T-03 — Create short link
- `POST /api/v1/links` creates a link and returns its short URL
- Input security:
  - only `http`/`https` URLs (reject `javascript:`, `data:`, `file:` etc.)
  - well-formed URL with a real host; max 2,048 characters
  - codes from a cryptographically secure generator (`secrets`), never sequential
- The link is committed to the database before the response is returned

### T-04 — Redirect and lookup
| Subtask | What | Done when |
|---|---|---|
| T-04.1 | `GET /{code}` redirects to the original URL | Status per ADR-001, `Location` header = long URL |
| T-04.2 | Unknown code | 404 with JSON error, never a 500 |
| T-04.3 | `GET /api/v1/links/{code}` returns details, no redirect | JSON: code, short URL, original URL, created time; 404 if unknown |

### T-05 — Hardening
| Subtask | What | Done when |
|---|---|---|
| T-05.1 | `GET /health` (app up), `GET /ready` (DB reachable) | `/health` 200; `/ready` 503 when DB unreachable |
| T-05.2 | Consistent JSON error shape for all errors | No stack traces to clients; unexpected errors logged, generic 500 |
| T-05.3 | Rate limiting on link creation (e.g. 10/min per client) | 429 when exceeded; redirects not rate-limited |
| T-05.4 | Redirect latency test | p95 < 50 ms over a few hundred requests; test fails otherwise |

Known trade-offs (T-05): in-memory rate limiter is per-instance (production: shared
store such as Redis); client IP used transiently, never stored. Latency test runs
in-process, so it measures app code, not network latency.

## Definition of done (every task)
- Tests written for the task's acceptance criteria:
  - unit tests for service and domain logic (e.g. URL validation, code generation)
  - integration tests for API endpoints through the full stack (API → service → DB)
- Edge and failure cases covered, not just the happy path
- `scripts/check.py` passes (lint, types, tests, coverage ≥ 85%, pip-audit)
- CI green on SQLite locally and Postgres in CI (from T-02 onwards)
- AI log entry written

## Sequencing
T-01 → ADR-001 → T-02 → T-03 → T-04 → T-05
                                  T-04 → T-06 (brownfield)
                                  T-04 → T-07 (ambiguous)
T-05, T-06, T-07 → T-08

T-06 and T-07 depend only on T-04, so they can be done in either order.

## Coverage check
Every FR (1–7) and every non-functional requirement maps to at least one task.
Scenarios: greenfield = T-02 to T-05, brownfield = T-06, ambiguous = T-07.