# url-shortener-ai-assisted

A URL shortener: submit a long URL and get back a short link; opening the
short link redirects to the original URL. Per-link click analytics (total
clicks, clicks per day, top referrers) are recorded on each redirect.
Links may optionally expire.

## Setup (quick start)

Requires Python 3.11+ (developed on 3.13; CI runs on 3.12 and 3.13).

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/check.py
alembic upgrade head
uvicorn shortener.main:app --reload
```

### Linux / macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/check.py
alembic upgrade head
uvicorn shortener.main:app --reload
```

`scripts/check.py` runs all quality gates in order — ruff check, ruff format
--check, mypy --strict, pytest (with coverage), and pip-audit — stopping at
the first failure.

Schema is managed entirely through Alembic migrations (no `create_all` in
application code), so `alembic upgrade head` must be run before starting the
service — a fresh database (the default SQLite file included) has no tables
until migrations are applied.

Interactive API docs (Swagger UI) are then at http://localhost:8000/docs
(OpenAPI schema at http://localhost:8000/openapi.json). Drop `--reload` outside
of local development.

## Configuration

All configuration is via environment variables (see `.env.example`; copy it
to `.env` to override locally). Never commit real secrets.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./shortener.db` | DB connection string. Point at Postgres (e.g. the docker-compose service below) with no code change: `postgresql+psycopg://shortener:shortener@localhost:5432/shortener`. |
| `BASE_URL` | `http://localhost:8000` | Public base used to build short URLs. Trailing slashes are stripped. |
| `RATE_LIMIT_MAX_REQUESTS` | `10` | Requests allowed per window, per client IP, on `POST /api/v1/links`. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window length, in seconds. |

Other Alembic commands:

```bash
alembic downgrade base    # revert all migrations
alembic revision -m "..."  # add a new migration
```

For an optional local Postgres instance instead of SQLite:

```bash
docker compose up -d
```

CI runs the full test suite against a Postgres service container (see
`.github/workflows/ci.yml`); locally, tests default to a temporary SQLite
database unless `DATABASE_URL` is set.

## API

| Method | Path                        | Purpose                                    |
|--------|-----------------------------|---------------------------------------------|
| POST   | `/api/v1/links`             | Create a short link (rate limited)         |
| GET    | `/api/v1/links/{code}`      | Look up a link's details by its code       |
| GET    | `/api/v1/links/{code}/stats`| Per-link click analytics                   |
| GET    | `/{code}`                   | Redirect (302) to the original URL         |
| GET    | `/health`                   | Liveness probe; no DB access               |
| GET    | `/ready`                    | Readiness probe; 503 if the DB is unreachable |
| GET    | `/docs`, `/openapi.json`    | Interactive API docs / OpenAPI schema      |

All examples assume the default `BASE_URL` (`http://localhost:8000`).

### Create a short link (with `expires_at`)

```bash
curl -s -X POST http://localhost:8000/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/long/path", "expires_at": "2026-12-31T23:59:59+00:00"}'
```

```json
{
  "code": "aB3dE7f",
  "short_url": "http://localhost:8000/aB3dE7f",
  "original_url": "https://example.com/some/long/path",
  "created_at": "2026-09-30T12:00:00+00:00",
  "expires_at": "2026-12-31T23:59:59+00:00"
}
```

### Create a short link (no expiry)

```bash
curl -s -X POST http://localhost:8000/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/long/path"}'
```

Response is the same shape, with `"expires_at": null`.

### Redirect

```bash
curl -i http://localhost:8000/aB3dE7f
```

```
HTTP/1.1 302 Found
Location: https://example.com/some/long/path
Cache-Control: no-store
```

An expired link returns `410` instead (see error shape below).

### Link details

```bash
curl -s http://localhost:8000/api/v1/links/aB3dE7f
```

Same response shape as create.

### Link stats

```bash
curl -s http://localhost:8000/api/v1/links/aB3dE7f/stats
```

```json
{
  "code": "aB3dE7f",
  "total_clicks": 42,
  "clicks_per_day": [
    {"date": "2026-09-29", "count": 5},
    {"date": "2026-09-30", "count": 7}
  ],
  "top_referrers": [
    {"referrer": "news.example.com", "count": 20},
    {"referrer": "(direct)", "count": 15}
  ],
  "expires_at": null
}
```

`total_clicks` and `top_referrers` (top 5) are all-time; `clicks_per_day`
covers the last 30 UTC calendar days (today and the preceding 29), ascending
by date, omitting days with zero clicks. These windows are also documented
on each field in the OpenAPI schema at `/docs`.

### Health and readiness

```bash
curl -s http://localhost:8000/health
# {"status":"ok"}

curl -s http://localhost:8000/ready
# {"status":"ready"}, or 503 with the error shape below if the DB is unreachable
```

### Error shape

Every error response has the shape
`{"error": {"code": "...", "message": "...", "details"?: [...]}}`. `details`
(when present) is validation-only and never echoes submitted input.

```bash
curl -s -X POST http://localhost:8000/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{"url": "javascript:alert(1)"}'
```

```json
{"error": {"code": "invalid_url", "message": "Invalid URL."}}
```

Other error codes: `validation_error` (422, malformed request body),
`invalid_expiry` (422), `not_found` (404, unknown or malformed code),
`link_expired` (410), `rate_limited` (429, with a `Retry-After` header),
`code_space_exhausted` (503), `not_ready` (503), `method_not_allowed` (405),
`internal_error` (500, generic — the traceback is logged server-side, never
returned).

## Running tests and quality gates

```bash
pytest                    # full test suite, with coverage (see pyproject.toml addopts)
python scripts/check.py   # ruff check, ruff format --check, mypy --strict, pytest+coverage, pip-audit
```

`scripts/check.py` is the single source of truth for "does this pass" — it's
what CI runs, and stops at the first failing gate.

## Project structure

```
src/shortener/     application code (routes, services, repositories, models)
alembic/versions/  database migrations
tests/              unit and integration tests
scripts/check.py    quality-gate runner
docs/               requirements, plan, ADRs, task briefs, architecture, engineering summary
```

## Docs index

- [Requirements](docs/requirements.md)
- [Plan](docs/plan.md)
- ADRs: [001 — Core design decisions](docs/adr/001-core-design-decisions.md), [002 — Link expiry](docs/adr/002-link-expiry.md)
- Task briefs: [T-01](docs/tasks/T-01.md) · [T-02](docs/tasks/T-02.md) · [T-03](docs/tasks/T-03.md) · [T-04](docs/tasks/T-04.md) · [T-05](docs/tasks/T-05.md) · [T-05b](docs/tasks/T-05b.md) · [T-06](docs/tasks/T-06.md) · [T-07](docs/tasks/T-07.md) · [T-08](docs/tasks/T-08.md)
- [Architecture overview](docs/architecture.md)
- [Module reference](docs/module-reference.md) — every module/class, and a full request walkthrough
- [Engineering summary](docs/engineering-summary.md)
- [AI log](AI_LOG.md) and [transcripts](docs/transcripts/)

## Known limitations

- Rate limiting on `POST /api/v1/links` is per client IP, in-memory, and
  per application instance (not shared across multiple instances behind a
  load balancer). It also uses a fixed window, so bursts are possible at
  window edges (e.g. a client can send up to 2x the limit across a window
  boundary). It keys on `request.client.host`, not `X-Forwarded-For`,
  since that header is spoofable without a trusted proxy in front of the
  service.
- The redirect latency test (p95 < 50 ms) runs in-process, so it measures
  app code, not real network latency; the measurement includes the
  background click write, since FastAPI's `TestClient` runs background
  tasks inline (real clients don't wait for it).
- Non-ASCII (IDN) hosts in submitted URLs are percent-encoded in the
  redirect's `Location` header rather than converted to punycode.
- Runtime dependencies are pinned with version ranges, not exact pins; a
  lock file is a follow-up.
- `httpx`/`starlette.testclient` emits a deprecation warning
  (`StarletteDeprecationWarning`) recommending `httpx2`; no library change
  has been made yet.
- Click recording is in-process and best-effort: a click can be lost if the
  process crashes between sending the redirect response and writing the
  click row (ADR-001 D4); under concurrent writes SQLite can lock, and a
  failed click write is logged and dropped rather than retried. Postgres is
  the production target for this reason.
- Referrer tracking relies on the `Referer` header, which browsers often
  strip or which clients can fake; `"(direct)"` is likely over-counted.
- Expired links are kept indefinitely (no cleanup job), so their rows
  accumulate, and there's no maximum expiry horizon — a creator can set an
  arbitrarily far-future date (ADR-002).
