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
```

### Linux / macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/check.py
```

`scripts/check.py` runs all quality gates in order — ruff check, ruff format
--check, mypy --strict, pytest (with coverage), and pip-audit — stopping at
the first failure.

## Database

Configuration is via environment variables (see `.env.example`):

- `DATABASE_URL` — defaults to a local SQLite file (`sqlite:///./shortener.db`)
  if unset. Point it at Postgres (e.g. the docker-compose service below) with
  no code change: `postgresql+psycopg://shortener:shortener@localhost:5432/shortener`.
- `BASE_URL` — public short-link base, defaults to `http://localhost:8000`.

Schema is managed entirely through Alembic migrations (no `create_all` in
application code):

```bash
alembic upgrade head      # apply all migrations
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
