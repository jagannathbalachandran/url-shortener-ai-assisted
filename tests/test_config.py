"""Tests for application settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortener.config import (
    DEFAULT_BASE_URL,
    DEFAULT_DATABASE_URL,
    Settings,
    get_settings,
)


def test_defaults_when_no_env_vars_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env file here to pick up

    settings = Settings()

    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.base_url == DEFAULT_BASE_URL


def test_database_url_overridden_by_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://u:p@host/db"


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
