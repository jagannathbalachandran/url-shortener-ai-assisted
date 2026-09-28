"""ASGI entrypoint: `uvicorn shortener.main:app`."""

from __future__ import annotations

from shortener.app import create_app

app = create_app()
