# url-shortener-ai-assisted
AI assisted engineering to build URL shortener application

## Setup

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

## Database

Configuration is via environment variables (see `.env.example`):

- `DATABASE_URL` — defaults to a local SQLite file (`sqlite:///./shortener.db`)
  if unset. Point it at Postgres (e.g. the docker-compose service below) with
  no code change: `postgresql+psycopg://shortener:shortener@localhost:5432/shortener`.
- `BASE_URL` — public short-link base, defaults to `http://localhost:8000`.

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

## Endpoints

| Method | Path                        | Purpose                                    |
|--------|-----------------------------|---------------------------------------------|
| POST   | `/api/v1/links`             | Create a short link (rate limited)         |
| GET    | `/api/v1/links/{code}`      | Look up a link's details by its code       |
| GET    | `/api/v1/links/{code}/stats`| Per-link click analytics                   |
| GET    | `/{code}`                   | Redirect (302) to the original URL         |
| GET    | `/health`                   | Liveness probe; no DB access               |
| GET    | `/ready`                    | Readiness probe; 503 if the DB is unreachable |
| GET    | `/docs`, `/openapi.json`    | Interactive API docs / OpenAPI schema      |

Errors use one shape: `{"error": {"code": "...", "message": "...", "details"?: [...]}}`.

### Click analytics

Each redirect is recorded as a click in a background task, after the
response is sent (ADR-001 D4) -- so redirect latency is unaffected, but a
click can be lost if the process crashes between the response and the
write. Only the referrer's lowercase host is stored (never the full URL,
query string, path, or IP address/user agent); a missing, unparseable, or
implausibly long referrer host is recorded as `"(direct)"`.

`GET /api/v1/links/{code}/stats` returns:

- `total_clicks` — all-time total clicks for the link.
- `clicks_per_day` — clicks per UTC calendar day for the last 30 days
  (today and the preceding 29 days), ascending by date; days with zero
  clicks are omitted.
- `top_referrers` — all-time top 5 referrer hosts by click count.

(These windows are also documented on each field in the OpenAPI schema,
visible at `/docs`.)

## Known limitations

- Rate limiting on `POST /api/v1/links` is per client IP, in-memory, and
  per application instance (not shared across multiple instances behind a
  load balancer). It also uses a fixed window, so bursts are possible at
  window edges (e.g. a client can send up to 2x the limit across a window
  boundary). It keys on `request.client.host`, not `X-Forwarded-For`,
  since that header is spoofable without a trusted proxy in front of the
  service.
- The redirect latency test (p95 < 50 ms) runs in-process, so it measures
  app code, not real network latency.
- Non-ASCII (IDN) hosts in submitted URLs are percent-encoded in the
  redirect's `Location` header rather than converted to punycode.
- Runtime dependencies are pinned with version ranges, not exact pins; a
  lock file is a follow-up.
- `httpx`/`starlette.testclient` emits a deprecation warning
  (`StarletteDeprecationWarning`) recommending `httpx2`; no library change
  has been made yet.
