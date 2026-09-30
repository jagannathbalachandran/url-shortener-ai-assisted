"""Test for the `shortener.main` ASGI entrypoint module."""

from __future__ import annotations

from fastapi import FastAPI

from shortener import main


def test_main_exposes_a_fastapi_app() -> None:
    assert isinstance(main.app, FastAPI)
