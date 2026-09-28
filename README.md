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
